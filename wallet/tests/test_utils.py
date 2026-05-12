from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
import unittest

import allure
import pytest

from app.utils.utils import b64, b64d, b64e, ccy_str, json_safe, last_n_month_starts, metal_grams, normalize_name, q_get

pytestmark = pytest.mark.unit


@allure.epic("Unit Tests")
@allure.feature("Wallet")
@allure.story("Wallet utility helpers normalize values deterministically")
@allure.severity(allure.severity_level.MINOR)
@allure.tag("utils")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
class WalletUtilsTests(unittest.TestCase):
    def test_normalize_name_collapses_whitespace(self) -> None:
        self.assertEqual(normalize_name("  Main   Wallet  "), "Main Wallet")

    def test_base64_helpers_round_trip_text_and_bytes(self) -> None:
        encoded = b64("wallet")

        self.assertEqual(encoded, b64e(b"wallet"))
        self.assertEqual(b64d(encoded), b"wallet")

    def test_currency_string_prefers_enum_value(self) -> None:
        self.assertEqual(ccy_str(SimpleNamespace(value="PLN")), "PLN")
        self.assertEqual(ccy_str("EUR"), "EUR")

    def test_last_n_month_starts_returns_month_floor_sequence(self) -> None:
        result = last_n_month_starts(3, datetime(2026, 5, 10, 14, 30, 45))

        self.assertEqual(
            result,
            [
                datetime(2026, 3, 1),
                datetime(2026, 4, 1),
                datetime(2026, 5, 1),
            ],
        )

    def test_metal_grams_reads_known_weight_fields(self) -> None:
        self.assertEqual(metal_grams(SimpleNamespace(weight_g="31.1034768")), Decimal("31.1034768"))
        self.assertEqual(metal_grams(SimpleNamespace(quantity_g=None)), Decimal("0"))

    def test_json_safe_converts_nested_decimals(self) -> None:
        payload = {"amount": Decimal("12.34"), "items": (Decimal("1.2"), {"fee": Decimal("0.1")})}

        self.assertEqual(json_safe(payload), {"amount": "12.34", "items": ["1.2", {"fee": "0.1"}]})

    def test_q_get_supports_dicts_objects_and_default(self) -> None:
        self.assertEqual(q_get({"symbol": "PKO"}, "symbol"), "PKO")
        self.assertEqual(q_get(SimpleNamespace(symbol="PKO"), "symbol"), "PKO")
        self.assertEqual(q_get(None, "symbol", "N/A"), "N/A")
