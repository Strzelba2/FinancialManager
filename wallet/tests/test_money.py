from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
import unittest

import allure
import pytest

from app.models.enums import AccountType, BrokerageEventKind
from app.utils.money import (
    account_type_allows_negative_balance,
    compute_cash_effect,
    dec,
    fx_convert,
    safe_ccy,
)

pytestmark = pytest.mark.unit


@allure.epic("Unit Tests")
@allure.feature("Wallet")
@allure.story("Money utility behavior is deterministic")
@allure.severity(allure.severity_level.BLOCKER)
@allure.tag("money", "financial-data")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
@allure.description(
    "Core money calculation helpers used in every brokerage and transaction flow. "
    "Verifies cash effect sign for buy/sell, FX conversion with missing and available "
    "rates, currency enum extraction, account balance policy, and None-to-zero "
    "coercion for Decimal fields."
)
class MoneyUtilsTests(unittest.TestCase):
    def test_compute_cash_effect_for_buy_is_negative(self) -> None:
        result = compute_cash_effect(BrokerageEventKind.TRADE_BUY, Decimal("2"), Decimal("15.50"))

        self.assertEqual(result, Decimal("-31.00"))

    def test_compute_cash_effect_for_sell_is_positive(self) -> None:
        result = compute_cash_effect(BrokerageEventKind.TRADE_SELL, Decimal("2"), Decimal("15.50"))

        self.assertEqual(result, Decimal("31.00"))

    def test_compute_cash_effect_for_dividend_is_positive(self) -> None:
        result = compute_cash_effect(BrokerageEventKind.DIV, Decimal("3"), Decimal("2.50"))

        self.assertEqual(result, Decimal("7.50"))

    def test_compute_cash_effect_for_non_cash_event_is_zero(self) -> None:
        result = compute_cash_effect(BrokerageEventKind.SPLIT, Decimal("3"), Decimal("2.50"))

        self.assertEqual(result, Decimal("0"))

    def test_fx_convert_returns_none_when_rate_is_missing(self) -> None:
        result = fx_convert(Decimal("100"), "USD", "PLN", {})

        self.assertIsNone(result)

    def test_fx_convert_uses_available_rate(self) -> None:
        result = fx_convert(Decimal("100"), "USD", "PLN", {"USD/PLN": "4.02"})

        self.assertEqual(result, Decimal("402.00"))

    def test_fx_convert_returns_amount_when_currency_matches(self) -> None:
        result = fx_convert(Decimal("100"), "PLN", "PLN", {})

        self.assertEqual(result, Decimal("100"))

    def test_safe_ccy_prefers_enum_value(self) -> None:
        result = safe_ccy(SimpleNamespace(value="EUR"), "PLN")

        self.assertEqual(result, "EUR")

    def test_safe_ccy_uses_fallback_for_none(self) -> None:
        self.assertEqual(safe_ccy(None, "PLN"), "PLN")

    def test_dec_turns_none_into_zero(self) -> None:
        self.assertEqual(dec(None), Decimal("0"))

    def test_account_type_allows_negative_balance_only_for_credit(self) -> None:
        self.assertTrue(account_type_allows_negative_balance(AccountType.CREDIT))
        self.assertTrue(account_type_allows_negative_balance("CREDIT"))
        self.assertFalse(account_type_allows_negative_balance(AccountType.CURRENT))
        self.assertFalse(account_type_allows_negative_balance(AccountType.SAVINGS))
        self.assertFalse(account_type_allows_negative_balance(None))
