from __future__ import annotations

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

import allure
import pytest

from app.utils.date import month_key, monthly_index_from_daily_candles

pytestmark = pytest.mark.unit


@allure.epic("Unit Tests")
@allure.feature("Wallet")
@allure.story("Date utility behavior is deterministic")
@allure.severity(allure.severity_level.NORMAL)
@allure.tag("utils", "financial-data")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
class DateUtilsTests(unittest.TestCase):
    def test_month_key_uses_explicit_datetime(self) -> None:
        result = month_key(datetime(2026, 5, 3, 9, 30, tzinfo=timezone.utc))

        self.assertEqual(result, "2026-05")

    def test_monthly_index_uses_last_close_per_month(self) -> None:
        candles = [
            SimpleNamespace(date_quote=datetime(2026, 4, 1, tzinfo=timezone.utc), close="10.10"),
            SimpleNamespace(date_quote=datetime(2026, 4, 30, tzinfo=timezone.utc), close="11.25"),
            SimpleNamespace(date_quote=datetime(2026, 5, 2, tzinfo=timezone.utc), close="12.50"),
            SimpleNamespace(date_quote=datetime(2026, 5, 1, tzinfo=timezone.utc), close="12.00"),
        ]

        result = monthly_index_from_daily_candles(candles)

        self.assertEqual(result, {"2026-04": 11.25, "2026-05": 12.5})
