from __future__ import annotations

import unittest
from datetime import date

import allure
import pytest

from app.reports.equity.prompt import SYSTEM_PROMPT, build_user_prompt

pytestmark = pytest.mark.unit


@allure.epic("Unit Tests")
@allure.feature("Stock Equity Reports")
@allure.story("Prompt contracts preserve grounded analysis instructions")
@allure.severity(allure.severity_level.NORMAL)
@allure.tag("reports", "ai")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
class EquityPromptTests(unittest.TestCase):
    def test_prompt_tells_model_to_ground_narrative_in_public_web_facts(self) -> None:
        user_prompt = build_user_prompt(
            mic="XWAR",
            symbol="PBX",
            period="2026-Q1",
            today=date(2026, 4, 23),
            instrument_context={"symbol": "PBX", "shortname": "PEKABEX"},
            grounding_context={
                "public_web_facts": {
                    "fundamentals": {
                        "ocf": {
                            "value": 9342000,
                            "as_of": "2025-09-30",
                            "unit": "PLN",
                        },
                        "bvps": {
                            "value": 23.7653,
                            "as_of": "2025-09-30",
                            "unit": "PLN",
                        },
                        "net_income_ttm": {
                            "value": -4960000,
                            "as_of": "2025-09-30",
                            "unit": "PLN",
                        },
                    },
                    "valuation_ratios": {"ev_ebitda": {"value": 18.76, "as_of": "2025-09-30"}},
                    "valuation_benchmarks": {"industry_ev_ebitda": {"value": 5.08, "as_of": "2025-09-30"}},
                    "valuation_anchors": {"peer_pb_implied_price": {"value": 31.61, "as_of": "2025-09-30", "unit": "PLN"}},
                }
            },
        )

        self.assertIn("public_web_facts", SYSTEM_PROMPT)
        self.assertIn("public_web_facts", user_prompt)
        self.assertIn("Oprzyj na nich opisy", user_prompt)
        self.assertIn("ujemny zysk netto", user_prompt)
        self.assertIn("-4960000", user_prompt)
        self.assertIn("9342000", user_prompt)
        self.assertIn("23.7653", user_prompt)
        self.assertIn("18.76", user_prompt)
        self.assertIn("valuation_benchmarks", user_prompt)
        self.assertIn("valuation_anchors", user_prompt)
        self.assertIn("co najmniej 2 metodach", user_prompt)
        self.assertIn("nie zwracaj null w verdict.price_target", user_prompt)
        self.assertIn("verdict.price_target.value nie powinien byc null", SYSTEM_PROMPT)
        self.assertIn("price_target.note", SYSTEM_PROMPT)
        self.assertIn("filtry go/no-go", user_prompt)
        self.assertIn("Bucket A/B/C/D", user_prompt)
        self.assertIn("konserwatywnym analitykiem akcji", SYSTEM_PROMPT)
        self.assertIn("market_valuation score", user_prompt)
        self.assertIn("bucket zwykle powinien byc C", user_prompt)
        self.assertIn("tania, ale slaba/ryzykowna", SYSTEM_PROMPT)
        self.assertIn("ocf", SYSTEM_PROMPT)
        self.assertIn("bvps", SYSTEM_PROMPT)
        self.assertNotIn("eps_norm", SYSTEM_PROMPT)


if __name__ == "__main__":  
    unittest.main()
