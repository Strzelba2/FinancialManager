from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
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
from app.api.services.quotes import (
    get_latest_quotes_by_symbols as get_latest_quotes_by_symbols_service,
    sync_daily_by_symbol,
)
from app.crud.quote_latest import get_latest_trade_date_by_symbol, trade_date_in_market_timezone
from app.markerdata.config import MarketConfig, TableLayout
from app.markerdata.historical_browser import (
    build_history_page_url,
    build_quote_page_url,
    extract_symbol,
    requires_browser_fetch,
)
from app.markerdata.mapping import row_to_instrument, row_to_quote_latest
from app.markerdata.parser import historical_url, parse_daily_csv, parse_time_to_utc
from app.markerdata.quote_source_page import (
    normalize_quote_source_url,
    parse_quote_source_page,
    quote_source_fetch_url,
    validate_quote_source_url,
)
from app.markerdata.quote_source_alt import (
    ALT_CHANGE_SELECTOR,
    ALT_PRICE_SELECTOR,
    ALT_TIME_SELECTOR,
    ALT_VOLUME_SELECTOR,
    _alt_symbol_from_url,
    _parse_alt_datetime,
    is_alt_quote_url,
    navigate_alt_quote_source,
    normalize_alt_quote_url,
    parse_alt_quote_source_page,
)
from app.markerdata.scraper import _has_block_marker, _snippet, navigate_quote_source
from app.markerdata.schemas import IndexRow
from app.models.enums import Currency, InstrumentStatus, InstrumentType
from app.schemas.schemas import InstrumentManualCreate
from app.utils.numbers import parse_float_en, parse_int_en, parse_int_pl

pytestmark = pytest.mark.unit

ST_BASE_URL = settings.ST_BASE_URL.rstrip("/")
ST_NETLOC = urlsplit(ST_BASE_URL).netloc
ST_SCHEME_RELATIVE_BASE = f"//{ST_NETLOC}"
QUOTE_SOURCE_URL = f"{ST_BASE_URL}/q/?s=lnga.uk"
QUOTE_SOURCE_CHART_URL = f"{ST_BASE_URL}/q/g/?s=lnga.uk"

ALT_BASE_URL = settings.ST_BASE_URL_ALT.rstrip("/")
ALT_NETLOC = urlsplit(ALT_BASE_URL).netloc
ALT_QUOTE_URL = f"{ALT_BASE_URL}/opm-xpar"


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

    def test_parse_daily_csv_handles_polish_stooq_macro_export_without_volume(self) -> None:
        csv_text = "\n".join(
            [
                "Data,Otwarcie,Najwyzszy,Najnizszy,Zamkniecie",
                "2026-04-30,3.2,3.2,3.2,3.2",
                "2026-05-29,3.1,3.1,3.1,3.1",
            ]
        )

        rows = parse_daily_csv(csv_text)

        self.assertEqual([row.date_quote for row in rows], [date(2026, 4, 30), date(2026, 5, 29)])
        self.assertEqual(rows[-1].close, Decimal("3.10"))
        self.assertIsNone(rows[-1].volume)


@allure.epic("Unit Tests")
@allure.feature("Stock Market Data")
@allure.story("Latest quote trade dates use the market calendar for candle sync")
@allure.severity(allure.severity_level.CRITICAL)
@allure.tag("market-data", "quotes", "stock")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
class QuoteLatestTradeDateTests(unittest.TestCase):
    def test_trade_date_uses_market_timezone_for_date_only_quotes(self) -> None:
        trade_at = datetime(2026, 6, 11, 22, 0, tzinfo=timezone.utc)

        result = trade_date_in_market_timezone(trade_at, "Europe/Warsaw")

        self.assertEqual(result, date(2026, 6, 12))

    def test_trade_date_falls_back_to_utc_for_invalid_market_timezone(self) -> None:
        trade_at = datetime(2026, 6, 11, 22, 0, tzinfo=timezone.utc)

        result = trade_date_in_market_timezone(trade_at, "Not/AZone")

        self.assertEqual(result, date(2026, 6, 11))

    def test_trade_date_treats_naive_timestamps_and_blank_timezone_as_utc(self) -> None:
        trade_at = datetime(2026, 6, 12, 0, 15)

        result = trade_date_in_market_timezone(trade_at, "  ")

        self.assertEqual(result, date(2026, 6, 12))


@allure.epic("Unit Tests")
@allure.feature("Stock Market Data")
@allure.story("Latest quote lookup resolves market-local trade dates for candle sync")
@allure.severity(allure.severity_level.CRITICAL)
@allure.tag("market-data", "quotes", "stock")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
class QuoteLatestCrudTests(unittest.IsolatedAsyncioTestCase):
    async def test_latest_trade_date_by_symbol_returns_none_without_quote_row(self) -> None:
        session = SimpleNamespace(
            execute=AsyncMock(return_value=SimpleNamespace(one_or_none=lambda: None)),
        )

        result = await get_latest_trade_date_by_symbol(session, "PKN")

        self.assertIsNone(result)
        session.execute.assert_awaited_once()

    async def test_latest_trade_date_by_symbol_uses_joined_market_timezone(self) -> None:
        session = SimpleNamespace(
            execute=AsyncMock(
                return_value=SimpleNamespace(
                    one_or_none=lambda: (
                        datetime(2026, 6, 11, 22, 0, tzinfo=timezone.utc),
                        "Europe/Warsaw",
                        "XWAR",
                    ),
                ),
            ),
        )

        result = await get_latest_trade_date_by_symbol(session, "PKN")

        self.assertEqual(result, date(2026, 6, 12))
        session.execute.assert_awaited_once()

    async def test_latest_trade_date_prefers_registry_timezone_for_configured_macro_market(self) -> None:
        session = SimpleNamespace(
            execute=AsyncMock(
                return_value=SimpleNamespace(
                    one_or_none=lambda: (
                        datetime(2026, 5, 28, 22, 0, tzinfo=timezone.utc),
                        "UTC",
                        "MCRO",
                    ),
                ),
            ),
        )

        result = await get_latest_trade_date_by_symbol(session, "CPIYPL.M")

        self.assertEqual(result, date(2026, 5, 29))
        session.execute.assert_awaited_once()

    async def test_latest_quotes_by_symbols_returns_shortname_display_name(self) -> None:
        instrument = SimpleNamespace(
            id=uuid4(),
            symbol="INP",
            shortname="INPRO",
            currency=Currency.PLN,
        )
        quote = SimpleNamespace(
            last_price=Decimal("8.25"),
            change_pct=Decimal("1.50"),
        )

        with patch(
            "app.api.services.quotes.fetch_latest_quotes_by_symbols",
            new=AsyncMock(return_value=[(instrument, SimpleNamespace(mic="XWAR"), quote)]),
        ):
            result = await get_latest_quotes_by_symbols_service(SimpleNamespace(), ["INP"])

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].symbol, "INP")
        self.assertEqual(result[0].name, "INPRO")
        self.assertEqual(result[0].price, Decimal("8.25"))


@allure.epic("Unit Tests")
@allure.feature("Stock Market Data")
@allure.story("Daily candle sync records the actual upstream candle range")
@allure.severity(allure.severity_level.CRITICAL)
@allure.tag("market-data", "candles", "sync", "stock")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
class DailyCandleSyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_sync_success_end_uses_latest_returned_candle_when_upstream_lags_target(self) -> None:
        instrument_id = uuid4()
        session = SimpleNamespace()
        instrument = SimpleNamespace(
            id=instrument_id,
            shortname="POLSKA",
            historical_source="https://stooq.pl/q/d/l/?s=cpiypl.m&i=d",
        )
        state = SimpleNamespace(
            daily_last_success_end=None,
            daily_last_fetched_rows=None,
            daily_last_attempt_end=None,
            daily_last_attempt_at=None,
            daily_last_error=None,
        )
        csv_text = "\n".join(
            [
                "Data,Otwarcie,Najwyzszy,Najnizszy,Zamkniecie",
                "2026-03-31,3,3,3,3",
                "2026-04-30,3.2,3.2,3.2,3.2",
            ]
        )

        with (
            patch("app.api.services.quotes.get_instrument_by_symbol", new=AsyncMock(return_value=instrument)),
            patch("app.api.services.quotes.get_latest_trade_date_by_symbol", new=AsyncMock(return_value=date(2026, 5, 29))),
            patch("app.api.services.quotes.get_min_max_date", new=AsyncMock(return_value=(date(2025, 1, 31), date(2026, 3, 31)))),
            patch("app.api.services.quotes.requires_browser_fetch", return_value=False),
            patch("app.api.services.quotes.download_text_csv", new=AsyncMock(return_value=csv_text)) as download_csv,
            patch("app.api.services.quotes.get_or_create_sync_state", new=AsyncMock(return_value=state)),
            patch("app.api.services.quotes.mark_daily_attempt", new=AsyncMock()) as mark_attempt,
            patch("app.api.services.quotes.mark_daily_success", new=AsyncMock()) as mark_success,
            patch("app.api.services.quotes._upsert_daily_row_batches", new=AsyncMock(return_value=2)),
        ):
            result = await sync_daily_by_symbol(session, "CPIYPL.M", overlap_days=7)

        self.assertEqual(result.sync_end, date(2026, 4, 30))
        mark_attempt.assert_awaited_once()
        mark_success.assert_awaited_once()
        requested_url = download_csv.await_args.kwargs["url"]
        self.assertIn("d1=20260324", requested_url)
        self.assertIn("d2=20260529", requested_url)
        self.assertEqual(mark_success.await_args.kwargs["target_end"], date(2026, 4, 30))


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


@allure.epic("Unit Tests")
@allure.feature("Stock Market Data")
@allure.story("quote_source URL helpers normalise and validate manual instrument URLs")
@allure.severity(allure.severity_level.CRITICAL)
@allure.tag("market-data", "quote-source", "stock")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
class QuoteSourceParserTests(unittest.TestCase):
    def test_manual_instrument_schema_accepts_quote_source(self) -> None:
        payload = InstrumentManualCreate(
            market_mic="XLON",
            symbol="lnga.uk",
            shortname="lnga.uk",
            name="WisdomTree Natural Gas",
            type=InstrumentType.ETF,
            status=InstrumentStatus.ACTIVE,
            historical_source=None,
            quote_source=QUOTE_SOURCE_URL,
            popularity=0,
            last_seen_at=None,
            currency=Currency.USD,
        )

        self.assertEqual(payload.symbol, "LNGA.UK")
        self.assertEqual(str(payload.quote_source), QUOTE_SOURCE_URL)

    def test_rejects_invalid_quote_source_url(self) -> None:
        with self.assertRaisesRegex(ValueError, "allowed"):
            validate_quote_source_url("https://example.com/q/?s=lnga.uk")

    def test_normalizes_provider_historical_url_to_quote_page(self) -> None:
        result = normalize_quote_source_url(f"{ST_BASE_URL}/q/d/l/?s=lnga.uk&i=d")

        self.assertEqual(result, QUOTE_SOURCE_URL)

    def test_normalizes_provider_chart_url_to_quote_page(self) -> None:
        result = normalize_quote_source_url(QUOTE_SOURCE_CHART_URL)

        self.assertEqual(result, QUOTE_SOURCE_URL)

    def test_fetch_url_preserves_chart_page_but_converts_historical_download(self) -> None:
        self.assertEqual(quote_source_fetch_url(QUOTE_SOURCE_CHART_URL), QUOTE_SOURCE_CHART_URL)
        self.assertEqual(
            quote_source_fetch_url(f"{ST_BASE_URL}/q/d/l/?s=lnga.uk&i=d"),
            QUOTE_SOURCE_URL,
        )


class _FakeQuoteLocator:
    def __init__(self, text: str | None = None) -> None:
        self._text = text

    @property
    def first(self) -> "_FakeQuoteLocator":
        return self

    async def count(self) -> int:
        return 1 if self._text else 0

    async def inner_text(self) -> str:
        return self._text or ""


class _FakeQuotePage:
    def __init__(self, rows: list[list[str]], selectors: dict[str, str | None] | None = None) -> None:
        self._rows = rows
        self._selectors = selectors or {}

    async def evaluate(self, _script: str) -> list[list[str]]:
        return self._rows

    def locator(self, selector: str) -> _FakeQuoteLocator:
        return _FakeQuoteLocator(self._selectors.get(selector))


@allure.epic("Unit Tests")
@allure.feature("Stock Market Data")
@allure.story("quote_source page parser reads provider table rows without live network")
@allure.severity(allure.severity_level.CRITICAL)
@allure.tag("market-data", "quote-source", "stock", "parsing")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
class QuoteSourcePageParserTests(unittest.IsolatedAsyncioTestCase):
    async def test_provider_table_skips_currency_cell_after_price_label(self) -> None:
        page = _FakeQuotePage([
            ["Kurs", "$", "0.01655"],
            ["Zmiana", "-0.00105", "(-5.97%)"],
            ["Wolumen", "752,979"],
            ["Data", "16:35"],
        ])

        result = await parse_quote_source_page(page, QUOTE_SOURCE_URL)

        self.assertEqual(result.symbol, "LNGA.UK")
        self.assertEqual(result.last_price, Decimal("0.017"))
        self.assertEqual(result.change_pct, Decimal("-5.970"))
        self.assertEqual(result.volume, 752979)

    async def test_provider_table_uses_percent_from_combined_change_cell(self) -> None:
        page = _FakeQuotePage([
            ["Kurs", "17.16 €"],
            ["Zmiana", "+0.08 (+0.47%)"],
            ["Zmiana 52t", "+6.02 (54.04%)"],
            ["Wolumen", "882"],
            ["Data", "17:30"],
        ])

        result = await parse_quote_source_page(page, f"{ST_BASE_URL}/q/?s=un9.de")

        self.assertEqual(result.symbol, "UN9.DE")
        self.assertEqual(result.last_price, Decimal("17.160"))
        self.assertEqual(result.change_pct, Decimal("0.470"))
        self.assertEqual(result.volume, 882)

    async def test_provider_table_missing_price_returns_controlled_error(self) -> None:
        page = _FakeQuotePage([
            ["Wolumen", "752,979"],
            ["Data", "16:35"],
        ])

        with self.assertRaisesRegex(ValueError, "last price"):
            await parse_quote_source_page(page, QUOTE_SOURCE_URL)


_ALT_FULL_VALUES = {
    ALT_PRICE_SELECTOR: "15.62",
    ALT_CHANGE_SELECTOR: "-3.78%",
    ALT_VOLUME_SELECTOR: "76,944.00",
    ALT_TIME_SELECTOR: "15:55:00",
}


class _FakeAltLocator:
    """Minimal stand-in for a Playwright locator used by ``_alt_text``."""

    def __init__(self, text: str | None) -> None:
        self._text = text

    @property
    def first(self) -> "_FakeAltLocator":
        return self

    async def count(self) -> int:
        return 1 if self._text is not None else 0

    async def inner_text(self) -> str:
        return self._text or ""


class _FakeAltPage:
    """Fake Playwright page returning canned inner text per selector."""

    def __init__(self, values: dict[str, str | None]) -> None:
        self._values = values

    def locator(self, selector: str) -> _FakeAltLocator:
        return _FakeAltLocator(self._values.get(selector))


@allure.epic("Unit Tests")
@allure.feature("Stock Equity Reports")
@allure.story("Alternative quote source URL helpers and EN number parsing")
@allure.severity(allure.severity_level.CRITICAL)
@allure.tag("market-data", "quote-source", "stock")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
class AltQuoteSourceParserTests(unittest.TestCase):
    def test_is_alt_quote_url_matches_only_alt_host(self) -> None:
        self.assertTrue(is_alt_quote_url(ALT_QUOTE_URL))
        self.assertFalse(is_alt_quote_url(QUOTE_SOURCE_URL))
        self.assertFalse(is_alt_quote_url(""))

    def test_normalize_alt_quote_url_strips_query_and_trailing_slash(self) -> None:
        result = normalize_alt_quote_url(f"{ALT_QUOTE_URL}/?foo=bar#frag")

        self.assertEqual(result, ALT_QUOTE_URL)

    def test_normalize_alt_quote_url_rejects_foreign_host(self) -> None:
        with self.assertRaisesRegex(ValueError, "allowed list"):
            normalize_alt_quote_url("https://example.com/markets/stocks/opm-xpar")

    def test_normalize_alt_quote_url_rejects_section_root(self) -> None:
        with self.assertRaisesRegex(ValueError, "allowed section"):
            normalize_alt_quote_url(ALT_BASE_URL)

    def test_normalize_alt_quote_url_rejects_bare_host(self) -> None:
        with self.assertRaisesRegex(ValueError, "instrument page"):
            normalize_alt_quote_url(f"https://{ALT_NETLOC}")

    def test_normalize_alt_quote_url_rejects_non_http_scheme(self) -> None:
        with self.assertRaisesRegex(ValueError, "http"):
            normalize_alt_quote_url(f"ftp://{ALT_NETLOC}/markets/stocks/opm-xpar")

    def test_alt_symbol_is_last_path_segment_uppercased(self) -> None:
        self.assertEqual(_alt_symbol_from_url(ALT_QUOTE_URL), "OPM-XPAR")

    def test_alt_symbol_rejects_url_without_path_segments(self) -> None:
        with self.assertRaisesRegex(ValueError, "path segment"):
            _alt_symbol_from_url(f"https://{ALT_NETLOC}")

    def test_parse_alt_datetime_accepts_full_dates_and_falls_back_to_now(self) -> None:
        self.assertEqual(
            _parse_alt_datetime("2026-06-07 15:55:00").tzinfo,
            timezone.utc,
        )
        self.assertEqual(
            _parse_alt_datetime("07/06/2026 15:55").tzinfo,
            timezone.utc,
        )
        self.assertEqual(_parse_alt_datetime("99:99").tzinfo, timezone.utc)

    def test_parse_float_en_handles_us_formatting(self) -> None:
        self.assertEqual(parse_float_en("15.62"), 15.62)
        self.assertEqual(parse_float_en("76,738.00"), 76738.0)
        self.assertEqual(parse_float_en("+1.20%"), 1.2)
        self.assertEqual(parse_float_en("-3.78%"), -3.78)
        self.assertIsNone(parse_float_en(""))
        self.assertIsNone(parse_float_en(None))

    def test_parse_int_en_truncates_and_beats_pl_parser_on_us_volume(self) -> None:
        self.assertEqual(parse_int_en("76,738.00"), 76738)
        self.assertEqual(parse_int_en("1,234.99"), 1234)
        self.assertIsNone(parse_int_en(""))
        self.assertEqual(parse_int_pl("76,738.00"), 7673800)


@allure.epic("Unit Tests")
@allure.feature("Stock Equity Reports")
@allure.story("Alternative quote source page parsing from a live page")
@allure.severity(allure.severity_level.CRITICAL)
@allure.tag("market-data", "quote-source", "stock")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
class AltQuoteSourcePageParseTests(unittest.IsolatedAsyncioTestCase):
    async def test_parses_price_change_volume_and_timestamp(self) -> None:
        page = _FakeAltPage(dict(_ALT_FULL_VALUES))

        result = await parse_alt_quote_source_page(page, ALT_QUOTE_URL)

        self.assertEqual(result.symbol, "OPM-XPAR")
        self.assertEqual(result.source_url, ALT_QUOTE_URL)
        self.assertEqual(result.last_price, Decimal("15.620"))
        self.assertEqual(result.change_pct, Decimal("-3.780"))
        self.assertEqual(result.volume, 76944)
        self.assertEqual(result.last_trade_at.tzinfo, timezone.utc)

    async def test_defaults_change_to_zero_and_timestamp_to_now(self) -> None:
        page = _FakeAltPage({ALT_PRICE_SELECTOR: "15.62"})

        result = await parse_alt_quote_source_page(page, ALT_QUOTE_URL)

        self.assertEqual(result.change_pct, Decimal("0.000"))
        self.assertIsNone(result.volume)
        self.assertEqual(result.last_trade_at.tzinfo, timezone.utc)
        self.assertEqual(
            result.last_trade_at.date(), datetime.now(timezone.utc).date()
        )

    async def test_raises_when_price_is_missing(self) -> None:
        page = _FakeAltPage({ALT_CHANGE_SELECTOR: "-3.78%"})

        with self.assertRaisesRegex(ValueError, "last price"):
            await parse_alt_quote_source_page(page, ALT_QUOTE_URL)


class _ClickableLocator:
    def __init__(self, count: int = 1, text: str = "") -> None:
        self._count = count
        self._text = text
        self.clicked = False

    @property
    def first(self) -> "_ClickableLocator":
        return self

    async def count(self) -> int:
        return self._count

    async def click(self, timeout: int | None = None) -> None:
        self.clicked = True

    async def inner_text(self) -> str:
        return self._text


class _FakeBrowserPage:
    def __init__(self, *, body: str = "Kurs 15.62", ok: bool = True) -> None:
        self.body = body
        self.ok = ok
        self.accept = _ClickableLocator()
        self.disclaimer = _ClickableLocator()
        self.waited_for_function = False

    async def goto(self, url: str, wait_until: str = "domcontentloaded"):
        return SimpleNamespace(ok=self.ok, status=503)

    async def wait_for_load_state(self, state: str, timeout: int) -> None:
        return None

    async def wait_for_selector(self, selector: str, state: str = "visible", timeout: int = 0) -> None:
        return None

    async def wait_for_function(self, script: str, arg: str, timeout: int) -> None:
        self.waited_for_function = True

    def get_by_role(self, role: str, name):
        return self.accept

    def locator(self, selector: str):
        if selector == "body":
            return _ClickableLocator(text=self.body)
        if selector == 'button[data-ref="disclaimer__update-btn"]':
            return self.disclaimer
        return _ClickableLocator()


@allure.epic("Unit Tests")
@allure.feature("Stock Equity Reports")
@allure.story("Quote source browser navigation detects blocking pages and consent flows")
@allure.severity(allure.severity_level.CRITICAL)
@allure.tag("market-data", "quote-source", "browser", "stock")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
class QuoteSourceBrowserNavigationTests(unittest.IsolatedAsyncioTestCase):
    async def test_standard_quote_source_navigation_detects_blocked_page(self) -> None:
        page = _FakeBrowserPage(body="captcha Dane zostały ukryte")

        self.assertTrue(_has_block_marker(page.body))
        self.assertEqual(_snippet(" a \n\n b ", limit=10), "a b")
        with self.assertRaisesRegex(RuntimeError, "blocked"):
            await navigate_quote_source(QUOTE_SOURCE_URL, page, fetch_nr=0)

    async def test_standard_quote_source_navigation_accepts_unblocked_page(self) -> None:
        page = _FakeBrowserPage(body="Kurs 15.62")

        await navigate_quote_source(QUOTE_SOURCE_URL, page, fetch_nr=1)

        self.assertFalse(_has_block_marker(page.body))

    async def test_alt_quote_source_navigation_dismisses_consent_and_waits_for_price(self) -> None:
        page = _FakeBrowserPage(body="15.62")

        await navigate_alt_quote_source(ALT_QUOTE_URL, page, consent_needed=True)

        self.assertTrue(page.accept.clicked)
        self.assertTrue(page.disclaimer.clicked)
        self.assertTrue(page.waited_for_function)

    async def test_alt_quote_source_navigation_rejects_http_error(self) -> None:
        page = _FakeBrowserPage(ok=False)

        with self.assertRaisesRegex(RuntimeError, "HTTP 503"):
            await navigate_alt_quote_source(ALT_QUOTE_URL, page, consent_needed=False)
