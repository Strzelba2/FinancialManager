from __future__ import annotations

import math
import unittest
from datetime import date, datetime, timedelta, timezone

import allure
import pytest

from app.reports.equity.ai_schema import EquityAiPayload
from app.reports.equity.builder import build_equity_report
from app.reports.equity.local_metrics import aggregate_candles_weekly, bollinger, closes
from app.reports.equity.sanitize import sanitize_equity_ai_payload

pytestmark = pytest.mark.unit


def mv(value, as_of="2024-12-31", unit=None, confidence="high", source="openai", note=None):
    payload = {
        "value": value,
        "as_of": as_of,
        "source": source,
        "confidence": confidence,
    }
    if unit is not None:
        payload["unit"] = unit
    if note is not None:
        payload["note"] = note
    return payload


def make_ai_payload() -> EquityAiPayload:
    return EquityAiPayload.model_validate(
        {
            "company": {
                "name": "TestCo",
                "full_name": "TestCo S.A.",
                "description": "Test company description.",
                "sector": "Industry",
                "industry": "Machinery",
                "country": "Poland",
                "exchange": "GPW",
                "founded": "2001",
                "employees": mv(500, unit="osoby"),
                "ceo": "Jane Doe",
                "ceo_since": "2020",
                "headquarters": "Warsaw, Poland",
                "is_leader_in": ["Components"],
                "main_products": ["Widgets"],
                "key_competitors": ["Comp A", "Comp B"],
                "market_position": "Top 3 niche supplier",
                "website": "https://example.com",
                "isin": "PLTEST000001",
                "shares_outstanding": mv(1_000_000, unit="akcji", confidence="medium"),
            },
            "fundamentals": {
                "ebitda_margin": mv(20.0, unit="%"),
                "roe": mv(15.0, unit="%"),
                "roic": mv(13.0, unit="%"),
                "ocf": mv(None, unit="PLN", confidence="medium"),
                "fcf": mv(2_000_000, unit="PLN", confidence="medium"),
                "bvps": mv(None, unit="PLN", confidence="medium"),
                "revenue_ttm": mv(20_000_000, unit="PLN"),
                "ebitda_ttm": mv(4_000_000, unit="PLN"),
                "net_income_ttm": mv(1_500_000, unit="PLN"),
                "eps_ttm": mv(1.25, unit="PLN", confidence="medium"),
                "interpretation": "Fundamentals interpretation.",
            },
            "debt_balance": {
                "cash_and_equivalents": mv(500_000, unit="PLN"),
                "net_debt": mv(1_000_000, unit="PLN", confidence="medium"),
                "net_debt_ebitda": mv(0.25, unit="x"),
                "current_ratio": mv(1.7, unit="x"),
                "quick_ratio": mv(1.2, unit="x"),
                "interest_coverage": mv(8.0, unit="x"),
                "de_ratio": mv(0.2, unit="x"),
                "capex": mv(700_000, unit="PLN"),
                "capex_to_depreciation": mv(1.1, unit="x"),
                "total_assets": mv(12_000_000, unit="PLN"),
                "equity": mv(8_000_000, unit="PLN", confidence="medium"),
                "interpretation": "Debt interpretation.",
            },
            "trend_condition": {
                "scores": {
                    "profitability": {"score": 7, "reasoning": "Good margins."},
                    "balance_sheet": {"score": 8, "reasoning": "Low leverage."},
                    "earnings_quality": {"score": 7, "reasoning": "Cash aligned."},
                    "revenue_growth": {"score": 8, "reasoning": "Healthy growth."},
                    "market_valuation": {"score": 7, "reasoning": "Reasonable valuation."},
                    "management_quality": {"score": 6, "reasoning": "Stable team."},
                    "competitive_advantage": {"score": 6, "reasoning": "Moderate moat."},
                    "industry_outlook": {"score": 6, "reasoning": "Steady market."},
                    "overall": 6.9,
                },
                "history": [
                    {
                        "year": year,
                        "revenue": 10_000_000 + idx * 2_000_000,
                        "ebitda": 2_000_000 + idx * 300_000,
                        "ebitda_margin_pct": 18 + idx * 0.5,
                        "net_income": 700_000 + idx * 150_000,
                        "eps": 0.6 + idx * 0.1,
                        "roe_pct": 10 + idx,
                        "net_debt_ebitda": 1.2 - idx * 0.1,
                        "dividend_per_share": 0.1 + idx * 0.1,
                        "direction": "up",
                    }
                    for idx, year in enumerate(range(2020, 2025))
                ],
                "positive_signals": ["Growing revenues."],
                "negative_signals": ["Moderate cyclicality."],
                "interpretation": "Trend interpretation.",
            },
            "dividend": {
                "payout_ratio": mv(40.0, unit="%"),
                "last_dividend": {
                    "amount": 0.50,
                    "currency": "PLN",
                    "ex_date": "2025-06-01",
                    "pay_date": "2025-06-20",
                },
                "history": [
                    {"year": 2021, "dividend_per_share": 0.20, "yield_pct": 2.0, "payout_ratio_pct": 30.0, "paid": True},
                    {"year": 2022, "dividend_per_share": 0.30, "yield_pct": 3.0, "payout_ratio_pct": 35.0, "paid": True},
                    {"year": 2023, "dividend_per_share": 0.40, "yield_pct": 4.0, "payout_ratio_pct": 38.0, "paid": True},
                    {"year": 2024, "dividend_per_share": 0.50, "yield_pct": 5.0, "payout_ratio_pct": 40.0, "paid": True},
                ],
                "is_dividend_stock": True,
                "dividend_consistency": "consistent",
                "interpretation": "Dividend interpretation.",
            },
            "key_events": {
                "positive": [
                    {"date": "2025-01-10", "title": "New contract", "description": "Positive event.", "impact": "medium", "confidence": "high"}
                ],
                "negative": [
                    {"date": "2025-02-10", "title": "Cost inflation", "description": "Negative event.", "impact": "low", "confidence": "medium"}
                ],
                "upcoming_dates": [{"date": "2025-05-20", "event": "Q1 results", "type": "earnings"}],
                "interpretation": "Events interpretation.",
            },
            "advantages_risks": {
                "moat_score": 6,
                "moat_type": "Scale",
                "advantages": [{"title": "Scale", "description": "Some scale.", "strength": "moderate"}],
                "risks": [{"title": "Cycles", "description": "Demand cycles.", "severity": "medium", "probability": "medium"}],
                "interpretation": "Moat interpretation.",
            },
            "shareholders": {
                "free_float_pct": mv(60.0, unit="%", confidence="medium"),
                "institutional_ownership_pct": mv(25.0, unit="%"),
                "insider_ownership_pct": mv(20.0, unit="%"),
                "major_shareholders": [
                    {"name": "Founder", "stake_pct": 20.0, "type": "insider", "change_direction": "unchanged"},
                    {"name": "Fund", "stake_pct": 8.0, "type": "institutional", "change_direction": "increased"},
                ],
                "insider_transactions": [
                    {"date": "2025-03-10", "insider": "Jane Doe", "role": "CEO", "type": "buy", "shares": 1_000, "price": 9.5, "value": 9_500, "currency": "PLN"}
                ],
                "interpretation": "Shareholders interpretation.",
            },
            "verdict": {
                "overall_score": 7.2,
                "recommendation": "buy",
                "time_horizon": "medium",
                "price_target": mv(12.5, as_of="2025-04-15", unit="PLN", confidence="medium"),
                "bull_case": {"title": "Bull", "description": "Bull case.", "probability": "medium", "catalysts_or_risks": ["Growth"]},
                "base_case": {"title": "Base", "description": "Base case.", "probability": "high", "catalysts_or_risks": ["Execution"]},
                "bear_case": {"title": "Bear", "description": "Bear case.", "probability": "low", "catalysts_or_risks": ["Recession"]},
                "key_watchpoints": ["Margins"],
                "valuation_matrix": {
                    "current_quadrant": "A",
                    "quadrants": {
                        "A": {"title": "Attractive", "description": "Cheap and healthy."},
                        "B": {"title": "Trap", "description": "Cheap but weak."},
                        "C": {"title": "Premium", "description": "Expensive but quality."},
                        "D": {"title": "Avoid", "description": "Expensive and weak."},
                    },
                    "momentum": {"signal": "accumulate", "label": "Accumulate", "reasoning": "Build position gradually."},
                },
                "interpretation": "Verdict interpretation.",
            },
        }
    )


def make_candles(*, start: date = date(2024, 1, 1), periods: int = 330) -> list[dict]:
    candles: list[dict] = []
    for idx in range(periods):
        day = start + timedelta(days=idx)
        base = 6.0 + idx * 0.02 + ((idx % 7) - 3) * 0.18
        open_price = round(base - 0.15, 2)
        close_price = round(base + 0.10, 2)
        if idx in (290, 305):
            close_price = round(base - 0.20, 2)
        volume = 1_000 + (idx % 9) * 60
        if idx == 320:
            volume = 4_500
            close_price = round(base + 0.65, 2)
        candles.append(
            {
                "date_quote": day,
                "open": open_price,
                "high": round(max(open_price, close_price) + 0.35, 2),
                "low": round(min(open_price, close_price) - 0.35, 2),
                "close": close_price,
                "volume": volume,
            }
        )
    return candles


@allure.epic("Unit Tests")
@allure.feature("Stock Equity Reports")
@allure.story("Report builder keeps local metrics and response contracts stable")
@allure.severity(allure.severity_level.CRITICAL)
@allure.tag("reports", "ai", "financial-data")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
@allure.description(
    "Builds the final equity report from an AI payload and market candle data. "
    "Verifies local metric computation (PE, PB, PS, EV/EBITDA, Bollinger bands on "
    "weekly candles, RSI, OBV), AI verdict reconciliation when local signals contradict "
    "the AI score, valuation quadrant assignment (A/B/C/D), and sanitizer fallbacks "
    "for placeholder and null values in the AI payload."
)
class BuildEquityReportTests(unittest.TestCase):
    def test_builder_computes_local_metrics_and_keeps_contract_shape(self) -> None:
        ai_payload = make_ai_payload()
        candles = make_candles(start=date(2023, 1, 1), periods=836)
        last_trade_at = datetime(2025, 4, 15, 14, 30, tzinfo=timezone.utc)

        report, market_data_as_of = build_equity_report(
            ai_payload=ai_payload,
            mic="XWAR",
            symbol="TEST",
            currency="PLN",
            instrument_shortname="TEST",
            instrument_name="TESTCO SPOLKA AKCYJNA",
            instrument_isin="PLTEST000001",
            current_price=10.0,
            change_1d_pct=1.5,
            last_trade_at=last_trade_at,
            candles=candles,
            period="2025-Q1",
            model="gpt-5.4-mini",
            final_generated_at=datetime(2025, 4, 19, 10, 0, tzinfo=timezone.utc),
            valid_until=date(2025, 7, 18),
        )

        self.assertEqual(report.meta.report_type, "equity")
        self.assertEqual(report.company.price.current, 10.0)
        self.assertEqual(market_data_as_of.isoformat(), "2025-04-15")
        self.assertAlmostEqual(report.company.price.market_cap, 10_000_000.0, places=2)
        self.assertAlmostEqual(report.fundamentals.ocf.value, 2_700_000.0, places=2)
        self.assertEqual(report.fundamentals.ocf.source, "local")
        self.assertAlmostEqual(report.fundamentals.pe_ratio.value, 8.0, places=2)
        self.assertAlmostEqual(report.fundamentals.pb_ratio.value, 1.25, places=2)
        self.assertAlmostEqual(report.fundamentals.ps_ratio.value, 0.5, places=2)
        self.assertAlmostEqual(report.fundamentals.ev_ebitda.value, 2.75, places=2)
        self.assertAlmostEqual(report.fundamentals.fcf_yield.value, 20.0, places=2)
        self.assertAlmostEqual(report.fundamentals.bvps.value, 8.0, places=4)
        self.assertEqual(report.fundamentals.bvps.source, "local")
        self.assertAlmostEqual(report.dividend.dividend_yield.value, 5.0, places=2)
        self.assertTrue(math.isclose(report.dividend.dividend_growth_3y.value, 35.72, rel_tol=0.03))
        self.assertEqual(report.volume_liquidity.float_shares.value, 600000)
        self.assertEqual(report.volume_liquidity.float_shares.source, "local")
        self.assertEqual(report.technical.moving_averages.ma_50.source, "local")
        self.assertEqual(report.technical.rsi.source, "local")
        self.assertIsInstance(report.technical.support_resistance.supports, list)
        self.assertIsInstance(report.technical.support_resistance.resistances, list)
        self.assertIsInstance(report.volume_liquidity.anomalous_sessions, list)
        self.assertIn(report.technical.trend, {"bullish", "neutral", "bearish"})
        self.assertIn(report.volume_liquidity.obv_signal, {"bullish", "neutral", "bearish"})
        self.assertEqual(report.meta.source_versions.model, "gpt-5.4-mini")

    def test_builder_uses_weekly_candles_and_bollinger_period_66_for_technical_section(self) -> None:
        ai_payload = make_ai_payload()
        candles = make_candles(start=date(2023, 1, 1), periods=836)
        last_trade_at = datetime(2025, 4, 15, 14, 30, tzinfo=timezone.utc)

        report, _ = build_equity_report(
            ai_payload=ai_payload,
            mic="XWAR",
            symbol="TEST",
            currency="PLN",
            instrument_shortname="TEST",
            instrument_name="TESTCO SPOLKA AKCYJNA",
            instrument_isin="PLTEST000001",
            current_price=10.0,
            change_1d_pct=1.5,
            last_trade_at=last_trade_at,
            candles=candles,
            period="2025-Q1",
            model="gpt-5.4-mini",
            final_generated_at=datetime(2025, 4, 19, 10, 0, tzinfo=timezone.utc),
            valid_until=date(2025, 7, 18),
        )

        weekly_candles = aggregate_candles_weekly(candles)
        weekly_close_values = closes(weekly_candles)
        expected_bollinger = bollinger(weekly_close_values, period=66)

        self.assertGreaterEqual(len(weekly_candles), 66)
        self.assertAlmostEqual(
            report.technical.bollinger_bands.middle.value,
            round(expected_bollinger["middle"], 2),
            places=2,
        )
        self.assertAlmostEqual(
            report.technical.bollinger_bands.upper.value,
            round(expected_bollinger["upper"], 2),
            places=2,
        )
        self.assertAlmostEqual(
            report.technical.bollinger_bands.lower.value,
            round(expected_bollinger["lower"], 2),
            places=2,
        )
        self.assertIn("swiecach tygodniowych", report.technical.interpretation)

    def test_builder_reconciles_contradictory_ai_verdict_using_local_signals(self) -> None:
        ai_payload = make_ai_payload().model_copy(deep=True)
        ai_payload.verdict.overall_score = 4.8
        ai_payload.verdict.recommendation = "reduce"
        ai_payload.verdict.price_target.value = 10.0
        ai_payload.verdict.price_target.as_of = "2025-04-15"
        ai_payload.verdict.valuation_matrix.current_quadrant = "D"
        ai_payload.verdict.interpretation = "Spolka jest droga i slaba."

        report, _ = build_equity_report(
            ai_payload=ai_payload,
            mic="XWAR",
            symbol="TEST",
            currency="PLN",
            instrument_shortname="TEST",
            instrument_name="TESTCO SPOLKA AKCYJNA",
            instrument_isin="PLTEST000001",
            current_price=10.0,
            change_1d_pct=1.5,
            last_trade_at=datetime(2025, 4, 15, 14, 30, tzinfo=timezone.utc),
            candles=make_candles(),
            period="2025-Q1",
            model="gpt-5.4-mini",
            final_generated_at=datetime(2025, 4, 19, 10, 0, tzinfo=timezone.utc),
            valid_until=date(2025, 7, 18),
        )

        self.assertEqual(report.verdict.upside_pct, 0.0)
        self.assertEqual(report.verdict.recommendation, "reduce")
        self.assertEqual(report.verdict.overall_score, 4.8)
        self.assertEqual(report.verdict.valuation_matrix.current_quadrant, "D")
        self.assertEqual(report.verdict.interpretation, "Spolka jest droga i slaba.")

    def test_builder_marks_discounted_but_weaker_company_as_bucket_b(self) -> None:
        ai_payload = make_ai_payload().model_copy(deep=True)
        ai_payload.trend_condition.scores.profitability.score = 4
        ai_payload.trend_condition.scores.balance_sheet.score = 4
        ai_payload.trend_condition.scores.earnings_quality.score = 4
        ai_payload.trend_condition.scores.revenue_growth.score = 5
        ai_payload.trend_condition.scores.competitive_advantage.score = 4
        ai_payload.trend_condition.scores.industry_outlook.score = 4
        ai_payload.verdict.price_target.value = 12.0
        ai_payload.verdict.price_target.as_of = "2025-04-15"
        ai_payload.verdict.overall_score = 5.9
        ai_payload.verdict.recommendation = "hold"
        ai_payload.verdict.valuation_matrix.current_quadrant = "B"

        report, _ = build_equity_report(
            ai_payload=ai_payload,
            mic="XWAR",
            symbol="TEST",
            currency="PLN",
            instrument_shortname="TEST",
            instrument_name="TESTCO SPOLKA AKCYJNA",
            instrument_isin="PLTEST000001",
            current_price=10.0,
            change_1d_pct=1.5,
            last_trade_at=datetime(2025, 4, 15, 14, 30, tzinfo=timezone.utc),
            candles=make_candles(),
            period="2025-Q1",
            model="gpt-5.4-mini",
            final_generated_at=datetime(2025, 4, 19, 10, 0, tzinfo=timezone.utc),
            valid_until=date(2025, 7, 18),
        )

        self.assertEqual(report.verdict.valuation_matrix.current_quadrant, "B")
        self.assertEqual(report.verdict.overall_score, 5.9)
        self.assertEqual(report.verdict.recommendation, "hold")

    def test_sanitizer_removes_placeholders_and_builder_uses_fallbacks(self) -> None:
        dirty_payload = EquityAiPayload.model_validate(
            {
                **make_ai_payload().model_dump(mode="json"),
                "company": {
                    **make_ai_payload().model_dump(mode="json")["company"],
                    "name": None,
                    "full_name": None,
                    "description": None,
                    "sector": "null",
                    "industry": "unknown",
                    "country": None,
                    "exchange": None,
                    "founded": "null",
                    "ceo": "null",
                    "ceo_since": "null",
                    "headquarters": None,
                    "is_leader_in": ["", "Prefabrykacja"],
                    "main_products": ["Produkt A", "null"],
                    "key_competitors": ["Comp A?", "Comp B"],
                    "market_position": "none",
                    "website": "null",
                    "isin": None,
                },
                "trend_condition": {
                    **make_ai_payload().model_dump(mode="json")["trend_condition"],
                    "scores": {
                        **make_ai_payload().model_dump(mode="json")["trend_condition"]["scores"],
                        "overall": 57,
                    },
                    "history": [
                        {
                            "year": 2024,
                            "revenue": None,
                            "ebitda": None,
                            "ebitda_margin_pct": None,
                            "net_income": None,
                            "eps": None,
                            "roe_pct": None,
                            "net_debt_ebitda": None,
                            "dividend_per_share": None,
                            "direction": "flat",
                        }
                    ],
                },
                "verdict": {
                    **make_ai_payload().model_dump(mode="json")["verdict"],
                    "overall_score": 52,
                    "key_watchpoints": ["", "Marze", "null"],
                },
                "shareholders": {
                    **make_ai_payload().model_dump(mode="json")["shareholders"],
                    "major_shareholders": [
                        {"name": "Fundusz?", "stake_pct": 9.0, "type": "institutional", "change_direction": "unchanged"},
                        {"name": "Founder", "stake_pct": 20.0, "type": "insider", "change_direction": "unchanged"},
                    ],
                },
            }
        )

        sanitized = sanitize_equity_ai_payload(
            dirty_payload,
            symbol="TEST",
            mic="XWAR",
            instrument_name="TESTCO SPOLKA AKCYJNA",
            instrument_shortname="TEST",
            instrument_isin="PLTEST000001",
        )

        self.assertIsNone(sanitized.company.ceo_since)
        self.assertEqual(sanitized.company.key_competitors, ["Comp B"])
        self.assertEqual(sanitized.trend_condition.history, [])
        self.assertAlmostEqual(sanitized.trend_condition.scores.overall, 5.7, places=1)
        self.assertAlmostEqual(sanitized.verdict.overall_score, 5.2, places=1)
        self.assertEqual(sanitized.verdict.key_watchpoints, ["Marze"])
        self.assertEqual(len(sanitized.shareholders.major_shareholders), 1)

        report, _ = build_equity_report(
            ai_payload=sanitized,
            mic="XWAR",
            symbol="TEST",
            currency="PLN",
            instrument_shortname="TEST",
            instrument_name="TESTCO SPOLKA AKCYJNA",
            instrument_isin="PLTEST000001",
            current_price=10.0,
            change_1d_pct=1.5,
            last_trade_at=datetime(2025, 4, 15, 14, 30, tzinfo=timezone.utc),
            candles=make_candles(),
            period="2025-Q1",
            model="gpt-5.4-mini",
            final_generated_at=datetime(2025, 4, 19, 10, 0, tzinfo=timezone.utc),
            valid_until=date(2025, 7, 18),
        )

        self.assertEqual(report.company.name, "TEST")
        self.assertEqual(report.company.full_name, "TESTCO SPOLKA AKCYJNA")
        self.assertEqual(report.company.exchange, "XWAR")
        self.assertEqual(report.company.isin, "PLTEST000001")
        self.assertEqual(report.company.ceo_since, "")


if __name__ == "__main__":  
    unittest.main()
