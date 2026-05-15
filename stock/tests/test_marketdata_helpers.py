from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch
from urllib.parse import urlsplit
from uuid import uuid4
from zoneinfo import ZoneInfo
import unittest

import allure
import httpx
import pandas as pd
import pytest

from app.core.config import settings
from app.core.clients.gpw_client import GpwListingsClient
from app.markerdata.config import MarketConfig, TableLayout
from app.markerdata.historical_browser import (
    build_history_page_url,
    build_quote_page_url,
    extract_symbol,
    requires_browser_fetch,
)
from app.markerdata.mapping import row_to_instrument, row_to_quote_latest
from app.markerdata.parser import historical_url, parse_daily_csv, parse_time_to_utc
from app.markerdata.schemas import IndexRow
from app.models.enums import InstrumentType

pytestmark = pytest.mark.unit

ST_BASE_URL = settings.ST_BASE_URL.rstrip("/")
ST_NETLOC = urlsplit(ST_BASE_URL).netloc
ST_SCHEME_RELATIVE_BASE = f"//{ST_NETLOC}"


def _market_config() -> MarketConfig:
    return MarketConfig(
        id="configured-wse",
        base_url=ST_BASE_URL,
        start_path="/t/?i=513",
        mic="XWAR",
        instrument_type=InstrumentType.STOCK,
        layout=TableLayout(min_cols=7),
    )


@allure.epic("Unit Tests")
@allure.feature("Stock Equity Reports")
@allure.story("Market data parser handles dates, CSV, and historical URLs")
@allure.severity(allure.severity_level.CRITICAL)
@allure.tag("market-data", "parsing", "stock")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
class MarketDataParserTests(unittest.TestCase):
    def test_parse_time_to_utc_converts_time_only_using_market_timezone(self) -> None:
        result = parse_time_to_utc("10:45", page_dt=date(2026, 5, 4), tz=ZoneInfo("Europe/Warsaw"))

        self.assertEqual(result, datetime(2026, 5, 4, 8, 45, tzinfo=timezone.utc))

    def test_parse_time_to_utc_converts_polish_month_names_and_rejects_invalid_text(self) -> None:
        result = parse_time_to_utc("12 stycznia", page_dt=date(2026, 2, 1), tz=ZoneInfo("Europe/Warsaw"))

        self.assertEqual(result, datetime(2026, 1, 11, 23, 0, tzinfo=timezone.utc))
        self.assertIsNone(parse_time_to_utc("not-a-date", page_dt=date(2026, 2, 1)))
        self.assertIsNone(parse_time_to_utc(""))

    def test_historical_url_extracts_symbol_from_relative_or_absolute_quote_href(self) -> None:
        cfg = _market_config()

        self.assertEqual(
            historical_url("/q/?s=PKO&amp;c=1", cfg),
            f"{ST_BASE_URL}/q/d/l/?s=PKO&i=d",
        )
        self.assertEqual(
            historical_url(f"{ST_BASE_URL}/q/?S=PEO", cfg, interval="w"),
            f"{ST_BASE_URL}/q/d/l/?s=PEO&i=w",
        )

        with self.assertRaisesRegex(ValueError, "quote_href is empty"):
            historical_url("", cfg)
        with self.assertRaisesRegex(ValueError, "Could not find 's'"):
            historical_url("/q/?c=1", cfg)

    def test_parse_daily_csv_handles_semicolon_comma_and_malformed_rows(self) -> None:
        csv_text = "\n".join(
            [
                "Date;Open;High;Low;Close;Volume",
                "2026-05-02;11,20;12,00;10,50;11,80;1000",
                "bad-row;1;2;3;4;5",
                "2026-05-01;10.00;11.00;9.50;10.50;",
            ]
        )

        rows = parse_daily_csv(csv_text)

        self.assertEqual([row.date_quote for row in rows], [date(2026, 5, 1), date(2026, 5, 2)])
        self.assertEqual(rows[0].close, Decimal("10.50"))
        self.assertEqual(rows[0].volume, None)
        self.assertEqual(rows[1].volume, 1000)


@allure.epic("Unit Tests")
@allure.feature("Stock Equity Reports")
@allure.story("Market data mapping converts parsed rows to service schemas")
@allure.severity(allure.severity_level.CRITICAL)
@allure.tag("market-data", "mapping", "stock")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
class MarketDataMappingTests(unittest.TestCase):
    def test_row_to_instrument_truncates_names_and_builds_historical_source(self) -> None:
        row = IndexRow(
            symbol="PEKABEX-LONG",
            name="Pekabex Long Name",
            href="/q/?s=PBX",
            provider=ST_BASE_URL,
        )
        market_id = uuid4()

        result = row_to_instrument(row, _market_config(), market_id)

        self.assertEqual(result.market_id, market_id)
        self.assertEqual(result.symbol, "PEKABEX-LONG")
        self.assertEqual(result.shortname, "PEKABEX LONG")
        self.assertEqual(str(result.historical_source), f"{ST_BASE_URL}/q/d/l/?s=PBX&i=d")
        self.assertEqual(result.type, InstrumentType.STOCK)

    def test_row_to_quote_latest_defaults_missing_values_and_preserves_source(self) -> None:
        row = IndexRow(
            symbol="PKO",
            name="PKO BP",
            last_price=None,
            change_pct=None,
            volume=10,
            href=f"{ST_BASE_URL}/q/?s=PKO",
            provider=ST_BASE_URL,
        )

        result = row_to_quote_latest(row)

        self.assertEqual(result.last_price, Decimal("0.00"))
        self.assertEqual(result.change_pct, Decimal("0.00"))
        self.assertEqual(result.volume, 10)
        self.assertEqual(str(result.provider), f"{ST_BASE_URL}/")
        self.assertEqual(result.href, f"{ST_BASE_URL}/q/?s=PKO")


@allure.epic("Unit Tests")
@allure.feature("Stock Equity Reports")
@allure.story("Historical browser helpers build supported quote and history URLs")
@allure.severity(allure.severity_level.NORMAL)
@allure.tag("market-data", "browser", "stock")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
class HistoricalBrowserHelperTests(unittest.TestCase):
    def test_browser_fetch_is_required_only_for_daily_market_download_urls(self) -> None:
        self.assertTrue(requires_browser_fetch(f"{ST_BASE_URL}/q/d/l/?s=PKO&i=d"))
        self.assertFalse(requires_browser_fetch(f"{ST_BASE_URL}/q/?s=PKO"))
        self.assertFalse(requires_browser_fetch(f"{ST_BASE_URL}/q/d/l/?i=d"))

    def test_symbol_extraction_and_page_urls_are_normalized(self) -> None:
        source = f"{ST_SCHEME_RELATIVE_BASE}/q/d/l/?S=PKO&i=d"

        self.assertEqual(extract_symbol(source), "PKO")
        self.assertEqual(build_quote_page_url(source), f"https://{ST_NETLOC}/q/?s=PKO")
        self.assertEqual(build_history_page_url(source), f"https://{ST_NETLOC}/q/d/?s=PKO")

        with self.assertRaisesRegex(ValueError, "Could not determine symbol"):
            extract_symbol(f"{ST_BASE_URL}/q/d/l/?i=d")


class _FakeHttpClient:
    def __init__(self, text: str = "<table></table>") -> None:
        self.text = text
        self.requested_urls: list[str] = []

    async def get(self, url: str) -> httpx.Response:
        self.requested_urls.append(url)
        return httpx.Response(200, text=self.text, request=httpx.Request("GET", url))

    async def aclose(self) -> None:
        pass


@allure.epic("Unit Tests")
@allure.feature("Stock Equity Reports")
@allure.story("GPW listings client normalizes tabular provider data without live network")
@allure.severity(allure.severity_level.CRITICAL)
@allure.tag("market-data", "client", "stock")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
class GpwListingsClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_subset_columns_keeps_known_columns_and_strips_text(self) -> None:
        client = GpwListingsClient()
        self.addAsyncCleanup(client.aclose)
        df = pd.DataFrame(
            [
                {
                    "Name": " PKO BP ",
                    "Shortcut": " PKO ",
                    "ISIN": " PLPKO0000016 ",
                    "Last / Closing": "55.12",
                    "% change": "1.20%",
                    "Cumulated volume": "1000",
                    "Last transaction time": "10:45",
                    "Noise": "ignored",
                }
            ]
        )

        result = client._subset_columns(df)

        self.assertEqual(list(result.columns), [
            "Name",
            "Shortcut",
            "ISIN",
            "Last / Closing",
            "% change",
            "Cumulated volume",
            "Last transaction time",
        ])
        self.assertEqual(result.iloc[0]["Name"], "PKO BP")
        self.assertEqual(result.iloc[0]["Shortcut"], "PKO")

    async def test_fetch_and_normalize_table_renames_provider_columns(self) -> None:
        client = GpwListingsClient()
        fake_http = _FakeHttpClient()
        client._client = fake_http
        self.addAsyncCleanup(client.aclose)
        raw_df = pd.DataFrame(
            [
                {
                    "Abbreviation": "PKO",
                    "Time of last trans.": "10:45",
                    "Last trans. price": "55.12",
                    "Change v. ref. price": "1.20%",
                    "Aggr. trade vol.": "1000",
                    "Unnamed: 0": "1",
                }
            ]
        )

        with patch("app.core.clients.gpw_client.pd.read_html", return_value=[raw_df]):
            result = await client._fetch_and_normalize_table("https://gpw.pl", "/akcje")

        self.assertEqual(fake_http.requested_urls, ["https://gpw.pl/akcje"])
        self.assertIn("Shortcut", result.columns)
        self.assertIn("Last transaction time", result.columns)
        self.assertIn("Last / Closing", result.columns)
        self.assertIn("% change", result.columns)
        self.assertIn("Cumulated volume", result.columns)
        self.assertIn("idx", result.columns)

    async def test_fetch_and_normalize_table_rejects_missing_tables(self) -> None:
        client = GpwListingsClient()
        client._client = _FakeHttpClient()
        self.addAsyncCleanup(client.aclose)

        with patch("app.core.clients.gpw_client.pd.read_html", return_value=[]):
            with self.assertRaisesRegex(RuntimeError, "No tables found"):
                await client._fetch_and_normalize_table("https://gpw.pl", "/akcje")

    async def test_symbol_map_filters_records_by_mic(self) -> None:
        client = GpwListingsClient()
        client.get_gpw_records = AsyncMock(return_value=[{"Shortcut": "PKO"}, {"Shortcut": ""}])
        client.get_newconnect_records = AsyncMock(return_value=[{"Shortcut": "MLG"}])
        self.addAsyncCleanup(client.aclose)

        gpw_map = await client.get_symbol_map("XWAR")
        nc_map = await client.get_symbol_map("XNCO")
        all_map = await client.get_symbol_map(None)

        self.assertEqual(gpw_map, {"PKO": {"Shortcut": "PKO"}})
        self.assertEqual(nc_map, {"MLG": {"Shortcut": "MLG"}})
        self.assertEqual(all_map, {"PKO": {"Shortcut": "PKO"}, "MLG": {"Shortcut": "MLG"}})
