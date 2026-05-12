from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

import allure
import pytest

from userauth.validators import CustomPasswordValidator

pytestmark = pytest.mark.unit


@allure.epic("Unit Tests")
@allure.feature("Session")
@allure.story("Password validator enforces strength requirements")
@allure.severity(allure.severity_level.CRITICAL)
@allure.tag("auth", "security")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
class CustomPasswordValidatorTests(SimpleTestCase):
    def setUp(self) -> None:
        self.validator = CustomPasswordValidator()

    def test_accepts_password_that_meets_strength_requirements(self) -> None:
        self.validator.validate("StrongPass123!")

    def test_rejects_passwords_that_miss_required_strength_rule(self) -> None:
        cases = [
            ("Short1!", "Password must be at least 12 characters long."),
            ("lowercase123!", "Password must contain at least one uppercase letter."),
            ("UPPERCASE123!", "Password must contain at least one lowercase letter."),
            ("NoDigitsHere!", "Password must contain at least one digit."),
            ("NoSpecial1234", "Password must contain at least one special character."),
        ]

        for password, expected_message in cases:
            with self.subTest(password=password):
                with self.assertRaisesMessage(ValidationError, expected_message):
                    self.validator.validate(password)

    def test_help_text_describes_strength_requirements(self) -> None:
        help_text = str(self.validator.get_help_text())

        self.assertIn("at least 12 characters", help_text)
        self.assertIn("one uppercase letter", help_text)
        self.assertIn("one lowercase letter", help_text)
        self.assertIn("one digit", help_text)
        self.assertIn("one special character", help_text)
