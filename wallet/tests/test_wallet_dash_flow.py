from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4
import unittest

import allure
import pytest

from app.api.services.wallet import dash_flow_8m
from app.models.enums import Currency

pytestmark = pytest.mark.unit


@allure.epic("Unit Tests")
@allure.feature("Wallet")
@allure.story("Dashboard flow separates taxes from expenses")
@allure.severity(allure.severity_level.CRITICAL)
@allure.tag("wallet", "transactions", "money", "financial-data")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
@allure.description(
    "Verifies that transaction status TAXES is exposed as a separate Dash Flow "
    "series, so the frontend can reduce profit by taxes without mixing them into "
    "ordinary expenses."
)
class WalletDashFlowUnitTests(unittest.IsolatedAsyncioTestCase):
    async def test_dash_flow_maps_tax_status_to_separate_currency_bucket(self) -> None:
        wallet = Mock(id=uuid4())
        session = Mock()
        may = datetime(2026, 5, 1, tzinfo=timezone.utc)
        june = datetime(2026, 6, 1, tzinfo=timezone.utc)

        with (
            patch(
                "app.api.services.wallet.last_n_month_starts",
                return_value=[may, june],
            ),
            patch("app.api.services.wallet.month_floor", return_value=june),
            patch(
                "app.api.services.wallet.sum_income_expense_for_wallet_month_range",
                new=AsyncMock(
                    return_value=[
                        (may, "INCOME", Currency.PLN, Decimal("1000.00")),
                        (may, "EXPENSE", Currency.PLN, Decimal("-300.00")),
                        (may, "TAXES", Currency.PLN, Decimal("-190.00")),
                    ],
                ),
            ),
            patch(
                "app.api.services.wallet.sum_capital_gains_for_wallet_month_range",
                new=AsyncMock(return_value=[(may, Currency.PLN, Decimal("50.00"))]),
            ),
        ):
            flow = await dash_flow_8m(session, wallet)

        may_flow = flow[0]
        self.assertEqual(may_flow.month, "2026-05")
        self.assertEqual(may_flow.income_by_currency[Currency.PLN], Decimal("1000.00"))
        self.assertEqual(may_flow.expense_by_currency[Currency.PLN], Decimal("-300.00"))
        self.assertEqual(may_flow.tax_by_currency[Currency.PLN], Decimal("-190.00"))
        self.assertEqual(may_flow.capital_by_currency[Currency.PLN], Decimal("50.00"))
        self.assertEqual(flow[1].tax_by_currency, {})
