from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4
import unittest

import allure
import pytest

from app.api.services.wallet_manager_service import get_wallet_manager_tree_service
from app.models.enums import Currency

pytestmark = pytest.mark.unit


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
