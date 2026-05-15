from __future__ import annotations

from decimal import Decimal
import unittest

import allure
import pytest

from app.validators.validators import (
    iban_is_valid,
    iban_normalize,
    none_if_empty,
    q2,
    q6,
    require_bytes_len_32,
    require_bytes_nonempty,
    require_iso2_opt,
    require_len_between_1_12,
    require_len_between_1_5,
    require_nonempty,
    require_nonnegative_opt,
    require_positive,
    require_regex,
    strip,
    strip_lower,
    strip_upper,
    validate_bic_opt,
    validate_iban_opt,
)

pytestmark = pytest.mark.unit


@allure.epic("Unit Tests")
@allure.feature("Wallet")
@allure.story("Wallet validators normalize and reject financial input safely")
@allure.severity(allure.severity_level.CRITICAL)
@allure.tag("validators", "money", "financial-data")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
@allure.description(
    "Covers wallet input normalization and negative paths for money precision, "
    "IBAN/BIC, byte secrets, required names, positive values, and ISO country codes."
)
class WalletValidatorTests(unittest.TestCase):
    def test_decimal_quantizers_use_half_up_precision(self) -> None:
        self.assertEqual(q2(Decimal("1.005")), Decimal("1.01"))
        self.assertEqual(q2(Decimal("1.004")), Decimal("1.00"))
        self.assertEqual(q6(Decimal("1.1234567")), Decimal("1.123457"))
        self.assertIsNone(q2(None))
        self.assertIsNone(q6(None))

    def test_string_normalizers_handle_strings_and_non_strings(self) -> None:
        self.assertEqual(strip("  Wallet  "), "Wallet")
        self.assertEqual(strip_upper("  pln  "), "PLN")
        self.assertEqual(strip_lower("  USER@EXAMPLE.COM  "), "user@example.com")
        self.assertEqual(strip_upper(123), 123)

    def test_none_if_empty_trims_or_removes_optional_text(self) -> None:
        self.assertIsNone(none_if_empty(None))
        self.assertIsNone(none_if_empty("   "))
        self.assertEqual(none_if_empty("  note  "), "note")

    def test_iban_normalization_and_checksum_validation(self) -> None:
        iban = "GB82 WEST 1234 5698 7654 32"

        self.assertEqual(iban_normalize(iban), "GB82WEST12345698765432")
        self.assertTrue(iban_is_valid(iban))
        self.assertFalse(iban_is_valid("GB82TEST123"))
        self.assertIsNone(validate_iban_opt(None))
        self.assertEqual(validate_iban_opt(iban), "GB82WEST12345698765432")

        with self.assertRaisesRegex(ValueError, "invalid IBAN"):
            validate_iban_opt("GB82WEST12345698765431")

    def test_bic_validation_normalizes_optional_codes(self) -> None:
        self.assertIsNone(validate_bic_opt(None))
        self.assertIsNone(validate_bic_opt("   "))
        self.assertEqual(validate_bic_opt(" deutdeff500 "), "DEUTDEFF500")

        with self.assertRaisesRegex(ValueError, "bic must be 8 or 11"):
            validate_bic_opt("DEUT")

    def test_length_and_nonempty_validators_reject_invalid_names(self) -> None:
        self.assertEqual(require_len_between_1_12("wallet-name"), "wallet-name")
        self.assertEqual(require_len_between_1_5("PKO"), "PKO")
        self.assertEqual(require_nonempty(" account "), " account ")

        with self.assertRaisesRegex(ValueError, "1..12"):
            require_len_between_1_12("")
        with self.assertRaisesRegex(ValueError, "1..5"):
            require_len_between_1_5("TOO-LONG")
        with self.assertRaisesRegex(ValueError, "cannot be empty"):
            require_nonempty("   ")

    def test_byte_validators_require_nonempty_and_exact_key_size(self) -> None:
        key = b"x" * 32

        self.assertEqual(require_bytes_nonempty(bytearray(b"abc")), b"abc")
        self.assertEqual(require_bytes_len_32(key), key)

        with self.assertRaisesRegex(ValueError, "non-empty bytes"):
            require_bytes_nonempty(b"")
        with self.assertRaisesRegex(ValueError, "exactly 32 bytes"):
            require_bytes_len_32(b"short")

    def test_money_boundary_validators_reject_zero_negative_and_invalid_country(self) -> None:
        self.assertEqual(require_positive(Decimal("0.01")), Decimal("0.01"))
        self.assertEqual(require_nonnegative_opt(Decimal("0")), Decimal("0"))
        self.assertIsNone(require_nonnegative_opt(None))
        self.assertIsNone(require_iso2_opt(None))
        self.assertEqual(require_iso2_opt("pl"), "PL")
        self.assertIsNone(require_iso2_opt(" "))

        with self.assertRaisesRegex(ValueError, "> 0"):
            require_positive(Decimal("0"))
        with self.assertRaisesRegex(ValueError, "≥ 0"):
            require_nonnegative_opt(Decimal("-0.01"))
        with self.assertRaisesRegex(ValueError, "2-letter"):
            require_iso2_opt("POL")

    def test_regex_validator_accepts_full_match_only(self) -> None:
        mic_validator = require_regex(r"^[A-Z0-9]{4}$", "invalid MIC")

        self.assertEqual(mic_validator("XWAR"), "XWAR")
        with self.assertRaisesRegex(ValueError, "invalid MIC"):
            mic_validator("XWAR1")
