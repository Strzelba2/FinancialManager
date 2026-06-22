from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
import unittest

import allure
import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from app.api.routes import stock as stock_routes
from app.crud.instrument import update_instrument_shortname
from app.schemas.schemas import InstrumentShortnameUpdate


pytestmark = pytest.mark.unit


class _Begin:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _session(row=None, flush_error: Exception | None = None) -> Mock:
    session = Mock()
    session.execute = AsyncMock(return_value=SimpleNamespace(first=lambda: row))
    session.flush = AsyncMock(side_effect=flush_error)
    session.begin = Mock(return_value=_Begin())
    return session


@allure.epic("Unit Tests")
@allure.feature("Stock")
@allure.story("Instrument display names use validated optimistic updates")
@allure.severity(allure.severity_level.NORMAL)
@allure.tag("stock", "financial-data", "api-contract")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
class InstrumentNameUpdateTests(unittest.IsolatedAsyncioTestCase):
    async def test_crud_updates_only_shortname_and_flushes(self) -> None:
        instrument = SimpleNamespace(symbol="PKO", shortname="PKO", name="POWSZECHNA KASA")
        market = SimpleNamespace(mic="XWAR")
        session = _session((instrument, market))

        result = await update_instrument_shortname(
            session,
            mic="XWAR",
            symbol="PKO",
            shortname="PKO BP SA",
            expected_shortname="PKO",
        )

        self.assertEqual(result, (instrument, market))
        self.assertEqual(instrument.shortname, "PKO BP SA")
        self.assertEqual(instrument.name, "POWSZECHNA KASA")
        session.flush.assert_awaited_once()

    async def test_crud_rejects_stale_expected_shortname(self) -> None:
        instrument = SimpleNamespace(symbol="PKO", shortname="CURRENT")
        session = _session((instrument, SimpleNamespace(mic="XWAR")))

        with self.assertRaisesRegex(ValueError, "changed concurrently"):
            await update_instrument_shortname(
                session,
                mic="XWAR",
                symbol="PKO",
                shortname="NEW NAME",
                expected_shortname="STALE",
            )

        session.flush.assert_not_awaited()

    async def test_crud_maps_unique_shortname_failure_to_conflict(self) -> None:
        instrument = SimpleNamespace(symbol="PKO", shortname="PKO")
        session = _session(
            (instrument, SimpleNamespace(mic="XWAR")),
            IntegrityError("UPDATE instrument", {}, Exception("duplicate")),
        )

        with self.assertRaisesRegex(ValueError, "shortname already exists"):
            await update_instrument_shortname(
                session,
                mic="XWAR",
                symbol="PKO",
                shortname="DUPLICATE",
                expected_shortname="PKO",
            )

    async def test_route_returns_not_found_and_conflict_contracts(self) -> None:
        payload = InstrumentShortnameUpdate(shortname="PKO BP SA", expected_shortname="PKO")
        session = _session()

        with patch(
            "app.api.routes.stock.update_instrument_shortname",
            new=AsyncMock(return_value=None),
        ):
            with self.assertRaises(HTTPException) as missing:
                await stock_routes.api_update_instrument_shortname("PKO", payload, "XWAR", session)
        self.assertEqual(missing.exception.status_code, 404)

        with patch(
            "app.api.routes.stock.update_instrument_shortname",
            new=AsyncMock(side_effect=ValueError("concurrent update")),
        ):
            with self.assertRaises(HTTPException) as conflict:
                await stock_routes.api_update_instrument_shortname("PKO", payload, "XWAR", session)
        self.assertEqual(conflict.exception.status_code, 409)

    async def test_schema_normalizes_case_and_rejects_invalid_names(self) -> None:
        payload = InstrumentShortnameUpdate(shortname="  Pko bp sa ", expected_shortname=" pko ")

        self.assertEqual(payload.shortname, "PKO BP SA")
        self.assertEqual(payload.expected_shortname, "PKO")
        with self.assertRaises(ValidationError):
            InstrumentShortnameUpdate(shortname=" ", expected_shortname="PKO")
        with self.assertRaises(ValidationError):
            InstrumentShortnameUpdate(shortname="X" * 41, expected_shortname="PKO")
