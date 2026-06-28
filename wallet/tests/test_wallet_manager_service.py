from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4
import unittest

import allure
import pytest

from app.api.services.wallet_manager_service import (
    create_monthly_snapshot_for_user_service,
    get_wallet_manager_tree_service,
)
from app.models.enums import Currency

pytestmark = pytest.mark.unit


class _AsyncContext:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


@allure.epic("Unit Tests")
@allure.feature("Wallet")
@allure.story("Wallet manager brokerage aggregation loads all holdings")
@allure.severity(allure.severity_level.CRITICAL)
@allure.tag("wallet", "brokerage", "holdings", "money", "financial-data")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
@allure.description(
    "Protects brokerage account valuation in /wallet-manager from the default holding "
    "page limit. The manager must aggregate every holding, not only the first page."
)
class WalletManagerServiceUnitTests(unittest.IsolatedAsyncioTestCase):
    async def test_wallet_manager_loads_brokerage_holdings_without_default_limit(self) -> None:
        session = Mock()
        user_id = uuid4()
        wallet_id = uuid4()
        brokerage_id = uuid4()
        wallet = SimpleNamespace(id=wallet_id, name="FUNDUSZ Rodzinny", currency=Currency.PLN)
        brokerage = SimpleNamespace(id=brokerage_id, wallet_id=wallet_id, name="Maklerskie ING Artur")
        stock_client = Mock(get_latest_quotes_for_symbols=AsyncMock(return_value={}))

        with (
            patch("app.api.services.wallet_manager_service.list_wallets", new=AsyncMock(return_value=[wallet])),
            patch("app.api.services.wallet_manager_service.list_fx_rows_for_months", new=AsyncMock(return_value=[])),
            patch("app.api.services.wallet_manager_service.list_deposit_accounts_for_wallets", new=AsyncMock(return_value=[])),
            patch("app.api.services.wallet_manager_service.count_transactions_since", new=AsyncMock(return_value={})),
            patch("app.api.services.wallet_manager_service.list_deposit_monthly_snapshots", new=AsyncMock(return_value=[])),
            patch("app.api.services.wallet_manager_service.list_brokerage_accounts", new=AsyncMock(return_value=[brokerage])),
            patch("app.api.services.wallet_manager_service.count_brokerage_events_since", new=AsyncMock(return_value={})),
            patch("app.api.services.wallet_manager_service.list_brokerage_monthly_snapshots", new=AsyncMock(return_value=[])),
            patch("app.api.services.wallet_manager_service.list_brokerage_deposit_links", new=AsyncMock(return_value=[])),
            patch("app.api.services.wallet_manager_service.list_holdings", new=AsyncMock(return_value=[])) as list_holdings_mock,
            patch("app.api.services.wallet_manager_service.list_metal_holdings_by_wallet", new=AsyncMock(return_value=[])),
            patch("app.api.services.wallet_manager_service.list_real_estates", new=AsyncMock(return_value=[])),
            patch("app.api.services.wallet_manager_service.list_metal_monthly_snapshots", new=AsyncMock(return_value=[])),
            patch("app.api.services.wallet_manager_service.list_real_estate_monthly_snapshots", new=AsyncMock(return_value=[])),
        ):
            tree = await get_wallet_manager_tree_service(
                session=session,
                user_id=user_id,
                months=1,
                stock_client=stock_client,
                currency_rate={},
            )

        list_holdings_mock.assert_awaited_once_with(
            session,
            account_ids=[brokerage_id],
            with_relations=True,
            limit=None,
        )
        brokerage_node = tree[0]["brokerage_accounts"][0]
        self.assertEqual(brokerage_node["id"], str(brokerage_id))
        self.assertEqual(brokerage_node["positions_count"], 0)

    async def test_create_monthly_snapshot_persists_deposit_brokerage_fx_and_syncs_cpi(self) -> None:
        session = Mock()
        session.begin.return_value = _AsyncContext()
        user_id = uuid4()
        wallet_id = uuid4()
        deposit_id = uuid4()
        brokerage_id = uuid4()
        holding_id = uuid4()
        month = "2026-05"
        wallet = SimpleNamespace(id=wallet_id, name="Main", currency=Currency.PLN)
        deposit = SimpleNamespace(
            id=deposit_id,
            wallet_id=wallet_id,
            currency=Currency.PLN,
            balance=SimpleNamespace(available=Decimal("100.00")),
        )
        brokerage = SimpleNamespace(id=brokerage_id, wallet_id=wallet_id)
        link = SimpleNamespace(brokerage_account_id=brokerage_id, deposit_account_id=deposit_id)
        instrument = SimpleNamespace(symbol="PKO", currency=Currency.PLN)
        holding = SimpleNamespace(
            id=holding_id,
            account_id=brokerage_id,
            quantity=Decimal("3"),
            avg_cost=Decimal("10"),
            instrument=instrument,
        )
        stock_client = Mock(
            get_latest_quotes_for_symbols=AsyncMock(
                return_value={
                    "PKO": SimpleNamespace(price=Decimal("20.00"), currency=Currency.PLN),
                },
            ),
            sync_daily_candles=AsyncMock(),
        )

        with (
            patch("app.api.services.wallet_manager_service.upsert_fx_monthly_snapshot_uow", new=AsyncMock()) as fx_upsert,
            patch("app.api.services.wallet_manager_service.list_wallets", new=AsyncMock(return_value=[wallet])),
            patch(
                "app.api.services.wallet_manager_service.list_deposit_accounts_for_wallets",
                new=AsyncMock(return_value=[deposit]),
            ),
            patch(
                "app.api.services.wallet_manager_service.upsert_depacc_monthly_snapshot_uow",
                new=AsyncMock(),
            ) as dep_upsert,
            patch("app.api.services.wallet_manager_service.list_brokerage_accounts", new=AsyncMock(return_value=[brokerage])),
            patch(
                "app.api.services.wallet_manager_service.list_brokerage_deposit_links",
                new=AsyncMock(return_value=[link]),
            ),
            patch("app.api.services.wallet_manager_service.list_holdings", new=AsyncMock(return_value=[holding])),
            patch(
                "app.api.services.wallet_manager_service.upsert_broacc_monthly_snapshot_uow",
                new=AsyncMock(),
            ) as bro_upsert,
            patch("app.api.services.wallet_manager_service.list_metal_holdings_by_wallet", new=AsyncMock(return_value=[])),
            patch("app.api.services.wallet_manager_service.list_real_estates", new=AsyncMock(return_value=[])),
        ):
            result = await create_monthly_snapshot_for_user_service(
                session=session,
                user_id=user_id,
                month_key_snap=month,
                currency_rate={"USD/PLN": Decimal("4.00")},
                stock_client=stock_client,
            )

        self.assertEqual(result, (month, True, 1, 1, 0, 0))
        fx_upsert.assert_awaited_once_with(session, month_key=month, rates_json={"USD/PLN": Decimal("4.00")})
        dep_upsert.assert_awaited_once_with(
            session,
            wallet_id=wallet_id,
            account_id=deposit_id,
            month_key=month,
            currency=Currency.PLN,
            available=Decimal("100.00"),
        )
        bro_upsert.assert_awaited_once_with(
            session,
            wallet_id=wallet_id,
            brokerage_account_id=brokerage_id,
            month_key=month,
            currency="PLN",
            cash=Decimal("100.00"),
            stocks=Decimal("60.00"),
        )
        stock_client.get_latest_quotes_for_symbols.assert_awaited_once_with(symbols=["PKO"])
        stock_client.sync_daily_candles.assert_awaited_once_with("CPIYPL.M")
