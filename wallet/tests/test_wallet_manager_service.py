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
from app.models.enums import AccountType, Currency, InstrumentCurrency

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
            patch("app.api.services.wallet_manager_service.list_cash_monthly_snapshots", new=AsyncMock(return_value=[])),
            patch("app.api.services.wallet_manager_service.list_cash_holdings_for_wallets", new=AsyncMock(return_value=[])),
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
        brokerage_cash_id = uuid4()
        brokerage_id = uuid4()
        holding_id = uuid4()
        month = "2026-05"
        wallet = SimpleNamespace(id=wallet_id, name="Main", currency=Currency.PLN)
        deposit = SimpleNamespace(
            id=deposit_id,
            wallet_id=wallet_id,
            currency=Currency.PLN,
            account_type=AccountType.CURRENT,
            balance=SimpleNamespace(available=Decimal("100.00")),
        )
        brokerage_cash = SimpleNamespace(
            id=brokerage_cash_id,
            wallet_id=wallet_id,
            currency=Currency.PLN,
            account_type=AccountType.BROKERAGE,
            balance=SimpleNamespace(available=Decimal("25.00")),
        )
        brokerage = SimpleNamespace(id=brokerage_id, wallet_id=wallet_id)
        link = SimpleNamespace(brokerage_account_id=brokerage_id, deposit_account_id=brokerage_cash_id)
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
                new=AsyncMock(return_value=[deposit, brokerage_cash]),
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
            patch("app.api.services.wallet_manager_service.list_cash_holdings_for_wallets", new=AsyncMock(return_value=[])),
        ):
            result = await create_monthly_snapshot_for_user_service(
                session=session,
                user_id=user_id,
                month_key_snap=month,
                currency_rate={"USD/PLN": Decimal("4.00")},
                stock_client=stock_client,
            )

        self.assertEqual(result, (month, True, 1, 1, 0, 0, 0))
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
            cash=Decimal("25.00"),
            stocks=Decimal("60.00"),
        )
        stock_client.get_latest_quotes_for_symbols.assert_awaited_once_with(symbols=["PKO"])
        stock_client.sync_daily_candles.assert_awaited_once_with("CPIYPL.M")


OCT_FX = {
    "EUR/PLN": Decimal("4.3745"),
    "GBP/PLN": Decimal("5.1353"),
    "USD/PLN": Decimal("3.8881"),
}


def _tree_patches(wallet, cash_rows, cash_snaps, fx_rows=()):
    prefix = "app.api.services.wallet_manager_service."
    empty = AsyncMock(return_value=[])
    return [
        patch(prefix + "list_wallets", new=AsyncMock(return_value=[wallet])),
        patch(prefix + "list_fx_rows_for_months", new=AsyncMock(return_value=list(fx_rows))),
        patch(prefix + "list_deposit_accounts_for_wallets", new=empty),
        patch(prefix + "count_transactions_since", new=AsyncMock(return_value={})),
        patch(prefix + "list_deposit_monthly_snapshots", new=empty),
        patch(prefix + "list_brokerage_accounts", new=empty),
        patch(prefix + "count_brokerage_events_since", new=AsyncMock(return_value={})),
        patch(prefix + "list_brokerage_monthly_snapshots", new=empty),
        patch(prefix + "list_brokerage_deposit_links", new=empty),
        patch(prefix + "list_holdings", new=empty),
        patch(prefix + "list_metal_holdings_by_wallet", new=empty),
        patch(prefix + "list_real_estates", new=empty),
        patch(prefix + "list_metal_monthly_snapshots", new=empty),
        patch(prefix + "list_real_estate_monthly_snapshots", new=empty),
        patch(prefix + "list_cash_monthly_snapshots", new=AsyncMock(return_value=cash_snaps)),
        patch(prefix + "list_cash_holdings_for_wallets", new=AsyncMock(return_value=cash_rows)),
    ]


def _cash(wallet_id, name, amount, currency):
    return SimpleNamespace(id=uuid4(), wallet_id=wallet_id, name=name, amount=Decimal(amount), currency=currency)


@allure.epic("Unit Tests")
@allure.feature("Wallet")
@allure.story("Wallet manager snapshots include physical cash")
@allure.severity(allure.severity_level.CRITICAL)
@allure.tag("wallet", "snapshots", "cash", "money", "fx", "financial-data")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
@allure.description(
    "Physical cash is stored in monthly snapshots in its original currency and is "
    "included in the wallet-manager current value and snapshot totals. Scenario: "
    "226.50 PLN + 1092.00 PLN + 196.70 EUR + 130.00 GBP with EUR/PLN 4.3745 and "
    "GBP/PLN 5.1353 equals 2846.55 PLN."
)
class WalletManagerPhysicalCashTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.wallet_id = uuid4()
        self.wallet = SimpleNamespace(id=self.wallet_id, name="FUNDUSZ Rodzinny", currency=Currency.PLN)
        self.cash_rows = [
            _cash(self.wallet_id, "Edyty Portfel", "226.50", InstrumentCurrency.PLN),
            _cash(self.wallet_id, "Artur Portfel", "1092.00", InstrumentCurrency.PLN),
            _cash(self.wallet_id, "Euro", "196.70", InstrumentCurrency.EUR),
            _cash(self.wallet_id, "funty", "130.00", InstrumentCurrency.GBP),
        ]

    async def test_create_monthly_snapshot_upserts_physical_cash_in_original_currency(self) -> None:
        session = Mock()
        session.begin.return_value = _AsyncContext()
        stock_client = Mock(get_latest_quotes_for_symbols=AsyncMock(return_value={}), sync_daily_candles=AsyncMock())
        prefix = "app.api.services.wallet_manager_service."

        with (
            patch(prefix + "upsert_fx_monthly_snapshot_uow", new=AsyncMock()),
            patch(prefix + "list_wallets", new=AsyncMock(return_value=[self.wallet])),
            patch(prefix + "list_deposit_accounts_for_wallets", new=AsyncMock(return_value=[])),
            patch(prefix + "list_brokerage_accounts", new=AsyncMock(return_value=[])),
            patch(prefix + "list_brokerage_deposit_links", new=AsyncMock(return_value=[])),
            patch(prefix + "list_holdings", new=AsyncMock(return_value=[])),
            patch(prefix + "list_metal_holdings_by_wallet", new=AsyncMock(return_value=[])),
            patch(prefix + "list_real_estates", new=AsyncMock(return_value=[])),
            patch(prefix + "list_cash_holdings_for_wallets", new=AsyncMock(return_value=self.cash_rows)),
            patch(prefix + "upsert_cash_monthly_snapshot", new=AsyncMock()) as cash_upsert,
        ):
            result = await create_monthly_snapshot_for_user_service(
                session=session,
                user_id=uuid4(),
                month_key_snap="2026-10",
                currency_rate={k: str(v) for k, v in OCT_FX.items()},
                stock_client=stock_client,
            )

        self.assertEqual(result, ("2026-10", True, 0, 0, 0, 0, 4))
        gbp_call = cash_upsert.await_args_list[3]
        self.assertEqual(gbp_call.kwargs, {
            "wallet_id": self.wallet_id,
            "cash_holding_id": self.cash_rows[3].id,
            "month_key": "2026-10",
            "currency": InstrumentCurrency.GBP,
            "value": Decimal("130.00"),
        })

    async def test_create_monthly_snapshot_without_wallets_returns_zero_counts(self) -> None:
        session = Mock()
        session.begin.return_value = _AsyncContext()

        with (
            patch("app.api.services.wallet_manager_service.upsert_fx_monthly_snapshot_uow", new=AsyncMock()),
            patch("app.api.services.wallet_manager_service.list_wallets", new=AsyncMock(return_value=[])),
        ):
            result = await create_monthly_snapshot_for_user_service(
                session=session,
                user_id=uuid4(),
                month_key_snap="2026-10",
                currency_rate={},
                stock_client=Mock(),
            )

        self.assertEqual(result, ("2026-10", True, 0, 0, 0, 0, 0))

    async def test_tree_includes_current_physical_cash_and_snapshot_cash_in_wallet_currency(self) -> None:
        cash_snaps = [
            SimpleNamespace(wallet_id=self.wallet_id, month_key=mk, value=c.amount, currency=c.currency)
            for c in self.cash_rows
            for mk in ["2026-10"]
        ]
        fx_row = SimpleNamespace(month_key="2026-10", rates_json={k: str(v) for k, v in OCT_FX.items()})
        patches = _tree_patches(self.wallet, self.cash_rows, cash_snaps, fx_rows=[fx_row])

        with patch("app.api.services.wallet_manager_service.last_n_month_keys", return_value=["2026-10"]):
            for p in patches:
                p.start()
            try:
                tree = await get_wallet_manager_tree_service(
                    session=Mock(),
                    user_id=uuid4(),
                    months=1,
                    stock_client=Mock(get_latest_quotes_for_symbols=AsyncMock(return_value={})),
                    currency_rate={k: str(v) for k, v in OCT_FX.items()},
                )
            finally:
                for p in patches:
                    p.stop()

        physical = tree[0]["physical_cash"]
        self.assertEqual(physical["count"], 4)
        self.assertEqual(physical["ccy"], "PLN")
        self.assertEqual(physical["value"].quantize(Decimal("0.01")), Decimal("2846.55"))
        self.assertEqual(physical["items"][3]["amount_ccy"], "GBP")
        self.assertEqual(tree[0]["snapshots"]["2026-10"]["cash_physical"].quantize(Decimal("0.01")), Decimal("2846.55"))

    async def test_tree_flags_cash_without_fx_rate_instead_of_counting_it_at_face_value(self) -> None:
        patches = _tree_patches(self.wallet, [self.cash_rows[3]], [])

        for p in patches:
            p.start()
        try:
            tree = await get_wallet_manager_tree_service(
                session=Mock(),
                user_id=uuid4(),
                months=1,
                stock_client=Mock(get_latest_quotes_for_symbols=AsyncMock(return_value={})),
                currency_rate={},
            )
        finally:
            for p in patches:
                p.stop()

        physical = tree[0]["physical_cash"]
        self.assertEqual(physical["value"], Decimal("0"))
        self.assertEqual(physical["health"]["missing_fx"], 1)

