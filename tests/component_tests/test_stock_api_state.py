from __future__ import annotations

from uuid import uuid4

import allure
import httpx
import pytest


@pytest.mark.component
@pytest.mark.db
@allure.epic("System Tests")
@allure.feature("Component")
@allure.story("Stock manual market and instrument API supports quote_source instruments")
@allure.severity(allure.severity_level.CRITICAL)
@allure.tag("stock", "market-data", "quote-source", "api-contract")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
@allure.description(
    "Verifies the public stock API contract used by Next UI and wallet: a market can "
    "be added manually, an instrument can be added with a quote_source URL, "
    "and the instrument can then be resolved by MIC and symbol."
)
class TestStockManualInstrumentApi:
    def test_create_market_and_instrument_with_quote_source_then_resolve(
        self, stock_url: str, quote_source_base_url: str
    ) -> None:
        suffix = uuid4().hex[:4].upper()
        mic = suffix
        empty_mic = f"Z{suffix[:3]}"
        symbol = f"L{suffix}.UK"[:12]
        isin = f"US{uuid4().hex[:9].upper()}0"

        market_response = httpx.post(
            f"{stock_url}/stock/markets",
            json={
                "mic": mic,
                "name": f"Manual Market {suffix}",
                "country": "UK",
                "timezone": "Europe/London",
                "active": True,
                "currency": "GBP",
            },
            timeout=10.0,
        )

        assert market_response.status_code == 201, market_response.text
        assert market_response.json()["mic"] == mic
        assert market_response.json()["currency"] == "GBP"

        empty_market_response = httpx.post(
            f"{stock_url}/stock/markets",
            json={
                "mic": empty_mic,
                "name": f"Empty Manual Market {suffix}",
                "country": "UK",
                "timezone": "Europe/London",
                "active": True,
                "currency": "GBP",
            },
            timeout=10.0,
        )
        assert empty_market_response.status_code == 201, empty_market_response.text

        instrument_response = httpx.post(
            f"{stock_url}/stock/instruments",
            json={
                "market_mic": mic,
                "symbol": symbol,
                "shortname": symbol,
                "name": "WisdomTree Natural Gas",
                "type": "ETF",
                "status": "ACTIVE",
                "currency": "USD",
                "isin": isin,
                "historical_source": None,
                "quote_source": f"{quote_source_base_url}/q/?s=lnga.uk",
                "popularity": 0,
                "last_seen_at": None,
            },
            timeout=10.0,
        )

        assert instrument_response.status_code == 201, instrument_response.text
        instrument = instrument_response.json()
        assert instrument["symbol"] == symbol
        assert instrument["mic"] == mic
        assert instrument["currency"] == "USD"
        assert instrument["quote_source"] == f"{quote_source_base_url}/q/?s=lnga.uk"

        resolve_response = httpx.get(
            f"{stock_url}/stock/instruments/resolve",
            params={"mic": mic, "symbol": symbol},
            timeout=10.0,
        )

        assert resolve_response.status_code == 200, resolve_response.text
        resolved = resolve_response.json()
        assert resolved["symbol"] == symbol
        assert resolved["mic"] == mic
        assert resolved["quote_source"] == f"{quote_source_base_url}/q/?s=lnga.uk"

        search_response = httpx.get(
            f"{stock_url}/stock/instruments/search",
            params={"q": isin, "limit": 5},
            timeout=10.0,
        )

        assert search_response.status_code == 200, search_response.text
        search_rows = search_response.json()
        assert search_rows
        assert search_rows[0]["symbol"] == symbol
        assert search_rows[0]["isin"] == isin

        all_markets_response = httpx.get(f"{stock_url}/stock/markets", timeout=10.0)
        assert all_markets_response.status_code == 200, all_markets_response.text
        all_market_mics = {market["mic"] for market in all_markets_response.json()}
        assert mic in all_market_mics
        assert empty_mic in all_market_mics

        quote_markets_response = httpx.get(
            f"{stock_url}/stock/markets",
            params={"only_with_instruments": "true"},
            timeout=10.0,
        )
        assert quote_markets_response.status_code == 200, quote_markets_response.text
        quote_market_mics = {market["mic"] for market in quote_markets_response.json()}
        assert mic in quote_market_mics
        assert empty_mic not in quote_market_mics
