from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, Mock, patch
from uuid import UUID, uuid4
import unittest

import allure
import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.api.routes import cash_holding as cash_routes
from app.crud.cash_holding_crud import update_cash_holding
from app.models.enums import InstrumentCurrency
from app.schemas.schemas import CashHoldingCreate, CashHoldingUpdate

pytestmark = pytest.mark.unit


class _Begin:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _session() -> Mock:
    session = Mock()
    session.begin = Mock(return_value=_Begin())
    return session


def _stamp() -> datetime:
    return datetime(2026, 10, 4, 12, 0, tzinfo=timezone.utc)


def _cash_row(wallet_id: UUID, **overrides) -> SimpleNamespace:
    values = {
        "id": uuid4(),
        "wallet_id": wallet_id,
        "name": "Sejf",
        "amount": Decimal("1500.00"),
        "currency": InstrumentCurrency.PLN,
        "note": None,
        "created_at": _stamp(),
        "updated_at": _stamp(),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@allure.epic("Unit Tests")
@allure.feature("Wallet")
@allure.story("Physical cash holding payloads keep money values non-negative and rounded")
@allure.severity(allure.severity_level.CRITICAL)
@allure.tag("wallet", "cash", "money", "validation", "unit")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
@allure.description(
    "Physical cash is an asset entered by the user: amount must be >= 0 and is stored "
    "with 2 decimals; currency may be PLN, USD, EUR, GBP or CHF; empty notes become null."
)
class TestCashHoldingSchemas(unittest.TestCase):
    def test_create_rounds_amount_to_two_decimals_and_accepts_gbp(self) -> None:
        payload = CashHoldingCreate(
            wallet_id=uuid4(),
            name="  Portfel  ",
            amount=Decimal("120.005"),
            currency=InstrumentCurrency.GBP,
            note="",
        )

        assert payload.name == "Portfel"
        assert payload.amount == Decimal("120.01")
        assert payload.currency == InstrumentCurrency.GBP
        assert payload.note is None

    def test_create_accepts_zero_amount_and_chf(self) -> None:
        payload = CashHoldingCreate(
            wallet_id=uuid4(),
            name="Skarbonka",
            amount=Decimal("0"),
            currency=InstrumentCurrency.CHF,
        )

        assert payload.amount == Decimal("0.00")

    def test_create_rejects_negative_amount(self) -> None:
        with pytest.raises(ValidationError):
            CashHoldingCreate(
                wallet_id=uuid4(),
                name="Portfel",
                amount=Decimal("-0.01"),
                currency=InstrumentCurrency.PLN,
            )

    def test_create_rejects_blank_name_and_unknown_currency(self) -> None:
        with pytest.raises(ValidationError):
            CashHoldingCreate(wallet_id=uuid4(), name="   ", amount=Decimal("10"), currency=InstrumentCurrency.PLN)
        with pytest.raises(ValidationError):
            CashHoldingCreate(wallet_id=uuid4(), name="Portfel", amount=Decimal("10"), currency="JPY")

    def test_update_requires_at_least_one_field_and_rejects_negative_amount(self) -> None:
        with pytest.raises(ValidationError):
            CashHoldingUpdate()
        with pytest.raises(ValidationError):
            CashHoldingUpdate(amount=Decimal("-5"))


@allure.epic("Unit Tests")
@allure.feature("Wallet")
@allure.story("Physical cash holding route handlers verify user and wallet ownership")
@allure.severity(allure.severity_level.CRITICAL)
@allure.tag("wallet", "cash", "api-contract", "ownership", "unit")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
class TestCashHoldingRoutes(unittest.IsolatedAsyncioTestCase):
    async def test_list_requires_existing_user_and_owned_wallet(self) -> None:
        user_id = uuid4()
        wallet_id = uuid4()
        row = _cash_row(wallet_id, currency=InstrumentCurrency.USD, amount=Decimal("200.00"))
        session = _session()

        with (
            patch("app.api.routes.cash_holding.get_user", new=AsyncMock(return_value=SimpleNamespace(id=user_id))),
            patch("app.api.routes.cash_holding.get_wallet", new=AsyncMock(return_value=SimpleNamespace(id=wallet_id, user_id=user_id))),
            patch("app.api.routes.cash_holding.list_cash_holdings", new=AsyncMock(return_value=[row])) as list_mock,
        ):
            response = await cash_routes.list_cash_holdings_for_wallet(wallet_id=wallet_id, user_id=user_id, session=session)

        assert response[0].id == row.id
        assert response[0].amount == Decimal("200.00")
        assert response[0].currency == InstrumentCurrency.USD
        list_mock.assert_awaited_once_with(session, wallet_id=wallet_id)

    async def test_list_rejects_foreign_wallet(self) -> None:
        user_id = uuid4()
        wallet_id = uuid4()

        with (
            patch("app.api.routes.cash_holding.get_user", new=AsyncMock(return_value=SimpleNamespace(id=user_id))),
            patch("app.api.routes.cash_holding.get_wallet", new=AsyncMock(return_value=SimpleNamespace(id=wallet_id, user_id=uuid4()))),
            patch("app.api.routes.cash_holding.list_cash_holdings", new=AsyncMock()) as list_mock,
        ):
            with pytest.raises(HTTPException) as exc:
                await cash_routes.list_cash_holdings_for_wallet(wallet_id=wallet_id, user_id=user_id, session=_session())

        assert exc.value.status_code == 404
        list_mock.assert_not_awaited()

    async def test_create_persists_for_owned_wallet(self) -> None:
        user_id = uuid4()
        wallet_id = uuid4()
        payload = CashHoldingCreate(wallet_id=wallet_id, name="Sejf", amount=Decimal("1500"), currency=InstrumentCurrency.PLN)
        created = _cash_row(wallet_id)

        with (
            patch("app.api.routes.cash_holding.get_user", new=AsyncMock(return_value=SimpleNamespace(id=user_id))),
            patch("app.api.routes.cash_holding.get_wallet", new=AsyncMock(return_value=SimpleNamespace(id=wallet_id, user_id=user_id))),
            patch("app.api.routes.cash_holding.create_cash_holding", new=AsyncMock(return_value=created)) as create_mock,
        ):
            response = await cash_routes.create_cash_holding_endpoint(payload=payload, user_id=user_id, session=_session())

        assert response.id == created.id
        assert response.amount == Decimal("1500.00")
        create_mock.assert_awaited_once_with(ANY, payload=payload)

    async def test_create_rejects_unknown_user_and_foreign_wallet_before_persisting(self) -> None:
        user_id = uuid4()
        wallet_id = uuid4()
        payload = CashHoldingCreate(wallet_id=wallet_id, name="Sejf", amount=Decimal("1500"), currency=InstrumentCurrency.PLN)
        create_mock = AsyncMock()

        with (
            patch("app.api.routes.cash_holding.get_user", new=AsyncMock(return_value=None)),
            patch("app.api.routes.cash_holding.create_cash_holding", new=create_mock),
        ):
            with pytest.raises(HTTPException) as unknown_user:
                await cash_routes.create_cash_holding_endpoint(payload=payload, user_id=user_id, session=_session())

        with (
            patch("app.api.routes.cash_holding.get_user", new=AsyncMock(return_value=SimpleNamespace(id=user_id))),
            patch("app.api.routes.cash_holding.get_wallet", new=AsyncMock(return_value=SimpleNamespace(id=wallet_id, user_id=uuid4()))),
            patch("app.api.routes.cash_holding.create_cash_holding", new=create_mock),
        ):
            with pytest.raises(HTTPException) as foreign_wallet:
                await cash_routes.create_cash_holding_endpoint(payload=payload, user_id=user_id, session=_session())

        assert unknown_user.value.status_code == 400
        assert foreign_wallet.value.status_code == 404
        create_mock.assert_not_awaited()

    async def test_update_checks_holding_wallet_owner_and_returns_updated_model(self) -> None:
        user_id = uuid4()
        wallet_id = uuid4()
        cash_id = uuid4()
        payload = CashHoldingUpdate(amount=Decimal("1250.50"), currency=InstrumentCurrency.EUR)
        existing = _cash_row(wallet_id, id=cash_id)
        updated = _cash_row(wallet_id, id=cash_id, amount=Decimal("1250.50"), currency=InstrumentCurrency.EUR)

        with (
            patch("app.api.routes.cash_holding.get_user", new=AsyncMock(return_value=SimpleNamespace(id=user_id))),
            patch("app.api.routes.cash_holding.get_cash_holding", new=AsyncMock(return_value=existing)),
            patch("app.api.routes.cash_holding.get_wallet", new=AsyncMock(return_value=SimpleNamespace(id=wallet_id, user_id=user_id))),
            patch("app.api.routes.cash_holding.update_cash_holding", new=AsyncMock(return_value=updated)) as update_mock,
        ):
            response = await cash_routes.update_cash_holding_endpoint(
                cash_holding_id=cash_id,
                payload=payload,
                user_id=user_id,
                session=_session(),
            )

        assert response.amount == Decimal("1250.50")
        assert response.currency == InstrumentCurrency.EUR
        update_mock.assert_awaited_once_with(ANY, cash_holding_id=cash_id, payload=payload)

    async def test_update_and_delete_hide_other_users_holding_as_not_found(self) -> None:
        user_id = uuid4()
        wallet_id = uuid4()
        existing = _cash_row(wallet_id)
        update_mock = AsyncMock()
        delete_mock = AsyncMock()

        with (
            patch("app.api.routes.cash_holding.get_user", new=AsyncMock(return_value=SimpleNamespace(id=user_id))),
            patch("app.api.routes.cash_holding.get_cash_holding", new=AsyncMock(return_value=existing)),
            patch("app.api.routes.cash_holding.get_wallet", new=AsyncMock(return_value=SimpleNamespace(id=wallet_id, user_id=uuid4()))),
            patch("app.api.routes.cash_holding.update_cash_holding", new=update_mock),
            patch("app.api.routes.cash_holding.delete_cash_holding", new=delete_mock),
        ):
            with pytest.raises(HTTPException) as update_exc:
                await cash_routes.update_cash_holding_endpoint(
                    cash_holding_id=existing.id,
                    payload=CashHoldingUpdate(amount=Decimal("1")),
                    user_id=user_id,
                    session=_session(),
                )
            with pytest.raises(HTTPException) as delete_exc:
                await cash_routes.delete_cash_holding_endpoint(cash_holding_id=existing.id, user_id=user_id, session=_session())

        assert update_exc.value.status_code == 404
        assert delete_exc.value.status_code == 404
        update_mock.assert_not_awaited()
        delete_mock.assert_not_awaited()

    async def test_delete_owned_holding_returns_ok(self) -> None:
        user_id = uuid4()
        wallet_id = uuid4()
        existing = _cash_row(wallet_id)

        with (
            patch("app.api.routes.cash_holding.get_user", new=AsyncMock(return_value=SimpleNamespace(id=user_id))),
            patch("app.api.routes.cash_holding.get_cash_holding", new=AsyncMock(return_value=existing)),
            patch("app.api.routes.cash_holding.get_wallet", new=AsyncMock(return_value=SimpleNamespace(id=wallet_id, user_id=user_id))),
            patch("app.api.routes.cash_holding.delete_cash_holding", new=AsyncMock(return_value=True)) as delete_mock,
        ):
            response = await cash_routes.delete_cash_holding_endpoint(cash_holding_id=existing.id, user_id=user_id, session=_session())

        assert response == {"ok": True}
        delete_mock.assert_awaited_once_with(ANY, cash_holding_id=existing.id)

    async def test_delete_maps_missing_row_to_not_found(self) -> None:
        user_id = uuid4()

        with (
            patch("app.api.routes.cash_holding.get_user", new=AsyncMock(return_value=SimpleNamespace(id=user_id))),
            patch("app.api.routes.cash_holding.get_cash_holding", new=AsyncMock(return_value=None)),
        ):
            with pytest.raises(HTTPException) as exc:
                await cash_routes.delete_cash_holding_endpoint(cash_holding_id=uuid4(), user_id=user_id, session=_session())

        assert exc.value.status_code == 404


@allure.epic("Unit Tests")
@allure.feature("Wallet")
@allure.story("Physical cash holding partial update keeps unset fields and can clear the note")
@allure.severity(allure.severity_level.NORMAL)
@allure.tag("wallet", "cash", "crud", "unit")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
class TestCashHoldingCrud(unittest.IsolatedAsyncioTestCase):
    async def test_update_changes_amount_keeps_currency_and_clears_note(self) -> None:
        obj = _cash_row(uuid4(), amount=Decimal("1500.00"), currency=InstrumentCurrency.PLN, note="na wakacje")
        session = Mock()
        session.add = Mock()
        session.flush = AsyncMock()
        session.refresh = AsyncMock()

        with patch("app.crud.cash_holding_crud.get_cash_holding", new=AsyncMock(return_value=obj)):
            result = await update_cash_holding(
                session,
                cash_holding_id=obj.id,
                payload=CashHoldingUpdate(amount=Decimal("1499.995"), note=""),
            )

        assert result is obj
        assert obj.amount == Decimal("1500.00")
        assert obj.currency == InstrumentCurrency.PLN
        assert obj.name == "Sejf"
        assert obj.note is None

    async def test_update_returns_none_for_missing_holding(self) -> None:
        with patch("app.crud.cash_holding_crud.get_cash_holding", new=AsyncMock(return_value=None)):
            result = await update_cash_holding(Mock(), cash_holding_id=uuid4(), payload=CashHoldingUpdate(amount=Decimal("1")))

        assert result is None
