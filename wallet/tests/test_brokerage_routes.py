from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4
import unittest

import allure
import pytest
from fastapi import HTTPException, status

from app.api.routes import account as account_routes
from app.api.routes import brokerage as brokerage_routes
from app.crud.holding_crud import HoldingQuantityExceeded
from app.models.enums import AccountType, BrokerageEventKind, Currency
from app.schemas.response import BatchUpdateBrokerageEventsRequest, BrokerageEventsImportSummary
from app.schemas.schemas import (
    AccountCreation,
    BrokerageCashAccountCreate,
    BrokerageCashLinksEnsureRequest,
    BrokerageEventCreate,
    BrokerageEventImportRow,
    BrokerageEventsImportRequest,
    BrokerageHistoryImportRequest,
    BrokerageHistoryImportRow,
)

pytestmark = pytest.mark.unit


class _Begin:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _session() -> Mock:
    session = Mock()
    session.rollback = AsyncMock()
    session.begin = Mock(return_value=_Begin())
    return session


def _event_payload(
    brokerage_account_id,
    symbol: str = "PKO",
    kind: BrokerageEventKind = BrokerageEventKind.TRADE_BUY,
) -> BrokerageEventCreate:
    return BrokerageEventCreate(
        brokerage_account_id=brokerage_account_id,
        instrument_symbol=symbol,
        instrument_mic="XWAR",
        instrument_name=symbol,
        kind=kind,
        quantity=Decimal("10"),
        price=Decimal("12.50"),
        currency=Currency.PLN,
        split_ratio=Decimal("0"),
        trade_at=datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc),
    )


@allure.epic("Unit Tests")
@allure.feature("Wallet")
@allure.story("Brokerage route handlers preserve ownership and import diagnostics")
@allure.severity(allure.severity_level.CRITICAL)
@allure.tag("wallet", "brokerage", "api-contract", "financial-data", "unit")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
@allure.description(
    "Covers route-level behavior that component tests exercise from outside: user "
    "ownership checks, duplicate brokerage imports, batch routes and cash-link setup."
)
class TestBrokerageRouteHandlers(unittest.IsolatedAsyncioTestCase):
    async def test_create_brokerage_event_checks_owner_and_returns_created_event(self) -> None:
        user_id = uuid4()
        brokerage_account_id = uuid4()
        instrument_id = uuid4()
        event_id = uuid4()
        session = _session()
        payload = _event_payload(brokerage_account_id)
        stock_client = Mock()
        event = SimpleNamespace(
            id=event_id,
            brokerage_account_id=brokerage_account_id,
            instrument_id=instrument_id,
            kind=payload.kind,
            quantity=payload.quantity,
            price=payload.price,
            currency=payload.currency,
            split_ratio=payload.split_ratio,
            note=None,
            target_instrument_id=None,
            trade_at=payload.trade_at,
        )

        with (
            patch("app.api.routes.brokerage.get_user", new=AsyncMock(return_value=SimpleNamespace(id=user_id))),
            patch(
                "app.api.routes.brokerage.get_brokerage_account_for_user",
                new=AsyncMock(return_value=SimpleNamespace(id=brokerage_account_id)),
            ),
            patch(
                "app.api.routes.brokerage.create_brokerage_event_and_update_holding",
                new=AsyncMock(return_value=(event, None)),
            ) as create_mock,
        ):
            response = await brokerage_routes.create_brokerage_event_endpoint(
                payload=payload,
                user_id=user_id,
                session=session,
                stock_client=stock_client,
            )

        assert response.id == event_id
        assert response.instrument_id == instrument_id
        assert response.holding is None
        create_mock.assert_awaited_once()

    async def test_import_brokerage_events_reports_created_duplicate_and_oversell_rows(self) -> None:
        user_id = uuid4()
        brokerage_account_id = uuid4()
        session = _session()
        stock_client = Mock()
        payload = BrokerageEventsImportRequest(
            brokerage_account_id=brokerage_account_id,
            events=[
                BrokerageEventImportRow(
                    instrument_symbol="DUP",
                    instrument_mic="XWAR",
                    instrument_name="Duplicate",
                    kind=BrokerageEventKind.TRADE_BUY,
                    quantity=Decimal("1"),
                    price=Decimal("10"),
                    currency=Currency.PLN,
                    split_ratio=Decimal("0"),
                    trade_at=datetime(2026, 6, 3, 10, 0, tzinfo=timezone.utc),
                ),
                BrokerageEventImportRow(
                    instrument_symbol="OK",
                    instrument_mic="XWAR",
                    instrument_name="Created",
                    kind=BrokerageEventKind.TRADE_BUY,
                    quantity=Decimal("2"),
                    price=Decimal("11"),
                    currency=Currency.PLN,
                    split_ratio=Decimal("0"),
                    trade_at=datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc),
                ),
                BrokerageEventImportRow(
                    instrument_symbol="SELL",
                    instrument_mic="XWAR",
                    instrument_name="Oversell",
                    kind=BrokerageEventKind.TRADE_SELL,
                    quantity=Decimal("5"),
                    price=Decimal("12"),
                    currency=Currency.PLN,
                    split_ratio=Decimal("0"),
                    trade_at=datetime(2026, 6, 2, 10, 0, tzinfo=timezone.utc),
                ),
            ],
        )

        async def create_side_effect(_session, be_payload, creat_transaction, stock_client=None):
            assert creat_transaction is False
            assert stock_client is not None
            if be_payload.instrument_symbol == "DUP":
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="already exists")
            if be_payload.instrument_symbol == "SELL":
                raise HoldingQuantityExceeded(
                    payload=be_payload,
                    held_quantity=Decimal("0"),
                    requested_quantity=be_payload.quantity,
                )
            return SimpleNamespace(id=uuid4()), SimpleNamespace()

        with (
            patch("app.api.routes.brokerage.get_user", new=AsyncMock(return_value=SimpleNamespace(id=user_id))),
            patch(
                "app.api.routes.brokerage.get_brokerage_account_for_user",
                new=AsyncMock(return_value=SimpleNamespace(id=brokerage_account_id)),
            ),
            patch(
                "app.api.routes.brokerage.create_brokerage_event_and_update_holding",
                new=AsyncMock(side_effect=create_side_effect),
            ),
        ):
            summary = await brokerage_routes.import_brokerage_events_endpoint(
                payload=payload,
                user_id=user_id,
                session=session,
                stock_client=stock_client,
            )

        assert summary.total == 3
        assert summary.created == 1
        assert summary.skipped_duplicates == 1
        assert summary.failed == 1
        assert [row.status for row in summary.rows] == [
            "created",
            "failed",
            "skipped_duplicate",
        ]
        assert summary.rows[1].reason_code == "holding_quantity_exceeded"

    async def test_import_brokerage_events_rejects_conversion_rows_as_manual_actions(self) -> None:
        user_id = uuid4()
        brokerage_account_id = uuid4()
        session = _session()
        payload = BrokerageEventsImportRequest(
            brokerage_account_id=brokerage_account_id,
            events=[
                BrokerageEventImportRow(
                    instrument_symbol="WORK",
                    instrument_mic="XWAR",
                    instrument_name="WORKSERV SA",
                    kind=BrokerageEventKind.CONVERSION,
                    quantity=Decimal("1000"),
                    price=Decimal("0"),
                    currency=Currency.PLN,
                    split_ratio=Decimal("0.2"),
                    note="WORKSERV -> GIGROUP, scalenie 1:5",
                    trade_at=datetime(2026, 6, 2, 10, 0, tzinfo=timezone.utc),
                )
            ],
        )
        create_mock = AsyncMock()

        with (
            patch("app.api.routes.brokerage.get_user", new=AsyncMock(return_value=SimpleNamespace(id=user_id))),
            patch(
                "app.api.routes.brokerage.get_brokerage_account_for_user",
                new=AsyncMock(return_value=SimpleNamespace(id=brokerage_account_id)),
            ),
            patch(
                "app.api.routes.brokerage.create_brokerage_event_and_update_holding",
                new=create_mock,
            ),
        ):
            summary = await brokerage_routes.import_brokerage_events_endpoint(
                payload=payload,
                user_id=user_id,
                session=session,
            )

        assert summary.total == 1
        assert summary.created == 0
        assert summary.failed == 1
        assert summary.errors == [
            "Row 1: CONVERSION events must be created manually through holding actions."
        ]
        assert summary.rows[0].status == "failed"
        assert summary.rows[0].reason_code == "conversion_import_not_supported"
        assert summary.rows[0].message == "CONVERSION events must be created manually through holding actions."
        create_mock.assert_not_awaited()

    async def test_history_import_route_checks_owner_then_delegates_service(self) -> None:
        user_id = uuid4()
        brokerage_account_id = uuid4()
        session = _session()
        stock_client = Mock()
        payload = BrokerageHistoryImportRequest(
            brokerage_account_id=brokerage_account_id,
            rows=[
                BrokerageHistoryImportRow(
                    row_number=1,
                    operation_type="TRANSFER",
                    trade_at=datetime(2026, 6, 4, 10, 0, tzinfo=timezone.utc),
                    currency=Currency.PLN,
                    amount=Decimal("10.00"),
                    amount_after=Decimal("10.00"),
                    description="Wpłata",
                )
            ],
        )
        expected = BrokerageEventsImportSummary(total=1, created=1, failed=0, rows=[])

        with (
            patch("app.api.routes.brokerage.get_user", new=AsyncMock(return_value=SimpleNamespace(id=user_id))),
            patch(
                "app.api.routes.brokerage.get_brokerage_account_for_user",
                new=AsyncMock(return_value=SimpleNamespace(id=brokerage_account_id)),
            ),
            patch(
                "app.api.routes.brokerage.import_brokerage_history_service",
                new=AsyncMock(return_value=expected),
            ) as import_mock,
        ):
            response = await brokerage_routes.import_brokerage_history_endpoint(
                payload=payload,
                user_id=user_id,
                session=session,
                stock_client=stock_client,
            )

        assert response is expected
        import_mock.assert_awaited_once_with(
            session=session,
            user_id=user_id,
            payload=payload,
            stock_client=stock_client,
        )

    async def test_ensure_cash_links_reuses_existing_and_creates_missing_currency(self) -> None:
        user_id = uuid4()
        brokerage_account_id = uuid4()
        wallet_id = uuid4()
        bank_id = uuid4()
        existing_deposit_id = uuid4()
        created_deposit_id = uuid4()
        session = _session()
        payload = BrokerageCashLinksEnsureRequest(
            cash_accounts=[
                BrokerageCashAccountCreate(
                    currency=Currency.USD,
                    account_number="BOSSA-USD",
                    name="USD cash",
                ),
                BrokerageCashAccountCreate(
                    currency=Currency.EUR,
                    account_number="BOSSA-EUR",
                    name="EUR cash",
                ),
            ]
        )

        async def existing_side_effect(_session, brokerage_account_id, currency):
            if currency == Currency.USD:
                return SimpleNamespace(deposit_account_id=existing_deposit_id)
            return None

        with (
            patch(
                "app.api.routes.brokerage.get_user",
                new=AsyncMock(return_value=SimpleNamespace(id=user_id, username="artur")),
            ),
            patch(
                "app.api.routes.brokerage.get_brokerage_account_for_user",
                new=AsyncMock(
                    return_value=SimpleNamespace(
                        id=brokerage_account_id,
                        wallet_id=wallet_id,
                        bank_id=bank_id,
                        name="Bossa IKE",
                    )
                ),
            ),
            patch(
                "app.api.routes.brokerage.get_link_by_ba_and_currency",
                new=AsyncMock(side_effect=existing_side_effect),
            ),
            patch(
                "app.api.routes.brokerage.create_brokerage_cash_account_link_service",
                new=AsyncMock(return_value=SimpleNamespace(id=created_deposit_id, name="EUR cash")),
            ) as create_link_mock,
        ):
            response = await brokerage_routes.ensure_brokerage_cash_links(
                brokerage_account_id=brokerage_account_id,
                payload=payload,
                user_id=user_id,
                session=session,
                crypto=Mock(),
            )

        assert [item.created for item in response] == [False, True]
        assert response[0].deposit_account_id == existing_deposit_id
        assert response[1].deposit_account_id == created_deposit_id
        create_link_mock.assert_awaited_once()

    async def test_brokerage_list_patch_delete_and_account_delete_routes_delegate_with_user_scope(self) -> None:
        user_id = uuid4()
        event_id = uuid4()
        brokerage_account_id = uuid4()
        session = _session()

        event = Mock()
        event.model_dump.return_value = {
            "id": event_id,
            "brokerage_account_id": brokerage_account_id,
            "instrument_id": uuid4(),
            "kind": BrokerageEventKind.TRADE_BUY,
            "quantity": Decimal("1"),
            "price": Decimal("10"),
            "currency": Currency.PLN,
            "split_ratio": Decimal("0"),
            "note": None,
            "target_instrument_id": None,
            "trade_at": datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc),
        }
        listed_rows = [
            (
                event,
                SimpleNamespace(name="Makler"),
                SimpleNamespace(symbol="PKO", name="PKOBP"),
                SimpleNamespace(),
            )
        ]

        with (
            patch(
                "app.api.routes.brokerage.list_brokerage_accounts_for_user",
                new=AsyncMock(return_value=[SimpleNamespace(id=brokerage_account_id)]),
            ),
            patch(
                "app.api.routes.brokerage.list_brokerage_events_page",
                new=AsyncMock(return_value=(listed_rows, 1, 1, 40, {"PLN": Decimal("10")})),
            ),
            patch(
                "app.api.routes.brokerage.batch_patch_brokerage_events",
                new=AsyncMock(return_value=1),
            ),
            patch(
                "app.api.routes.brokerage.delete_brokerage_event_and_rebuild_holding",
                new=AsyncMock(return_value=True),
            ),
            patch("app.api.routes.brokerage.get_user", new=AsyncMock(return_value=SimpleNamespace(id=user_id))),
            patch(
                "app.api.routes.brokerage.get_brokerage_account_for_user",
                new=AsyncMock(return_value=SimpleNamespace(id=brokerage_account_id)),
            ),
            patch(
                "app.api.routes.brokerage.delete_brokerage_account_with_cash_accounts_service",
                new=AsyncMock(return_value=True),
            ),
        ):
            accounts = await brokerage_routes.get_brokerage_accounts_for_user(
                user_id=user_id,
                session=session,
            )
            page = await brokerage_routes.get_brokerage_events_page(
                user_id=user_id,
                session=session,
            )
            patched = await brokerage_routes.patch_brokerage_events_batch(
                BatchUpdateBrokerageEventsRequest(
                    items=[{"id": event_id, "note": "corrected"}]
                ),
                user_id=user_id,
                session=session,
            )
            deleted_event = await brokerage_routes.api_delete_brokerage_event(
                event_id=event_id,
                user_id=user_id,
                session=session,
            )
            deleted_account = await brokerage_routes.api_delete_brokerage_account(
                brokerage_account_id=brokerage_account_id,
                user_id=user_id,
                session=session,
            )

        assert accounts[0].id == brokerage_account_id
        assert page.total == 1
        assert page.items[0].instrument_symbol == "PKO"
        assert patched == {"updated": 1}
        assert deleted_event == {"ok": True}
        assert deleted_account == {"ok": True}


@allure.epic("Unit Tests")
@allure.feature("Wallet")
@allure.story("Account route rolls back brokerage account creation when cash subaccount setup fails")
@allure.severity(allure.severity_level.CRITICAL)
@allure.tag("wallet", "accounts", "brokerage", "financial-data", "unit")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
class TestAccountRouteBrokerageCreation(unittest.IsolatedAsyncioTestCase):
    async def test_brokerage_account_creation_cleans_up_deposit_accounts_when_extra_link_fails(self) -> None:
        user_id = uuid4()
        wallet_id = uuid4()
        bank_id = uuid4()
        primary_deposit_id = uuid4()
        brokerage_account_id = uuid4()
        extra_deposit_id = uuid4()
        session = _session()
        payload = AccountCreation(
            name="Bossa IKE",
            account_type=AccountType.BROKERAGE,
            currency=Currency.PLN,
            account_number="PLN-TECH",
            bank_id=bank_id,
            brokerage_cash_accounts=[
                BrokerageCashAccountCreate(
                    currency=Currency.USD,
                    account_number="USD-TECH",
                    name="USD cash",
                ),
                BrokerageCashAccountCreate(
                    currency=Currency.EUR,
                    account_number="EUR-TECH",
                    name="EUR cash",
                ),
            ],
        )

        async def extra_link_side_effect(**kwargs):
            if kwargs["cash_account"].currency == Currency.USD:
                return SimpleNamespace(id=extra_deposit_id)
            raise HTTPException(status_code=422, detail="invalid EUR link")

        with (
            patch(
                "app.api.routes.account.get_user",
                new=AsyncMock(return_value=SimpleNamespace(id=user_id, username="artur")),
            ),
            patch(
                "app.api.routes.account.get_wallet",
                new=AsyncMock(return_value=SimpleNamespace(id=wallet_id, user_id=user_id)),
            ),
            patch(
                "app.api.routes.account.create_deposit_account_service",
                new=AsyncMock(
                    return_value=SimpleNamespace(
                        id=primary_deposit_id,
                        name="Bossa IKE",
                        account_type=AccountType.BROKERAGE,
                        bank_id=bank_id,
                    )
                ),
            ),
            patch(
                "app.api.routes.account.create_brokeage_account_service",
                new=AsyncMock(return_value=SimpleNamespace(id=brokerage_account_id)),
            ),
            patch(
                "app.api.routes.account.create_brokerage_cash_account_link_service",
                new=AsyncMock(side_effect=extra_link_side_effect),
            ),
            patch("app.api.routes.account.delete_deposit_account", new=AsyncMock(return_value=True)) as delete_deposit_mock,
            patch("app.api.routes.account.delete_brokerage_account", new=AsyncMock(return_value=True)) as delete_brokerage_mock,
        ):
            with pytest.raises(HTTPException) as exc_info:
                await account_routes.create_account(
                    wallet_id=wallet_id,
                    payload=payload,
                    user_id=user_id,
                    session=session,
                    crypto=Mock(),
                )

        assert exc_info.value.status_code == 422
        deleted_ids = [call.kwargs["account_id"] for call in delete_deposit_mock.await_args_list]
        assert deleted_ids == [extra_deposit_id, primary_deposit_id]
        delete_brokerage_mock.assert_awaited_once_with(
            session=session,
            account_id=brokerage_account_id,
        )
