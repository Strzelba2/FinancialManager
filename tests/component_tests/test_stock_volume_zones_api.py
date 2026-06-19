from __future__ import annotations

import base64
from datetime import date, timedelta
from uuid import uuid4

import allure
import httpx
import pytest


def _daily_csv(periods: int, start: date = date(2026, 1, 1)) -> str:
    lines = ["Date,Open,High,Low,Close,Volume"]
    for idx in range(periods):
        day = start + timedelta(days=idx)
        if idx < 16:
            close = 122 - idx * 1.2
            lines.append(f"{day.isoformat()},{close + 0.6:.2f},{close + 1.2:.2f},{close - 1.0:.2f},{close:.2f},1000")
        elif idx < 40:
            lines.append(f"{day.isoformat()},100.80,104.00,98.20,103.40,5200")
        else:
            close = 105 + (idx - 40) * 0.8
            lines.append(f"{day.isoformat()},{close - 0.4:.2f},{close + 1.0:.2f},{close - 1.1:.2f},{close:.2f},1800")
    return "\n".join(lines)


def _create_instrument_with_candles(stock_url: str, periods: int) -> tuple[str, str]:
    suffix = uuid4().hex[:4].upper()
    mic = f"V{suffix[:3]}"
    symbol = f"VZ{suffix}"

    market_response = httpx.post(
        f"{stock_url}/stock/markets",
        json={
            "mic": mic,
            "name": f"Volume Zone Market {suffix}",
            "country": "PL",
            "timezone": "Europe/Warsaw",
            "active": True,
            "currency": "PLN",
        },
        timeout=10.0,
    )
    assert market_response.status_code == 201, market_response.text

    instrument_response = httpx.post(
        f"{stock_url}/stock/instruments",
        json={
            "market_mic": mic,
            "symbol": symbol,
            "shortname": symbol,
            "name": f"Volume Zone Test {suffix}",
            "type": "STOCK",
            "status": "ACTIVE",
            "currency": "PLN",
            "isin": None,
            "historical_source": None,
            "quote_source": None,
            "popularity": 0,
            "last_seen_at": None,
        },
        timeout=10.0,
    )
    assert instrument_response.status_code == 201, instrument_response.text

    content = base64.b64encode(_daily_csv(periods).encode("utf-8")).decode("ascii")
    import_response = httpx.post(
        f"{stock_url}/stock/instruments/{symbol}/candles/daily/import_csv",
        json={
            "filename": "volume-zones.csv",
            "content_b64": content,
            "return_all": False,
            "include_items": False,
        },
        timeout=10.0,
    )
    assert import_response.status_code == 200, import_response.text
    return mic, symbol


@pytest.mark.component
@pytest.mark.db
@allure.epic("System Tests")
@allure.feature("Component")
@allure.story("Stock volume-zone API analyzes deterministic OHLCV candles")
@allure.severity(allure.severity_level.CRITICAL)
@allure.tag("stock", "market-data", "reports", "volume-zones", "api-contract")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
@allure.description(
    "Verifies the public stock API contract used by Next UI: deterministic daily "
    "candles can be analyzed into volume zones, no historical free-float is claimed, "
    "and cache keys move when a later candle is imported."
)
class TestStockVolumeZonesApi:
    def test_volume_zones_endpoint_returns_shape_and_updates_after_new_candle(self, stock_url: str) -> None:
        mic, symbol = _create_instrument_with_candles(stock_url, periods=52)

        response = httpx.get(
            f"{stock_url}/stock/analysis/{mic}/{symbol}/volume-zones",
            params={"mode": "summary", "max_zones": "3"},
            timeout=10.0,
        )

        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["symbol"] == symbol
        assert payload["mic"] == mic
        assert payload["calculation_version"] == "1.5.1"
        assert payload["configuration_version"] == "1.4.1"
        assert payload["data_quality"]["historical_free_float_available"] is False
        assert "DAILY_OHLCV_PROXY_NOT_ORDER_FLOW" in payload["data_quality"]["warnings"]
        assert len(payload["zones"]) <= 3
        assert payload["current_state"]["state"]
        assert isinstance(payload["directional_episodes"], list)
        assert isinstance(payload["resolved_directional_episodes"], list)
        assert isinstance(payload["major_directional_phases"], list)
        if payload["major_directional_phases"]:
            phase = payload["major_directional_phases"][0]
            assert "setup_score" in phase
            assert "historical_outcome_score" in phase
            assert "expected_direction_return" in phase

        cached_response = httpx.get(
            f"{stock_url}/stock/analysis/{mic}/{symbol}/volume-zones",
            params={"mode": "summary", "max_zones": "3"},
            timeout=10.0,
        )
        assert cached_response.status_code == 200, cached_response.text
        assert cached_response.json()["as_of"] == payload["as_of"]

        updated_content = base64.b64encode(_daily_csv(53).encode("utf-8")).decode("ascii")
        import_response = httpx.post(
            f"{stock_url}/stock/instruments/{symbol}/candles/daily/import_csv",
            json={
                "filename": "volume-zones-updated.csv",
                "content_b64": updated_content,
                "return_all": False,
                "include_items": False,
            },
            timeout=10.0,
        )
        assert import_response.status_code == 200, import_response.text

        updated_response = httpx.get(
            f"{stock_url}/stock/analysis/{mic}/{symbol}/volume-zones",
            params={"mode": "summary", "max_zones": "3"},
            timeout=10.0,
        )
        assert updated_response.status_code == 200, updated_response.text
        assert updated_response.json()["as_of"] > payload["as_of"]

    def test_volume_zones_endpoint_rejects_too_short_history(self, stock_url: str) -> None:
        mic, symbol = _create_instrument_with_candles(stock_url, periods=8)

        response = httpx.get(
            f"{stock_url}/stock/analysis/{mic}/{symbol}/volume-zones",
            timeout=10.0,
        )

        assert response.status_code == 422, response.text
        assert "valid daily candles are required" in response.json()["detail"]
