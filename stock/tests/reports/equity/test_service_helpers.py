from __future__ import annotations

import unittest
from datetime import date
from types import SimpleNamespace

import allure
import pytest

from app.core.config import settings
from app.reports.equity.service import (
    ai_snapshot_is_fresh,
    build_ai_cache_prompt_hash,
    last_closed_quarter,
    needs_candle_refresh,
    normalize_period,
    should_fetch_web_source_facts,
    should_refresh_ai_for_grounded_narrative,
)

pytestmark = pytest.mark.unit


@allure.epic("Unit Tests")
@allure.feature("Stock Equity Reports")
@allure.story("Report service refresh decisions are deterministic")
@allure.severity(allure.severity_level.NORMAL)
@allure.tag("reports", "ai")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
@allure.description(
    "Verifies report service refresh decisions: candle staleness gap (5-day rule), "
    "AI snapshot freshness for current vs archived quarters, cache prompt hash "
    "stability for the same identity inputs, web-source fetch conditions, and "
    "quarter boundary handling at year-end."
)
class EquityServiceHelperTests(unittest.TestCase):
    def test_last_closed_quarter_handles_year_boundary(self) -> None:
        self.assertEqual(last_closed_quarter(date(2026, 1, 15)), "2025-Q4")
        self.assertEqual(last_closed_quarter(date(2026, 4, 19)), "2026-Q1")
        self.assertEqual(last_closed_quarter(date(2026, 10, 1)), "2026-Q3")

    def test_normalize_period_validates_shape(self) -> None:
        self.assertEqual(normalize_period("2025-q1", date(2026, 4, 19)), "2025-Q1")
        with self.assertRaises(ValueError):
            normalize_period("2025/01", date(2026, 4, 19))

    def test_needs_candle_refresh_uses_five_day_gap(self) -> None:
        self.assertFalse(needs_candle_refresh(date(2025, 4, 10), date(2025, 4, 15)))
        self.assertTrue(needs_candle_refresh(date(2025, 4, 9), date(2025, 4, 15)))
        self.assertTrue(needs_candle_refresh(None, date(2025, 4, 15)))

    def test_ai_snapshot_freshness_distinguishes_current_and_archived_periods(self) -> None:
        ready_snapshot = SimpleNamespace(
            status="ready",
            prompt_version=settings.OPENAI_REPORT_PROMPT_VERSION,
            prompt_hash="hash-1",
            valid_until=date(2025, 7, 18),
        )
        stale_prompt_snapshot = SimpleNamespace(
            status="ready",
            prompt_version="older",
            prompt_hash="hash-1",
            valid_until=date(2025, 7, 18),
        )
        stale_hash_snapshot = SimpleNamespace(
            status="ready",
            prompt_version=settings.OPENAI_REPORT_PROMPT_VERSION,
            prompt_hash="older-hash",
            valid_until=date(2025, 7, 18),
        )

        self.assertTrue(
            ai_snapshot_is_fresh(
                ready_snapshot,
                current_period="2025-Q1",
                requested_period="2024-Q4",
                today=date(2025, 4, 19),
                current_prompt_hash="hash-1",
            )
        )
        self.assertTrue(
            ai_snapshot_is_fresh(
                ready_snapshot,
                current_period="2025-Q1",
                requested_period="2025-Q1",
                today=date(2025, 4, 19),
                current_prompt_hash="hash-1",
            )
        )
        self.assertFalse(
            ai_snapshot_is_fresh(
                ready_snapshot,
                current_period="2025-Q1",
                requested_period="2025-Q1",
                today=date(2025, 8, 1),
                current_prompt_hash="hash-1",
            )
        )
        self.assertFalse(
            ai_snapshot_is_fresh(
                stale_prompt_snapshot,
                current_period="2025-Q1",
                requested_period="2025-Q1",
                today=date(2025, 4, 19),
                current_prompt_hash="hash-1",
            )
        )
        self.assertFalse(
            ai_snapshot_is_fresh(
                stale_hash_snapshot,
                current_period="2025-Q1",
                requested_period="2025-Q1",
                today=date(2025, 4, 19),
                current_prompt_hash="hash-1",
            )
        )

    def test_build_ai_cache_prompt_hash_is_stable_for_same_identity(self) -> None:
        first = build_ai_cache_prompt_hash(mic="xwar", symbol="pbx", period="2026-Q1")
        second = build_ai_cache_prompt_hash(mic="XWAR", symbol="PBX", period="2026-Q1")
        different_period = build_ai_cache_prompt_hash(mic="XWAR", symbol="PBX", period="2025-Q4")

        self.assertEqual(first, second)
        self.assertNotEqual(first, different_period)

    def test_web_source_fetch_is_needed_for_sparse_ai_or_sparse_final_report(self) -> None:
        self.assertTrue(
            should_fetch_web_source_facts(
                ai_payload_sparse=True,
                final_snapshot_sparse=False,
                ai_fresh=True,
            )
        )
        self.assertTrue(
            should_fetch_web_source_facts(
                ai_payload_sparse=False,
                final_snapshot_sparse=True,
                ai_fresh=True,
            )
        )
        self.assertTrue(
            should_fetch_web_source_facts(
                ai_payload_sparse=False,
                final_snapshot_sparse=False,
                ai_fresh=False,
            )
        )
        self.assertFalse(
            should_fetch_web_source_facts(
                ai_payload_sparse=False,
                final_snapshot_sparse=False,
                ai_fresh=True,
            )
        )

    def test_sparse_ai_cache_with_web_facts_triggers_grounded_narrative_refresh(self) -> None:
        web_facts = SimpleNamespace(has_material_data=lambda: True)
        empty_web_facts = SimpleNamespace(has_material_data=lambda: False)

        self.assertTrue(
            should_refresh_ai_for_grounded_narrative(
                ai_fresh=True,
                ai_payload_sparse=True,
                web_source_facts=web_facts,
            )
        )
        self.assertFalse(
            should_refresh_ai_for_grounded_narrative(
                ai_fresh=True,
                ai_payload_sparse=False,
                web_source_facts=web_facts,
            )
        )
        self.assertFalse(
            should_refresh_ai_for_grounded_narrative(
                ai_fresh=False,
                ai_payload_sparse=True,
                web_source_facts=web_facts,
            )
        )
        self.assertFalse(
            should_refresh_ai_for_grounded_narrative(
                ai_fresh=True,
                ai_payload_sparse=True,
                web_source_facts=empty_web_facts,
            )
        )
        self.assertFalse(
            should_refresh_ai_for_grounded_narrative(
                ai_fresh=True,
                ai_payload_sparse=True,
                web_source_facts=None,
            )
        )


if __name__ == "__main__":  
    unittest.main()
