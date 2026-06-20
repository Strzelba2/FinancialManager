from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
import unittest

import allure
import pytest

from app.api.services.holding import compute_top_n_performance_from_quotes
from app.models.enums import AccountType, BrokerageEventKind, InstrumentCurrency
from app.schemas.response import QuoteBySymbolItem
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
        adjustment = compute_cash_effect(BrokerageEventKind.ADJUSTMENT, Decimal("3"), Decimal("2.50"))

        self.assertEqual(result, Decimal("0"))
        self.assertEqual(adjustment, Decimal("0"))

    def test_fx_convert_returns_none_when_rate_is_missing(self) -> None:
        result = fx_convert(Decimal("100"), "USD", "PLN", {})

        self.assertIsNone(result)

    def test_fx_convert_uses_available_rate(self) -> None:
        result = fx_convert(Decimal("100"), "USD", "PLN", {"USD/PLN": "4.02"})

        self.assertEqual(result, Decimal("402.00"))

    def test_fx_convert_returns_amount_when_currency_matches(self) -> None:
        result = fx_convert(Decimal("100"), "PLN", "PLN", {})

        self.assertEqual(result, Decimal("100"))

    def test_fx_convert_uses_chf_direct_rate_to_view_currency(self) -> None:
        # CHF instruments convert to a view currency via the forward direct key
        # supplied by the frontend FX map (CHF/PLN, CHF/USD, CHF/EUR).
        rates = {"CHF/PLN": "4.50", "CHF/USD": "1.125", "CHF/EUR": "1.0227"}

        self.assertEqual(fx_convert(Decimal("100"), "CHF", "PLN", rates), Decimal("450.00"))
        self.assertEqual(fx_convert(Decimal("100"), "CHF", "USD", rates), Decimal("112.500"))

    def test_fx_convert_returns_none_when_chf_rate_is_missing(self) -> None:
        # Without the CHF key the snapshot leaves the amount unconverted (None),
        # matching the pre-CHF behaviour for unknown currencies.
        self.assertIsNone(fx_convert(Decimal("100"), "CHF", "PLN", {"USD/PLN": "4.0"}))

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


@allure.epic("Unit Tests")
@allure.feature("Wallet")
@allure.story("Portfolio performance aggregates duplicate symbols before ranking")
@allure.severity(allure.severity_level.CRITICAL)
@allure.tag("wallet", "brokerage", "money", "financial-data")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
@allure.description(
    "Duplicate PLN holdings for WAS and F51 are combined across brokerage accounts "
    "using total quantity and weighted cost before five unique gainers and losers are ranked."
)
class PositionPerformanceRankingTests(unittest.TestCase):
    @staticmethod
    def _holding(symbol: str, avg_cost: str, quantity: str = "10") -> SimpleNamespace:
        return SimpleNamespace(
            id=symbol,
            quantity=Decimal(quantity),
            avg_cost=Decimal(avg_cost),
            instrument=SimpleNamespace(symbol=symbol),
        )

    @staticmethod
    def _quote(symbol: str, price: str) -> QuoteBySymbolItem:
        return QuoteBySymbolItem(
            symbol=symbol,
            price=Decimal(price),
            currency=InstrumentCurrency.PLN,
            change_pct=Decimal("0"),
        )

    def test_top_five_lists_never_borrow_positions_from_opposite_sign(self) -> None:
        prices = {
            "ALR": "20",
            "UNT": "15",
            "WAS": "14",
            "ZUE": "12",
            "PEO": "11",
            "CRB": "1",
            "F51": "2",
            "IPW": "3",
            "MPS": "4",
            "LTX": "5",
        }
        holdings = [
            self._holding("ALR", "10"),
            self._holding("UNT", "10"),
            self._holding("WAS", "8"),
            self._holding("WAS", "12"),
            self._holding("ZUE", "10"),
            self._holding("PEO", "10"),
            self._holding("CRB", "10"),
            self._holding("F51", "8"),
            self._holding("F51", "12"),
            self._holding("IPW", "10"),
            self._holding("MPS", "10"),
            self._holding("LTX", "10"),
        ]
        quotes = {symbol: self._quote(symbol, price) for symbol, price in prices.items()}

        losers, gainers = compute_top_n_performance_from_quotes(holdings, quotes, n=5)

        self.assertEqual([position.symbol for position in gainers], ["ALR", "UNT", "WAS", "ZUE", "PEO"])
        self.assertEqual([position.symbol for position in losers], ["CRB", "F51", "IPW", "MPS", "LTX"])
        self.assertTrue(all(position.pnl_pct > 0 for position in gainers))
        self.assertTrue(all(position.pnl_pct < 0 for position in losers))
        self.assertEqual(gainers[0].pnl_amount, Decimal("100"))
        self.assertEqual(losers[0].pnl_amount, Decimal("-90"))
        was = next(position for position in gainers if position.symbol == "WAS")
        f51 = next(position for position in losers if position.symbol == "F51")
        self.assertEqual(was.quantity, Decimal("20"))
        self.assertEqual(was.cost, Decimal("200"))
        self.assertEqual(was.avg_cost, Decimal("10"))
        self.assertEqual(was.pnl_amount, Decimal("80"))
        self.assertEqual(f51.quantity, Decimal("20"))
        self.assertEqual(f51.cost, Decimal("200"))
        self.assertEqual(f51.avg_cost, Decimal("10"))
        self.assertEqual(f51.pnl_amount, Decimal("-160"))
