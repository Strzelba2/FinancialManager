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
from sqlalchemy.exc import IntegrityError

from app.api.routes import alerts as alert_routes
from app.api.routes import debt as debt_routes
from app.api.routes import favorites as favorite_routes
from app.api.routes import goals as goal_routes
from app.api.routes import metal_holding as metal_routes
from app.api.routes import note as note_routes
from app.api.routes import real_estate as real_estate_routes
from app.api.routes import recurring_expenses as recurring_routes
from app.api.routes import transaction as transaction_routes
from app.api.routes import wallet as wallet_routes
from app.api.routes import wallet_manager as manager_routes
from app.core.exceptions import DuplicateTransactionError, ImportMismatchError, UnknownAccountError, UnknownUserError
from app.models.enums import Currency, InstrumentCurrency, MetalType, PropertyType
from app.schemas.response import (
    BatchUpdateTransactionsRequest,
    BatchUpdateTransactionsResponse,
    CreateMonthlySnapshotIn,
    SellMetalIn,
    SellRealEstateIn,
    WalletManagerTreeIn,
    WalletRenameIn,
)
from app.schemas.schemas import (
    CreateTransactionsRequest,
    DebtCreate,
    DebtUpdate,
    FavoriteItemCreate,
    FavoriteListCreate,
    MetalHoldingCreate,
    MetalHoldingUpdate,
    PriceAlertCreate,
    PriceAlertUpdate,
    RealEstateCreate,
    RealEstateUpdate,
    RecurringExpenseCreate,
    RecurringExpenseUpdate,
    TransactionBatchUpdate,
    TransactionCreate,
    TransactionIn,
    UserNoteUpsert,
    WalletCreateWithoutUser,
    YearGoalCreate,
)

pytestmark = pytest.mark.unit


class _Begin:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _session() -> Mock:
    session = Mock()
    session.begin = Mock(return_value=_Begin())
    session.rollback = AsyncMock()
    session.refresh = AsyncMock()
    return session


def _stamp() -> datetime:
    return datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)


def _debt_row(wallet_id: UUID, **overrides) -> SimpleNamespace:
    values = {
        "id": uuid4(),
        "wallet_id": wallet_id,
        "name": "Mortgage",
        "lander": "Bank",
        "amount": Decimal("250000.00"),
        "currency": Currency.PLN,
        "interest_rate_pct": Decimal("6.50"),
        "monthly_payment": Decimal("3200.00"),
        "end_date": _stamp(),
        "created_at": _stamp(),
        "updated_at": _stamp(),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _expense_row(wallet_id: UUID, **overrides) -> SimpleNamespace:
    values = {
        "id": uuid4(),
        "wallet_id": wallet_id,
        "name": "Rent",
        "category": "Home",
        "amount": Decimal("2100.00"),
        "currency": Currency.PLN,
        "due_day": 5,
        "account": "Main",
        "note": "standing order",
        "created_at": _stamp(),
        "updated_at": _stamp(),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _note_row(user_id: UUID, text: str = "monthly planning") -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        user_id=user_id,
        text=text,
        created_at=_stamp(),
        updated_at=_stamp(),
    )


def _alert_row(user_id: UUID, instrument_id: UUID, **overrides) -> SimpleNamespace:
    values = {
        "id": uuid4(),
        "user_id": user_id,
        "instrument_id": instrument_id,
        "below_price": Decimal("80.00"),
        "above_price": Decimal("110.00"),
        "enabled": True,
        "one_shot": False,
        "expires_at": None,
        "created_at": _stamp(),
        "updated_at": _stamp(),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _favorite_list(user_id: UUID, **overrides) -> SimpleNamespace:
    values = {
        "id": uuid4(),
        "user_id": user_id,
        "name": "Watchlist",
        "description": "long term",
        "created_at": _stamp(),
        "updated_at": _stamp(),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _favorite_item(list_id: UUID, instrument_id: UUID) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        favorite_list_id=list_id,
        instrument_id=instrument_id,
        created_at=_stamp(),
        updated_at=_stamp(),
    )


def _metal_row(wallet_id: UUID, **overrides) -> SimpleNamespace:
    values = {
        "id": uuid4(),
        "wallet_id": wallet_id,
        "metal": MetalType.GOLD,
        "grams": Decimal("10.000000"),
        "cost_basis": Decimal("2500.00"),
        "cost_currency": Currency.PLN,
        "quote_symbol": "GC.F",
        "created_at": _stamp(),
        "updated_at": _stamp(),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _real_estate_row(wallet_id: UUID, **overrides) -> SimpleNamespace:
    values = {
        "id": uuid4(),
        "wallet_id": wallet_id,
        "name": "Apartment",
        "country": "PL",
        "city": "Warsaw",
        "type": PropertyType.APARTMENT,
        "area_m2": Decimal("48.50"),
        "purchase_price": Decimal("650000.00"),
        "purchase_currency": Currency.PLN,
        "created_at": _stamp(),
        "updated_at": _stamp(),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _year_goal_row(wallet_id: UUID, **overrides) -> SimpleNamespace:
    values = {
        "id": uuid4(),
        "wallet_id": wallet_id,
        "year": 2026,
        "rev_target_year": Decimal("120000.00"),
        "exp_budget_year": Decimal("80000.00"),
        "capital_gain_target_year": Decimal("15000.00"),
        "currency": Currency.PLN,
        "created_at": _stamp(),
        "updated_at": _stamp(),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@allure.epic("Unit Tests")
@allure.feature("Wallet")
@allure.story("Debt route handlers verify user and wallet ownership")
@allure.severity(allure.severity_level.CRITICAL)
@allure.tag("wallet", "debts", "api-contract", "ownership", "unit")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
class TestDebtRoutes(unittest.IsolatedAsyncioTestCase):
    async def test_list_debts_requires_existing_user_and_owned_wallet(self) -> None:
        user_id = uuid4()
        wallet_id = uuid4()
        debt = _debt_row(wallet_id)
        session = _session()

        with (
            patch("app.api.routes.debt.get_user", new=AsyncMock(return_value=SimpleNamespace(id=user_id))),
            patch("app.api.routes.debt.get_wallet", new=AsyncMock(return_value=SimpleNamespace(id=wallet_id, user_id=user_id))),
            patch("app.api.routes.debt.list_debts", new=AsyncMock(return_value=[debt])) as list_mock,
        ):
            response = await debt_routes.list_debts_for_wallet(wallet_id=wallet_id, user_id=user_id, session=session)

        assert response[0].id == debt.id
        assert response[0].amount == Decimal("250000.00")
        list_mock.assert_awaited_once_with(session, wallet_id=wallet_id)

    async def test_create_debt_rejects_foreign_wallet_before_persisting(self) -> None:
        user_id = uuid4()
        wallet_id = uuid4()
        payload = DebtCreate(
            wallet_id=wallet_id,
            name="Car loan",
            lander="Credit union",
            amount=Decimal("12000.00"),
            currency=Currency.PLN,
            interest_rate_pct=Decimal("8.00"),
            monthly_payment=Decimal("600.00"),
            end_date=_stamp(),
        )
        create_mock = AsyncMock()

        with (
            patch("app.api.routes.debt.get_user", new=AsyncMock(return_value=SimpleNamespace(id=user_id))),
            patch("app.api.routes.debt.get_wallet", new=AsyncMock(return_value=SimpleNamespace(id=wallet_id, user_id=uuid4()))),
            patch("app.api.routes.debt.create_debt", new=create_mock),
        ):
            with pytest.raises(HTTPException) as exc:
                await debt_routes.create_debt_endpoint(payload=payload, user_id=user_id, session=_session())

        assert exc.value.status_code == 404
        create_mock.assert_not_awaited()

    async def test_update_debt_checks_debt_wallet_owner_and_returns_updated_model(self) -> None:
        user_id = uuid4()
        wallet_id = uuid4()
        debt_id = uuid4()
        payload = DebtUpdate(amount=Decimal("240000.00"), monthly_payment=Decimal("3500.00"))
        existing = _debt_row(wallet_id, id=debt_id)
        updated = _debt_row(wallet_id, id=debt_id, amount=Decimal("240000.00"), monthly_payment=Decimal("3500.00"))

        with (
            patch("app.api.routes.debt.get_user", new=AsyncMock(return_value=SimpleNamespace(id=user_id))),
            patch("app.api.routes.debt.get_debt", new=AsyncMock(return_value=existing)),
            patch("app.api.routes.debt.get_wallet", new=AsyncMock(return_value=SimpleNamespace(id=wallet_id, user_id=user_id))),
            patch("app.api.routes.debt.update_debt", new=AsyncMock(return_value=updated)) as update_mock,
        ):
            response = await debt_routes.update_debt_endpoint(
                debt_id=debt_id,
                payload=payload,
                user_id=user_id,
                session=_session(),
            )

        assert response.amount == Decimal("240000.00")
        assert response.monthly_payment == Decimal("3500.00")
        update_mock.assert_awaited_once_with(ANY, debt_id=debt_id, payload=payload)

    async def test_delete_debt_maps_missing_row_to_not_found(self) -> None:
        user_id = uuid4()
        debt_id = uuid4()

        with (
            patch("app.api.routes.debt.get_user", new=AsyncMock(return_value=SimpleNamespace(id=user_id))),
            patch("app.api.routes.debt.get_debt", new=AsyncMock(return_value=None)),
        ):
            with pytest.raises(HTTPException) as exc:
                await debt_routes.delete_debt_endpoint(debt_id=debt_id, user_id=user_id, session=_session())

        assert exc.value.status_code == 404


@allure.epic("Unit Tests")
@allure.feature("Wallet")
@allure.story("Recurring expense route handlers preserve request contract")
@allure.severity(allure.severity_level.NORMAL)
@allure.tag("wallet", "recurring-expenses", "api-contract", "unit")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
class TestRecurringExpenseRoutes(unittest.IsolatedAsyncioTestCase):
    async def test_create_recurring_expense_requires_owned_wallet(self) -> None:
        user_id = uuid4()
        wallet_id = uuid4()
        payload = RecurringExpenseCreate(
            wallet_id=wallet_id,
            name="Insurance",
            category="Protection",
            amount=Decimal("99.90"),
            currency=Currency.PLN,
            due_day=15,
            account="Main",
            note="annual policy paid monthly",
        )
        created = _expense_row(wallet_id, name="Insurance", amount=Decimal("99.90"), due_day=15)

        with (
            patch("app.api.routes.recurring_expenses.get_user", new=AsyncMock(return_value=SimpleNamespace(id=user_id))),
            patch(
                "app.api.routes.recurring_expenses.get_wallet",
                new=AsyncMock(return_value=SimpleNamespace(id=wallet_id, user_id=user_id)),
            ),
            patch("app.api.routes.recurring_expenses.create_recurring_expense", new=AsyncMock(return_value=created)) as create_mock,
        ):
            response = await recurring_routes.create_recurring_expense_endpoint(
                payload=payload,
                user_id=user_id,
                session=_session(),
            )

        assert response.name == "Insurance"
        assert response.due_day == 15
        create_mock.assert_awaited_once()

    async def test_list_recurring_expenses_rejects_unknown_user(self) -> None:
        list_mock = AsyncMock()

        with (
            patch("app.api.routes.recurring_expenses.get_user", new=AsyncMock(return_value=None)),
            patch("app.api.routes.recurring_expenses.list_recurring_expenses", new=list_mock),
        ):
            with pytest.raises(HTTPException) as exc:
                await recurring_routes.list_recurring_expenses_endpoint(
                    wallet_id=uuid4(),
                    user_id=uuid4(),
                    session=_session(),
                )

        assert exc.value.status_code == 400
        list_mock.assert_not_awaited()

    async def test_update_recurring_expense_returns_not_found_when_crud_has_no_row(self) -> None:
        with (
            patch("app.api.routes.recurring_expenses.get_user", new=AsyncMock(return_value=SimpleNamespace(id=uuid4()))),
            patch("app.api.routes.recurring_expenses.update_recurring_expense", new=AsyncMock(return_value=None)),
        ):
            with pytest.raises(HTTPException) as exc:
                await recurring_routes.update_recurring_expense_endpoint(
                    expense_id=uuid4(),
                    payload=RecurringExpenseUpdate(amount=Decimal("120.00")),
                    user_id=uuid4(),
                    session=_session(),
                )

        assert exc.value.status_code == 404

    async def test_delete_recurring_expense_delegates_to_crud_for_current_user(self) -> None:
        user_id = uuid4()
        expense_id = uuid4()

        with (
            patch("app.api.routes.recurring_expenses.get_user", new=AsyncMock(return_value=SimpleNamespace(id=user_id))),
            patch("app.api.routes.recurring_expenses.delete_recurring_expense", new=AsyncMock(return_value=True)) as delete_mock,
        ):
            response = await recurring_routes.delete_recurring_expense_endpoint(
                expense_id=expense_id,
                user_id=user_id,
                session=_session(),
            )

        assert response == {"ok": True}
        delete_mock.assert_awaited_once()


@allure.epic("Unit Tests")
@allure.feature("Wallet")
@allure.story("User note handlers validate authenticated user context")
@allure.severity(allure.severity_level.NORMAL)
@allure.tag("wallet", "notes", "api-contract", "unit")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
class TestUserNoteRoutes(unittest.IsolatedAsyncioTestCase):
    async def test_get_note_returns_none_for_known_user_without_note(self) -> None:
        user_id = uuid4()

        with (
            patch("app.api.routes.note.get_user", new=AsyncMock(return_value=SimpleNamespace(id=user_id))),
            patch("app.api.routes.note.get_user_note", new=AsyncMock(return_value=None)),
        ):
            response = await note_routes.get_my_note(user_id=user_id, session=_session())

        assert response is None

    async def test_upsert_note_refreshes_persisted_object_before_response(self) -> None:
        user_id = uuid4()
        session = _session()
        note = _note_row(user_id, text="rebalance plan")

        with (
            patch("app.api.routes.note.get_user", new=AsyncMock(return_value=SimpleNamespace(id=user_id))),
            patch("app.api.routes.note.upsert_user_note", new=AsyncMock(return_value=note)) as upsert_mock,
        ):
            response = await note_routes.upsert_my_note(
                payload=UserNoteUpsert(text="rebalance plan"),
                user_id=user_id,
                session=session,
            )

        assert response.text == "rebalance plan"
        upsert_mock.assert_awaited_once_with(session, user_id=user_id, text="rebalance plan")
        session.refresh.assert_awaited_once_with(note)

    async def test_upsert_note_rejects_unknown_user_before_write(self) -> None:
        upsert_mock = AsyncMock()

        with (
            patch("app.api.routes.note.get_user", new=AsyncMock(return_value=None)),
            patch("app.api.routes.note.upsert_user_note", new=upsert_mock),
        ):
            with pytest.raises(HTTPException) as exc:
                await note_routes.upsert_my_note(
                    payload=UserNoteUpsert(text=""),
                    user_id=uuid4(),
                    session=_session(),
                )

        assert exc.value.status_code == 400
        upsert_mock.assert_not_awaited()


@allure.epic("Unit Tests")
@allure.feature("Wallet")
@allure.story("Alert and favorite routes resolve stock instruments and map API errors")
@allure.severity(allure.severity_level.CRITICAL)
@allure.tag("wallet", "alerts", "favorites", "api-contract", "unit")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
class TestAlertsAndFavoritesRoutes(unittest.IsolatedAsyncioTestCase):
    async def test_list_alerts_preserves_symbol_enrichment(self) -> None:
        user_id = uuid4()
        instrument_id = uuid4()
        alert = _alert_row(user_id, instrument_id)

        with patch("app.api.routes.alerts.list_alerts_with_symbols", new=AsyncMock(return_value=[(alert, "PKO")])):
            response = await alert_routes.api_list_alerts(session=_session(), user_id=user_id)

        assert response[0].symbol == "PKO"
        assert response[0].above_price == Decimal("110.00")

    async def test_upsert_alert_maps_invalid_thresholds_to_bad_request(self) -> None:
        user_id = uuid4()
        instrument = SimpleNamespace(id=uuid4())
        body = PriceAlertCreate(symbol="PKO", below_price=Decimal("120.00"), above_price=Decimal("100.00"))

        with (
            patch("app.api.routes.alerts.get_instrument_by_symbol", new=AsyncMock(return_value=instrument)),
            patch("app.api.routes.alerts.upsert_alert", new=AsyncMock(side_effect=ValueError("below must be below above"))),
        ):
            with pytest.raises(HTTPException) as exc:
                await alert_routes.api_upsert_alert(body=body, session=_session(), user_id=user_id)

        assert exc.value.status_code == 400
        assert "below must be below above" in exc.value.detail

    async def test_get_alert_returns_not_found_for_unknown_symbol(self) -> None:
        with patch("app.api.routes.alerts.get_instrument_by_symbol", new=AsyncMock(return_value=None)):
            with pytest.raises(HTTPException) as exc:
                await alert_routes.api_get_alert(symbol="NOPE", session=_session(), user_id=uuid4())

        assert exc.value.status_code == 404

    async def test_patch_alert_delegates_partial_payload_and_returns_model(self) -> None:
        user_id = uuid4()
        instrument_id = uuid4()
        body = PriceAlertUpdate(enabled=False)
        updated = _alert_row(user_id, instrument_id, enabled=False)

        with (
            patch("app.api.routes.alerts.get_instrument_by_symbol", new=AsyncMock(return_value=SimpleNamespace(id=instrument_id))),
            patch("app.api.routes.alerts.patch_alert", new=AsyncMock(return_value=updated)) as patch_mock,
        ):
            response = await alert_routes.api_patch_alert(symbol="PKO", body=body, session=_session(), user_id=user_id)

        assert response.enabled is False
        patch_mock.assert_awaited_once_with(ANY, user_id, instrument_id, body)

    async def test_create_favorite_list_maps_duplicate_name_to_conflict(self) -> None:
        with patch(
            "app.api.routes.favorites.create_favorite_list",
            new=AsyncMock(side_effect=ValueError("favorite list already exists")),
        ):
            with pytest.raises(HTTPException) as exc:
                await favorite_routes.api_create_list(
                    body=FavoriteListCreate(name="Watchlist", description=None),
                    session=_session(),
                    user_id=uuid4(),
                )

        assert exc.value.status_code == 409

    async def test_add_favorite_item_resolves_stock_instrument_and_local_mirror(self) -> None:
        user_id = uuid4()
        list_id = uuid4()
        instrument_id = uuid4()
        stock_client = Mock()
        stock_client.resolve_instrument = AsyncMock(
            return_value=SimpleNamespace(name="PKO Bank Polski", mic="XWAR", symbol="PKO", currency="PLN")
        )
        local_instrument = SimpleNamespace(id=instrument_id)
        favorite = _favorite_item(list_id, instrument_id)

        with (
            patch("app.api.routes.favorites.get_or_create_instrument", new=AsyncMock(return_value=local_instrument)) as get_or_create,
            patch("app.api.routes.favorites.add_favorite_item", new=AsyncMock(return_value=favorite)) as add_mock,
        ):
            response = await favorite_routes.api_add_item(
                list_id=list_id,
                body=FavoriteItemCreate(symbol="PKO", mic="XWAR"),
                session=_session(),
                user_id=user_id,
                stock_client=stock_client,
            )

        assert response.instrument_id == instrument_id
        get_or_create.assert_awaited_once_with(
            session=ANY,
            mic="XWAR",
            symbol="PKO",
            name="PKO Bank Polski",
            currency=InstrumentCurrency.PLN,
        )
        add_mock.assert_awaited_once_with(ANY, user_id, list_id, instrument_id)

    async def test_remove_favorite_item_returns_not_found_when_item_missing(self) -> None:
        with (
            patch("app.api.routes.favorites.get_instrument_by_symbol", new=AsyncMock(return_value=SimpleNamespace(id=uuid4()))),
            patch("app.api.routes.favorites.remove_favorite_item", new=AsyncMock(return_value=False)),
        ):
            with pytest.raises(HTTPException) as exc:
                await favorite_routes.api_remove_item(
                    list_id=uuid4(),
                    symbol="PKO",
                    session=_session(),
                    user_id=uuid4(),
                )

        assert exc.value.status_code == 404


@allure.epic("Unit Tests")
@allure.feature("Wallet")
@allure.story("Transaction route handlers map service errors and page rows")
@allure.severity(allure.severity_level.CRITICAL)
@allure.tag("wallet", "transactions", "api-contract", "financial-data", "unit")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
class TestTransactionRoutes(unittest.IsolatedAsyncioTestCase):
    async def test_create_rebalance_maps_domain_exceptions_to_http_status(self) -> None:
        payload = CreateTransactionsRequest(
            account_id=uuid4(),
            transactions=[
                TransactionIn(
                    date=_stamp(),
                    amount=Decimal("10.00"),
                    description="Dividend",
                    amount_after=Decimal("110.00"),
                    category="Capital",
                    status="INCOME",
                )
            ],
        )

        cases = [
            (UnknownUserError("unknown"), 400),
            (UnknownAccountError("missing account"), 404),
            (DuplicateTransactionError("duplicate"), 409),
            (ImportMismatchError("balance mismatch"), 422),
        ]

        for error, expected_status in cases:
            with self.subTest(expected_status=expected_status):
                with patch(
                    "app.api.routes.transaction.create_transactions_rebalance_service",
                    new=AsyncMock(side_effect=error),
                ):
                    with pytest.raises(HTTPException) as exc:
                        await transaction_routes.create_transactions_rebalance(
                            payload=payload,
                            user_id=uuid4(),
                            session=_session(),
                        )

                assert exc.value.status_code == expected_status

    async def test_transactions_page_enriches_rows_with_account_name_and_currency(self) -> None:
        user_id = uuid4()
        account_id = uuid4()
        tx = TransactionCreate(
            account_id=account_id,
            amount=Decimal("120.00"),
            description="Salary",
            category="Work",
            status="INCOME",
            balance_before=Decimal("0.00"),
            balance_after=Decimal("120.00"),
            date_transaction=_stamp(),
        )
        tx_read = SimpleNamespace(
            id=uuid4(),
            account_id=account_id,
            amount=tx.amount,
            description=tx.description,
            category=tx.category,
            status=tx.status,
            balance_before=tx.balance_before,
            balance_after=tx.balance_after,
            date_transaction=tx.date_transaction,
            created_at=_stamp(),
            updated_at=_stamp(),
            model_dump=lambda: {
                "id": tx_read.id,
                "account_id": account_id,
                "amount": tx.amount,
                "description": tx.description,
                "category": tx.category,
                "status": tx.status,
                "balance_before": tx.balance_before,
                "balance_after": tx.balance_after,
                "date_transaction": tx.date_transaction,
                "created_at": _stamp(),
                "updated_at": _stamp(),
            },
        )
        account = SimpleNamespace(name="Main", currency=Currency.PLN)

        with patch(
            "app.api.routes.transaction.list_transactions_page",
            new=AsyncMock(return_value=([(tx_read, account)], 1, 50, {"PLN": Decimal("120.00")})),
        ) as list_mock:
            response = await transaction_routes.get_transactions_page(
                page=1,
                size=50,
                account_id=[account_id],
                category=["Work"],
                status=["INCOME"],
                date_from=None,
                date_to=None,
                q="salary",
                sort_by="date",
                sort_dir="desc",
                user_id=user_id,
                session=_session(),
            )

        assert response.total == 1
        assert response.items[0].account_name == "Main"
        assert response.items[0].ccy == "PLN"
        list_mock.assert_awaited_once()

    async def test_delete_transaction_maps_balance_mismatch_to_bad_request(self) -> None:
        with patch(
            "app.api.routes.transaction.delete_transaction_for_user_rebalance",
            new=AsyncMock(side_effect=ImportMismatchError("balance mismatch")),
        ):
            with pytest.raises(HTTPException) as exc:
                await transaction_routes.api_delete_transaction(
                    transaction_id=uuid4(),
                    user_id=uuid4(),
                    session=_session(),
                )

        assert exc.value.status_code == 400

    async def test_batch_patch_transactions_delegates_request_object(self) -> None:
        req = BatchUpdateTransactionsRequest(
            items=[
                {
                    "id": uuid4(),
                    "category": "Groceries",
                }
            ]
        )
        expected = BatchUpdateTransactionsResponse(updated=1, failed=[])

        with patch("app.api.routes.transaction.batch_update_transactions", new=AsyncMock(return_value=expected)) as batch_mock:
            response = await transaction_routes.patch_transactions_batch(
                req=req,
                user_id=uuid4(),
                session=_session(),
            )

        assert response.updated == 1
        batch_mock.assert_awaited_once()


@allure.epic("Unit Tests")
@allure.feature("Wallet")
@allure.story("Metal holding route handlers protect write paths and sale delegation")
@allure.severity(allure.severity_level.CRITICAL)
@allure.tag("wallet", "metal-holdings", "financial-data", "api-contract", "unit")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
class TestMetalHoldingRoutes(unittest.IsolatedAsyncioTestCase):
    async def test_list_metal_holdings_returns_wallet_rows_for_known_user(self) -> None:
        user_id = uuid4()
        wallet_id = uuid4()
        row = _metal_row(wallet_id)

        with (
            patch("app.api.routes.metal_holding.get_user", new=AsyncMock(return_value=SimpleNamespace(id=user_id))),
            patch("app.api.routes.metal_holding.list_metal_holdings_by_wallet", new=AsyncMock(return_value=[row])) as list_mock,
        ):
            response = await metal_routes.list_metal_holdings_endpoint(
                wallet_id=wallet_id,
                user_id=user_id,
                session=_session(),
            )

        assert response[0].metal == MetalType.GOLD
        assert response[0].grams == Decimal("10.000000")
        list_mock.assert_awaited_once_with(ANY, wallet_id=wallet_id)

    async def test_create_metal_holding_maps_duplicate_to_conflict(self) -> None:
        payload = MetalHoldingCreate(
            wallet_id=uuid4(),
            metal=MetalType.GOLD,
            grams=Decimal("1.500000"),
            cost_basis=Decimal("420.00"),
            cost_currency=Currency.PLN,
            quote_symbol="GC.F",
        )

        with (
            patch("app.api.routes.metal_holding.get_user", new=AsyncMock(return_value=SimpleNamespace(id=uuid4()))),
            patch(
                "app.api.routes.metal_holding.create_metal_holding",
                new=AsyncMock(side_effect=IntegrityError("insert", {}, Exception("duplicate"))),
            ),
        ):
            with pytest.raises(HTTPException) as exc:
                await metal_routes.create_metal_holding_endpoint(
                    payload=payload,
                    user_id=uuid4(),
                    session=_session(),
                )

        assert exc.value.status_code == 409

    async def test_update_metal_holding_returns_not_found_when_crud_has_no_row(self) -> None:
        with (
            patch("app.api.routes.metal_holding.get_user", new=AsyncMock(return_value=SimpleNamespace(id=uuid4()))),
            patch("app.api.routes.metal_holding.update_metal_holding", new=AsyncMock(return_value=None)),
        ):
            with pytest.raises(HTTPException) as exc:
                await metal_routes.update_metal_holding_endpoint(
                    metal_holding_id=uuid4(),
                    payload=MetalHoldingUpdate(grams=Decimal("2.000000")),
                    user_id=uuid4(),
                    session=_session(),
                )

        assert exc.value.status_code == 404

    async def test_sell_metal_rejects_unknown_user_after_rolling_back_read_transaction(self) -> None:
        session = _session()
        sell_mock = AsyncMock()

        with (
            patch("app.api.routes.metal_holding.get_user", new=AsyncMock(return_value=None)),
            patch("app.api.routes.metal_holding.sell_metal_holding_service", new=sell_mock),
        ):
            with pytest.raises(HTTPException) as exc:
                await metal_routes.sell_metal(
                    metal_holding_id=uuid4(),
                    req=SellMetalIn(
                        deposit_account_id=uuid4(),
                        grams_sold=Decimal("1.000000"),
                        proceeds_amount=Decimal("300.00"),
                        proceeds_currency="PLN",
                        create_transaction=True,
                    ),
                    user_id=uuid4(),
                    session=session,
                )

        assert exc.value.status_code == 400
        session.rollback.assert_awaited_once()
        sell_mock.assert_not_awaited()

    async def test_sell_metal_returns_service_update_count(self) -> None:
        user_id = uuid4()
        holding_id = uuid4()
        req = SellMetalIn(
            deposit_account_id=uuid4(),
            grams_sold=Decimal("2.000000"),
            proceeds_amount=Decimal("700.00"),
            proceeds_currency="PLN",
            create_transaction=True,
        )

        with (
            patch("app.api.routes.metal_holding.get_user", new=AsyncMock(return_value=SimpleNamespace(id=user_id))),
            patch("app.api.routes.metal_holding.sell_metal_holding_service", new=AsyncMock(return_value=1)) as service,
        ):
            response = await metal_routes.sell_metal(
                metal_holding_id=holding_id,
                req=req,
                user_id=user_id,
                session=_session(),
            )

        assert response == {"updated": 1}
        service.assert_awaited_once_with(session=ANY, user_id=user_id, metal_holding_id=holding_id, req=req)


@allure.epic("Unit Tests")
@allure.feature("Wallet")
@allure.story("Real estate route handlers map persistence and sale errors")
@allure.severity(allure.severity_level.CRITICAL)
@allure.tag("wallet", "real-estate", "financial-data", "api-contract", "unit")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
class TestRealEstateRoutes(unittest.IsolatedAsyncioTestCase):
    async def test_create_real_estate_returns_created_asset_for_known_user(self) -> None:
        user_id = uuid4()
        wallet_id = uuid4()
        payload = RealEstateCreate(
            wallet_id=wallet_id,
            name="Apartment",
            country="PL",
            city="Warsaw",
            type=PropertyType.APARTMENT,
            area_m2=Decimal("48.50"),
            purchase_price=Decimal("650000.00"),
            purchase_currency=Currency.PLN,
        )
        created = _real_estate_row(wallet_id)

        with (
            patch("app.api.routes.real_estate.get_user", new=AsyncMock(return_value=SimpleNamespace(id=user_id))),
            patch("app.api.routes.real_estate.create_real_estate", new=AsyncMock(return_value=created)) as create_mock,
        ):
            response = await real_estate_routes.create_real_estate_endpoint(
                payload=payload,
                user_id=user_id,
                session=_session(),
            )

        assert response.name == "Apartment"
        assert response.purchase_price == Decimal("650000.00")
        create_mock.assert_awaited_once_with(ANY, data=payload)

    async def test_create_real_estate_maps_integrity_error_to_bad_request(self) -> None:
        payload = RealEstateCreate(
            wallet_id=uuid4(),
            name="Apartment",
            country="PL",
            city="Warsaw",
            type=PropertyType.APARTMENT,
            area_m2=Decimal("48.50"),
            purchase_price=Decimal("650000.00"),
            purchase_currency=Currency.PLN,
        )

        with (
            patch("app.api.routes.real_estate.get_user", new=AsyncMock(return_value=SimpleNamespace(id=uuid4()))),
            patch(
                "app.api.routes.real_estate.create_real_estate",
                new=AsyncMock(side_effect=IntegrityError("insert", {}, Exception("constraint"))),
            ),
        ):
            with pytest.raises(HTTPException) as exc:
                await real_estate_routes.create_real_estate_endpoint(
                    payload=payload,
                    user_id=uuid4(),
                    session=_session(),
                )

        assert exc.value.status_code == 400

    async def test_update_real_estate_maps_missing_asset_to_not_found(self) -> None:
        with (
            patch("app.api.routes.real_estate.get_user", new=AsyncMock(return_value=SimpleNamespace(id=uuid4()))),
            patch("app.api.routes.real_estate.update_real_estate", new=AsyncMock(side_effect=ValueError("missing"))),
        ):
            with pytest.raises(HTTPException) as exc:
                await real_estate_routes.update_real_estate_endpoint(
                    real_estate_id=uuid4(),
                    payload=RealEstateUpdate(name="Updated apartment"),
                    user_id=uuid4(),
                    session=_session(),
                )

        assert exc.value.status_code == 404

    async def test_delete_real_estate_rejects_unknown_user_before_delete(self) -> None:
        delete_mock = AsyncMock()

        with (
            patch("app.api.routes.real_estate.get_user", new=AsyncMock(return_value=None)),
            patch("app.api.routes.real_estate.delete_real_estate", new=delete_mock),
        ):
            with pytest.raises(HTTPException) as exc:
                await real_estate_routes.delete_real_estate_endpoint(
                    real_estate_id=uuid4(),
                    user_id=uuid4(),
                    session=_session(),
                )

        assert exc.value.status_code == 400
        delete_mock.assert_not_awaited()

    async def test_sell_real_estate_rolls_back_before_service_delegation(self) -> None:
        user_id = uuid4()
        real_estate_id = uuid4()
        session = _session()
        req = SellRealEstateIn(
            deposit_account_id=uuid4(),
            proceeds_amount=Decimal("720000.00"),
            proceeds_currency="PLN",
            create_transaction=True,
        )

        with (
            patch("app.api.routes.real_estate.get_user", new=AsyncMock(return_value=SimpleNamespace(id=user_id))),
            patch("app.api.routes.real_estate.sell_real_estate_service", new=AsyncMock(return_value=1)) as service,
        ):
            response = await real_estate_routes.sell_real_estate(
                real_estate_id=real_estate_id,
                req=req,
                user_id=user_id,
                session=session,
            )

        assert response == {"updated": 1}
        session.rollback.assert_awaited_once()
        service.assert_awaited_once_with(session=session, user_id=user_id, real_estate_id=real_estate_id, req=req)


@allure.epic("Unit Tests")
@allure.feature("Wallet")
@allure.story("Year goal routes enforce wallet ownership and expose YTD maps")
@allure.severity(allure.severity_level.CRITICAL)
@allure.tag("wallet", "goals", "money", "ownership", "unit")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
class TestGoalRoutes(unittest.IsolatedAsyncioTestCase):
    async def test_get_goal_returns_none_for_owned_wallet_without_goal(self) -> None:
        user_id = uuid4()
        wallet_id = uuid4()

        with (
            patch("app.api.routes.goals.get_wallet", new=AsyncMock(return_value=SimpleNamespace(id=wallet_id, user_id=user_id))),
            patch("app.api.routes.goals.get_year_goal", new=AsyncMock(return_value=None)),
        ):
            response = await goal_routes.get_goals_for_wallet_year(
                wallet_id=wallet_id,
                year=2026,
                user_id=user_id,
                session=_session(),
            )

        assert response is None

    async def test_list_goals_rejects_foreign_wallet(self) -> None:
        with patch("app.api.routes.goals.get_wallet", new=AsyncMock(return_value=SimpleNamespace(id=uuid4(), user_id=uuid4()))):
            with pytest.raises(HTTPException) as exc:
                await goal_routes.list_goals_for_wallet(wallet_id=uuid4(), user_id=uuid4(), session=_session())

        assert exc.value.status_code == 404

    async def test_upsert_goal_requires_owned_wallet_and_returns_goal(self) -> None:
        user_id = uuid4()
        wallet_id = uuid4()
        payload = YearGoalCreate(
            wallet_id=wallet_id,
            year=2026,
            rev_target_year=Decimal("120000.00"),
            exp_budget_year=Decimal("80000.00"),
            capital_gain_target_year=Decimal("15000.00"),
            currency=Currency.PLN,
        )
        goal = _year_goal_row(wallet_id)

        with (
            patch("app.api.routes.goals.get_wallet", new=AsyncMock(return_value=SimpleNamespace(id=wallet_id, user_id=user_id))),
            patch("app.api.routes.goals.upsert_year_goal", new=AsyncMock(return_value=goal)) as upsert_mock,
        ):
            response = await goal_routes.upsert_goals(payload=payload, user_id=user_id, session=_session())

        assert response.year == 2026
        assert response.capital_gain_target_year == Decimal("15000.00")
        upsert_mock.assert_awaited_once_with(ANY, payload=payload)

    async def test_ytd_summary_returns_income_and_expense_maps_for_owned_wallet(self) -> None:
        user_id = uuid4()
        wallet_id = uuid4()
        income = {Currency.PLN: Decimal("1000.00")}
        expense = {Currency.PLN: Decimal("400.00")}

        with (
            patch("app.api.routes.goals.get_wallet", new=AsyncMock(return_value=SimpleNamespace(id=wallet_id, user_id=user_id))),
            patch(
                "app.api.routes.goals.compute_wallet_ytd_income_expense_maps",
                new=AsyncMock(return_value=(income, expense)),
            ) as compute_mock,
        ):
            response = await goal_routes.get_wallet_ytd_summary(
                wallet_id=wallet_id,
                year=2026,
                user_id=user_id,
                session=_session(),
            )

        assert response == {"year": 2026, "income_by_currency": income, "expense_by_currency": expense}
        compute_mock.assert_awaited_once_with(ANY, wallet_id=wallet_id, year=2026)


@allure.epic("Unit Tests")
@allure.feature("Wallet")
@allure.story("Wallet and manager route handlers delegate with validated request payloads")
@allure.severity(allure.severity_level.NORMAL)
@allure.tag("wallet", "manager", "api-contract", "unit")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
class TestWalletAndManagerRoutes(unittest.IsolatedAsyncioTestCase):
    async def test_create_wallet_rejects_unknown_user_before_service_call(self) -> None:
        create_mock = AsyncMock()

        with (
            patch("app.api.routes.wallet.get_user", new=AsyncMock(return_value=None)),
            patch("app.api.routes.wallet.create_wallet_service", new=create_mock),
        ):
            with pytest.raises(HTTPException) as exc:
                await wallet_routes.create_user_wallet(
                    payload=WalletCreateWithoutUser(name="Family", currency=Currency.PLN),
                    user_id=uuid4(),
                    session=_session(),
                )

        assert exc.value.status_code == 400
        create_mock.assert_not_awaited()

    async def test_create_wallet_merges_authenticated_user_into_payload(self) -> None:
        user_id = uuid4()
        wallet_id = uuid4()

        async def create_wallet(_session, data):
            assert data.user_id == user_id
            assert data.name == "Family"
            return SimpleNamespace(id=wallet_id, user_id=user_id, name=data.name, currency=data.currency)

        with (
            patch("app.api.routes.wallet.get_user", new=AsyncMock(return_value=SimpleNamespace(id=user_id))),
            patch("app.api.routes.wallet.create_wallet_service", new=AsyncMock(side_effect=create_wallet)),
        ):
            response = await wallet_routes.create_user_wallet(
                payload=WalletCreateWithoutUser(name="Family", currency=Currency.PLN),
                user_id=user_id,
                session=_session(),
            )

        assert response.id == wallet_id
        assert response.name == "Family"

    async def test_delete_wallet_returns_not_found_when_service_refuses_delete(self) -> None:
        user_id = uuid4()

        with (
            patch("app.api.routes.wallet.get_user", new=AsyncMock(return_value=SimpleNamespace(id=user_id))),
            patch("app.api.routes.wallet.delete_wallet_service", new=AsyncMock(return_value=False)),
        ):
            with pytest.raises(HTTPException) as exc:
                await wallet_routes.delete_user_wallet(wallet_id=uuid4(), user_id=user_id, session=_session())

        assert exc.value.status_code == 404

    async def test_rename_wallet_returns_lightweight_wallet_contract(self) -> None:
        wallet_id = uuid4()
        user_id = uuid4()

        with patch(
            "app.api.routes.wallet.rename_wallet_service",
            new=AsyncMock(return_value=SimpleNamespace(id=wallet_id, name="Renamed")),
        ) as rename_mock:
            response = await wallet_routes.api_rename_wallet(
                wallet_id=wallet_id,
                payload=WalletRenameIn(name="Renamed"),
                user_id=user_id,
                session=_session(),
            )

        assert response.id == wallet_id
        assert response.name == "Renamed"
        rename_mock.assert_awaited_once_with(session=ANY, user_id=user_id, wallet_id=wallet_id, name="Renamed")

    async def test_manager_tree_passes_currency_rates_and_month_window_to_service(self) -> None:
        user_id = uuid4()
        stock_client = Mock()
        payload = WalletManagerTreeIn(months=6, currency_rate={"USD": Decimal("4.00")})
        expected = [
            {
                "id": str(uuid4()),
                "name": "Main",
                "base_ccy": "PLN",
            }
        ]

        with patch("app.api.routes.wallet_manager.get_wallet_manager_tree_service", new=AsyncMock(return_value=expected)) as service:
            response = await manager_routes.wallet_manager_tree(
                payload=payload,
                user_id=user_id,
                session=_session(),
                stock_client=stock_client,
            )

        assert response == expected
        service.assert_awaited_once_with(
            session=ANY,
            user_id=user_id,
            months=6,
            stock_client=stock_client,
            currency_rate={"USD": Decimal("4.00")},
        )

    async def test_monthly_snapshot_response_exposes_upsert_counts(self) -> None:
        user_id = uuid4()
        payload = CreateMonthlySnapshotIn(month_key="2026-06", currency_rate={"USD": Decimal("4.00")})

        with patch(
            "app.api.routes.wallet_manager.create_monthly_snapshot_for_user_service",
            new=AsyncMock(return_value=("2026-06", True, 2, 1, 3, 4)),
        ) as service:
            response = await manager_routes.api_create_monthly_snapshot(
                payload=payload,
                user_id=user_id,
                session=_session(),
                stock_client=Mock(),
            )

        assert response.ok is True
        assert response.month_key == "2026-06"
        assert response.dep_upserted == 2
        assert response.re_upserted == 4
        service.assert_awaited_once()
