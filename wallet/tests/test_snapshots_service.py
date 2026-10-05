from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4
import unittest

import allure
import pytest

from app.api.services.snapshots_service import sum_snapshots_into_monthly_totals
from app.models.enums import Currency, InstrumentCurrency

pytestmark = pytest.mark.unit


@allure.epic("Unit Tests")
@allure.feature("Wallet")
@allure.story("Wallet dashboard snapshot totals aggregate financial assets")
@allure.severity(allure.severity_level.CRITICAL)
@allure.tag("wallet", "snapshots", "money", "fx", "financial-data")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
@allure.description(
    "Verifies the money aggregation used by /wallet dashboard assets_8m_total. "
    "Deposit cash, brokerage cash and positions, metals, and real estate are summed "
    "per wallet/month in the selected currency, with missing FX rates excluded."
)
class SnapshotMonthlyTotalsTests(unittest.TestCase):
    def test_sums_all_snapshot_asset_classes_in_pln(self) -> None:
        wallet_id = uuid4()
        month = "2026-05"

        totals = sum_snapshots_into_monthly_totals(
            fx_by_month={},
            target_ccy="PLN",
            dep_rows=[
                SimpleNamespace(wallet_id=wallet_id, month_key=month, currency=Currency.PLN, available=Decimal("100.00")),
            ],
            bro_rows=[
                SimpleNamespace(
                    wallet_id=wallet_id,
                    month_key=month,
                    currency=Currency.PLN,
                    cash=Decimal("50.00"),
                    stocks=Decimal("150.00"),
                ),
            ],
            metal_rows=[
                SimpleNamespace(wallet_id=wallet_id, month_key=month, currency=Currency.PLN, value=Decimal("25.00")),
            ],
            re_rows=[
                SimpleNamespace(wallet_id=wallet_id, month_key=month, currency=Currency.PLN, value=Decimal("500.00")),
            ],
        )

        self.assertEqual(totals[wallet_id][month], Decimal("825.00"))

    def test_converts_foreign_currency_snapshots_to_target_currency(self) -> None:
        wallet_id = uuid4()
        month = "2026-05"

        totals = sum_snapshots_into_monthly_totals(
            fx_by_month={month: {"USD/PLN": "4.00"}},
            target_ccy="PLN",
            dep_rows=[
                SimpleNamespace(wallet_id=wallet_id, month_key=month, currency=Currency.USD, available=Decimal("10.00")),
            ],
            bro_rows=[
                SimpleNamespace(
                    wallet_id=wallet_id,
                    month_key=month,
                    currency=Currency.USD,
                    cash=Decimal("5.00"),
                    stocks=Decimal("15.00"),
                ),
            ],
            metal_rows=[],
            re_rows=[],
        )

        self.assertEqual(totals[wallet_id][month], Decimal("120.0000"))

    def test_missing_fx_rate_skips_foreign_snapshot_without_inflating_total(self) -> None:
        wallet_id = uuid4()
        month = "2026-05"

        totals = sum_snapshots_into_monthly_totals(
            fx_by_month={month: {}},
            target_ccy="PLN",
            dep_rows=[
                SimpleNamespace(wallet_id=wallet_id, month_key=month, currency=Currency.USD, available=Decimal("10.00")),
                SimpleNamespace(wallet_id=wallet_id, month_key=month, currency=Currency.PLN, available=Decimal("20.00")),
            ],
            bro_rows=[],
            metal_rows=[],
            re_rows=[],
        )

        self.assertEqual(totals[wallet_id][month], Decimal("20.00"))

    def test_includes_physical_cash_in_original_currency(self) -> None:
        wallet_id = uuid4()
        month = "2026-10"
        cash = [
            ("226.50", InstrumentCurrency.PLN),
            ("1092.00", InstrumentCurrency.PLN),
            ("196.70", InstrumentCurrency.EUR),
            ("130.00", InstrumentCurrency.GBP),
        ]

        totals = sum_snapshots_into_monthly_totals(
            fx_by_month={month: {"EUR/PLN": "4.3745", "GBP/PLN": "5.1353"}},
            target_ccy="PLN",
            dep_rows=[
                SimpleNamespace(wallet_id=wallet_id, month_key=month, currency=Currency.PLN, available=Decimal("875661.99")),
            ],
            bro_rows=[],
            metal_rows=[],
            re_rows=[],
            cash_rows=[
                SimpleNamespace(wallet_id=wallet_id, month_key=month, currency=ccy, value=Decimal(amount))
                for amount, ccy in cash
            ],
        )

        # 1318.50 PLN + 196.70 EUR * 4.3745 + 130.00 GBP * 5.1353 = 2846.55 PLN of physical cash.
        self.assertEqual(totals[wallet_id][month].quantize(Decimal("0.01")), Decimal("878508.54"))

