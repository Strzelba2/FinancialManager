from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4
import unittest

import allure
import pytest
from fastapi import HTTPException

from app.api.routes import instrument as instrument_routes
from app.api.services.instrument_sync import synchronize_instrument_name
from app.clients.stock_client import StockInstrumentUpdateError
from app.schemas.response import InstrumentNameSyncResponse, StockInstrumentRead
from app.schemas.schemas import InstrumentNameSyncRequest


pytestmark = pytest.mark.unit


class _Begin:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _session(existing=None, flush_side_effect=None) -> Mock:
    session = Mock()
    session.execute = AsyncMock(
        return_value=SimpleNamespace(scalar_one_or_none=lambda: existing),
    )
    session.add = Mock()
    session.flush = AsyncMock(side_effect=flush_side_effect)
    session.begin = Mock(return_value=_Begin())
    return session


def _stock_instrument(shortname: str) -> StockInstrumentRead:
    return StockInstrumentRead(
        mic="XWAR",
        symbol="PKO",
        shortname=shortname,
        name="POWSZECHNA KASA OSZCZEDNOSCI BANK POLSKI SA",
        currency="PLN",
        type="STOCK",
        status="ACTIVE",
    )


def _stock_client(update_side_effect=None) -> Mock:
    client = Mock()
    client.resolve_instrument = AsyncMock(return_value=_stock_instrument("PKO"))
    client.update_instrument_shortname = AsyncMock(
        return_value=_stock_instrument("PKO BP SA"),
        side_effect=update_side_effect,
    )
    return client


@allure.epic("Unit Tests")
@allure.feature("Wallet")
@allure.story("Wallet keeps its instrument mirror synchronized with stock display names")
@allure.severity(allure.severity_level.CRITICAL)
@allure.tag("wallet", "stock", "financial-data", "api-contract")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
@allure.description(
    "Verifies existing and missing wallet mirrors, MIC conflicts, stock failures, "
    "and compensating updates without changing holdings or money state."
)
class InstrumentNameSynchronizationTests(unittest.IsolatedAsyncioTestCase):
    async def test_updates_existing_wallet_name_from_normalized_stock_response(self) -> None:
        instrument = SimpleNamespace(symbol="PKO", mic="XWAR", name="PKO")
        session = _session(instrument)
        stock_client = _stock_client()

        result = await synchronize_instrument_name(
            session=session,
            stock_client=stock_client,
            mic="XWAR",
            symbol="PKO",
            name="Pko bp sa",
        )

        self.assertEqual(instrument.name, "PKO BP SA")
        self.assertFalse(result.created)
        self.assertEqual(result.name, "PKO BP SA")
        stock_client.update_instrument_shortname.assert_awaited_once_with(
            mic="XWAR",
            symbol="PKO",
            shortname="Pko bp sa",
            expected_shortname="PKO",
        )

    async def test_creates_missing_wallet_mirror_from_stock_metadata(self) -> None:
        session = _session()
        stock_client = _stock_client()

        result = await synchronize_instrument_name(
            session=session,
            stock_client=stock_client,
            mic="XWAR",
            symbol="PKO",
            name="PKO BP SA",
        )

        self.assertTrue(result.created)
        session.add.assert_called_once()
        created = session.add.call_args.args[0]
        self.assertEqual(created.symbol, "PKO")
        self.assertEqual(created.mic, "XWAR")
        self.assertEqual(created.name, "PKO BP SA")
        self.assertEqual(created.currency.value, "PLN")
        self.assertEqual(created.type.value, "STOCK")

    async def test_rejects_existing_symbol_for_another_mic_without_stock_write(self) -> None:
        instrument = SimpleNamespace(symbol="PKO", mic="XLON", name="PKO")
        session = _session(instrument)
        stock_client = _stock_client()

        with self.assertRaises(HTTPException) as captured:
            await synchronize_instrument_name(session, stock_client, "XWAR", "PKO", "PKO BP SA")

        self.assertEqual(captured.exception.status_code, 409)
        stock_client.update_instrument_shortname.assert_not_awaited()

    async def test_stock_conflict_leaves_wallet_name_unchanged(self) -> None:
        instrument = SimpleNamespace(symbol="PKO", mic="XWAR", name="PKO")
        session = _session(instrument)
        stock_client = _stock_client(StockInstrumentUpdateError(409, "concurrent update"))

        with self.assertRaises(HTTPException) as captured:
            await synchronize_instrument_name(session, stock_client, "XWAR", "PKO", "PKO BP SA")

        self.assertEqual(captured.exception.status_code, 409)
        self.assertEqual(instrument.name, "PKO")

    async def test_ambiguous_stock_failure_reconciles_a_committed_remote_update(self) -> None:
        instrument = SimpleNamespace(symbol="PKO", mic="XWAR", name="PKO")
        session = _session(instrument)
        stock_client = _stock_client(StockInstrumentUpdateError(503, "response lost"))
        stock_client.resolve_instrument = AsyncMock(side_effect=[
            _stock_instrument("PKO"),
            _stock_instrument("PKO BP SA"),
        ])

        result = await synchronize_instrument_name(
            session,
            stock_client,
            "XWAR",
            "PKO",
            "Pko bp sa",
        )

        self.assertEqual(result.name, "PKO BP SA")
        self.assertEqual(instrument.name, "PKO BP SA")
        self.assertEqual(stock_client.resolve_instrument.await_count, 2)

    async def test_wallet_failure_compensates_stock_to_previous_name(self) -> None:
        instrument = SimpleNamespace(symbol="PKO", mic="XWAR", name="PKO")
        session = _session(instrument, RuntimeError("wallet flush failed"))
        stock_client = _stock_client([
            _stock_instrument("PKO BP SA"),
            _stock_instrument("PKO"),
        ])

        with self.assertRaises(HTTPException) as captured:
            await synchronize_instrument_name(session, stock_client, "XWAR", "PKO", "PKO BP SA")

        self.assertEqual(captured.exception.status_code, 500)
        self.assertEqual(stock_client.update_instrument_shortname.await_count, 2)
        compensation = stock_client.update_instrument_shortname.await_args_list[1].kwargs
        self.assertEqual(compensation["shortname"], "PKO")
        self.assertEqual(compensation["expected_shortname"], "PKO BP SA")

    async def test_failed_stock_compensation_returns_explicit_consistency_error(self) -> None:
        instrument = SimpleNamespace(symbol="PKO", mic="XWAR", name="PKO")
        session = _session(instrument, RuntimeError("wallet flush failed"))
        stock_client = _stock_client([
            _stock_instrument("PKO BP SA"),
            StockInstrumentUpdateError(409, "compensation conflict"),
        ])

        with self.assertRaises(HTTPException) as captured:
            await synchronize_instrument_name(session, stock_client, "XWAR", "PKO", "PKO BP SA")

        self.assertEqual(captured.exception.status_code, 500)
        self.assertIn("compensation was unsuccessful", captured.exception.detail)


@allure.epic("Unit Tests")
@allure.feature("Wallet")
@allure.story("Instrument name route delegates authenticated synchronization requests")
@allure.severity(allure.severity_level.CRITICAL)
@allure.tag("wallet", "stock", "financial-data", "api-contract", "auth")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
class InstrumentNameRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_route_delegates_payload_and_returns_sync_response(self) -> None:
        user_id = uuid4()
        session = Mock()
        stock_client = Mock()
        payload = InstrumentNameSyncRequest(mic="xwar", name=" PKO BP SA ")
        expected = InstrumentNameSyncResponse(
            symbol="PKO",
            mic="XWAR",
            name="PKO BP SA",
            created=True,
        )

        with patch(
            "app.api.routes.instrument.synchronize_instrument_name",
            new=AsyncMock(return_value=expected),
        ) as synchronize_mock:
            result = await instrument_routes.api_synchronize_instrument_name(
                symbol="PKO",
                payload=payload,
                _user_id=user_id,
                session=session,
                stock_client=stock_client,
            )

        self.assertIs(result, expected)
        synchronize_mock.assert_awaited_once_with(
            session=session,
            stock_client=stock_client,
            mic="XWAR",
            symbol="PKO",
            name="PKO BP SA",
        )

    async def test_route_preserves_coordinator_http_error(self) -> None:
        user_id = uuid4()
        session = Mock()
        stock_client = Mock()
        payload = InstrumentNameSyncRequest(mic="XWAR", name="PKO BP SA")
        conflict = HTTPException(status_code=409, detail="Instrument shortname changed concurrently.")

        with patch(
            "app.api.routes.instrument.synchronize_instrument_name",
            new=AsyncMock(side_effect=conflict),
        ) as synchronize_mock:
            with self.assertRaises(HTTPException) as captured:
                await instrument_routes.api_synchronize_instrument_name(
                    symbol="PKO",
                    payload=payload,
                    _user_id=user_id,
                    session=session,
                    stock_client=stock_client,
                )

        self.assertIs(captured.exception, conflict)
        self.assertEqual(captured.exception.status_code, 409)
        self.assertEqual(captured.exception.detail, "Instrument shortname changed concurrently.")
        synchronize_mock.assert_awaited_once_with(
            session=session,
            stock_client=stock_client,
            mic="XWAR",
            symbol="PKO",
            name="PKO BP SA",
        )
