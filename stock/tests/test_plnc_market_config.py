from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, call, patch

import allure
from fastapi import Request
import pytest

from app.api.routes import stock as stock_routes
from app.core.config import settings
from app.core.tasks import tasks_quotes
from app.markerdata.registry import MARKET_INGEST_KEYS, MARKETS
from app.models.enums import InstrumentType


pytestmark = pytest.mark.unit


class _AsyncContext:
    def __init__(self, value) -> None:
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False


@allure.epic("Unit Tests")
@allure.feature("Stock Market Data")
@allure.story("Registered Stooq quote markets use the provider and scheduled ingest")
@allure.severity(allure.severity_level.CRITICAL)
@allure.tag("market-data", "quotes", "stock")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
class PlncMarketConfigTests(unittest.TestCase):
    def test_pln_currency_registry_uses_currency_pair_source(self) -> None:
        cfg = MARKETS["pln_currency"]

        self.assertEqual(cfg.mic, "PLNC")
        self.assertEqual(cfg.instrument_type, InstrumentType.CURRENCY_PAIR)
        self.assertEqual(cfg.start_path, settings.ST_START_PLN_CURRENCY_QUOTE_URL)
        self.assertEqual(cfg.layout.min_cols, 6)
        self.assertIsNone(cfg.layout.volume_col)
        self.assertEqual(cfg.layout.time_col, 5)

    def test_global_indexs_registry_uses_index_source(self) -> None:
        cfg = MARKETS["global_indexs"]

        self.assertEqual(cfg.mic, "GLIX")
        self.assertEqual(cfg.instrument_type, InstrumentType.INDEX)
        self.assertEqual(cfg.start_path, settings.ST_START_PLN_INDEXS_QUOTE_URL)
        self.assertEqual(cfg.layout.min_cols, 6)
        self.assertIsNone(cfg.layout.volume_col)
        self.assertEqual(cfg.layout.time_col, 5)

    def test_scheduled_ingest_includes_stooq_quote_markets(self) -> None:
        self.assertEqual(MARKET_INGEST_KEYS, tuple(MARKETS.keys()))
        self.assertIn("pln_currency", MARKET_INGEST_KEYS)
        self.assertIn("global_indexs", MARKET_INGEST_KEYS)
        self.assertIs(tasks_quotes.MARKET_INGEST_KEYS, MARKET_INGEST_KEYS)

    def test_celery_ingest_runs_every_registered_market(self) -> None:
        session = object()
        storage = object()
        provider = object()
        ingest_market = AsyncMock(side_effect=[1] * len(MARKET_INGEST_KEYS))
        refresh_quote_sources = AsyncMock(return_value={"processed": 2})

        with (
            patch.object(tasks_quotes, "get_provider", return_value=provider),
            patch.object(tasks_quotes, "app_context", return_value=_AsyncContext((session, storage))),
            patch.object(tasks_quotes, "market_lock", side_effect=lambda *_args: _AsyncContext(True)),
            patch.object(tasks_quotes, "ingest_market", ingest_market),
            patch.object(tasks_quotes, "refresh_quote_source_instruments", refresh_quote_sources),
        ):
            result = tasks_quotes.ingest_gpw_quarter.run()

        self.assertEqual(result, len(MARKET_INGEST_KEYS) + 2)
        ingest_market.assert_has_awaits(
            [call(session, provider, market_key, storage) for market_key in MARKET_INGEST_KEYS]
        )
        refresh_quote_sources.assert_awaited_once_with(session, storage)


@allure.epic("Unit Tests")
@allure.feature("Stock Market Data")
@allure.story("Manual quote refresh runs every registered market")
@allure.severity(allure.severity_level.CRITICAL)
@allure.tag("market-data", "quotes", "stock")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
class PlncManualIngestRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_manual_ingest_background_job_runs_every_registered_market(self) -> None:
        stock_storage = SimpleNamespace(
            exists=AsyncMock(return_value=False),
            set=AsyncMock(),
            hmset=AsyncMock(),
            clear=AsyncMock(),
        )
        storage = SimpleNamespace(stock=stock_storage)
        request = Request({"type": "http", "app": SimpleNamespace(storage=storage)})
        session = object()
        provider = object()
        created_tasks = []
        ingest_market = AsyncMock(side_effect=[3] * len(MARKET_INGEST_KEYS))
        refresh_quote_sources = AsyncMock(
            return_value={"processed": 4, "failed": 1, "errors": [{"symbol": "USDPLN"}]}
        )

        def capture_task(coro):
            created_tasks.append(coro)
            return SimpleNamespace()

        with (
            patch.object(stock_routes, "get_provider", return_value=provider),
            patch.object(stock_routes.db, "async_session", return_value=_AsyncContext(session)),
            patch.object(stock_routes, "ingest_market", ingest_market),
            patch.object(stock_routes, "refresh_quote_source_instruments", refresh_quote_sources),
            patch.object(stock_routes.asyncio, "create_task", side_effect=capture_task),
        ):
            response = await stock_routes.start_manual_ingest(request)
            self.assertTrue(response["ok"])
            self.assertEqual(len(created_tasks), 1)
            await created_tasks[0]

        ingest_market.assert_has_awaits(
            [call(session, provider, market_key, storage) for market_key in MARKET_INGEST_KEYS]
        )
        refresh_quote_sources.assert_awaited_once_with(session, storage)
        stock_storage.clear.assert_awaited_once_with("ingest:lock")
        done_payload = stock_storage.hmset.await_args_list[-1].args[1]
        self.assertEqual(done_payload["state"], "done")
        self.assertEqual(done_payload["processed"], len(MARKET_INGEST_KEYS) * 3)
        self.assertEqual(done_payload["quote_source_processed"], 4)
        self.assertEqual(done_payload["quote_source_failed"], 1)
