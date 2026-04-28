from __future__ import annotations

import httpx
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from openai import APIStatusError

from app.reports.equity.openai_client import (
    OpenAIEquityReportClient,
    _extract_parsed_payload,
    _is_likely_truncated_json_error,
)


def _mv(value, as_of="2024-12-31", unit=None, confidence="high", source="openai", note=None):
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


def _payload_dict() -> dict:
    return {
        "company": {
            "name": "PBX",
            "full_name": "Pekabex SA",
            "description": "Opis",
            "sector": "Budownictwo",
            "industry": "Prefabrykacja",
            "country": "Polska",
            "exchange": "XWAR",
            "founded": "2008",
            "employees": _mv(None, unit="osoby", confidence="low"),
            "ceo": "Prezes",
            "ceo_since": None,
            "headquarters": "Poznan",
            "is_leader_in": [],
            "main_products": [],
            "key_competitors": [],
            "market_position": None,
            "website": "https://example.com",
            "isin": "PLTEST000001",
            "shares_outstanding": _mv(1000000, unit="akcji"),
        },
        "fundamentals": {
            "ebitda_margin": _mv(None, unit="%"),
            "roe": _mv(None, unit="%"),
            "roic": _mv(None, unit="%"),
            "ocf": _mv(None, unit="PLN"),
            "fcf": _mv(None, unit="PLN"),
            "bvps": _mv(None, unit="PLN"),
            "revenue_ttm": _mv(None, unit="PLN"),
            "ebitda_ttm": _mv(None, unit="PLN"),
            "net_income_ttm": _mv(None, unit="PLN"),
            "eps_ttm": _mv(None, unit="PLN"),
            "interpretation": "Interpretacja",
        },
        "debt_balance": {
            "cash_and_equivalents": _mv(None, unit="PLN"),
            "net_debt": _mv(None, unit="PLN"),
            "net_debt_ebitda": _mv(None, unit="x"),
            "current_ratio": _mv(None, unit="x"),
            "quick_ratio": _mv(None, unit="x"),
            "interest_coverage": _mv(None, unit="x"),
            "de_ratio": _mv(None, unit="x"),
            "capex": _mv(None, unit="PLN"),
            "capex_to_depreciation": _mv(None, unit="x"),
            "total_assets": _mv(None, unit="PLN"),
            "equity": _mv(None, unit="PLN"),
            "interpretation": "Interpretacja",
        },
        "trend_condition": {
            "scores": {
                "profitability": {"score": 5, "reasoning": "x"},
                "balance_sheet": {"score": 5, "reasoning": "x"},
                "earnings_quality": {"score": 5, "reasoning": "x"},
                "revenue_growth": {"score": 5, "reasoning": "x"},
                "market_valuation": {"score": 5, "reasoning": "x"},
                "management_quality": {"score": 5, "reasoning": "x"},
                "competitive_advantage": {"score": 5, "reasoning": "x"},
                "industry_outlook": {"score": 5, "reasoning": "x"},
                "overall": 5,
            },
            "history": [],
            "positive_signals": [],
            "negative_signals": [],
            "interpretation": "Interpretacja",
        },
        "dividend": {
            "payout_ratio": _mv(None, unit="%"),
            "last_dividend": None,
            "history": [],
            "is_dividend_stock": False,
            "dividend_consistency": "none",
            "interpretation": "Interpretacja",
        },
        "key_events": {
            "positive": [],
            "negative": [],
            "upcoming_dates": [],
            "interpretation": "Interpretacja",
        },
        "advantages_risks": {
            "moat_score": 5,
            "moat_type": "operacyjny",
            "advantages": [],
            "risks": [],
            "interpretation": "Interpretacja",
        },
        "shareholders": {
            "free_float_pct": _mv(None, unit="%"),
            "institutional_ownership_pct": _mv(None, unit="%"),
            "insider_ownership_pct": _mv(None, unit="%"),
            "major_shareholders": [],
            "insider_transactions": [],
            "interpretation": "Interpretacja",
        },
        "verdict": {
            "overall_score": 5,
            "recommendation": "hold",
            "time_horizon": "medium",
            "price_target": _mv(None, unit="PLN"),
            "bull_case": {"title": "Bull", "description": "x", "probability": "medium", "catalysts_or_risks": []},
            "base_case": {"title": "Base", "description": "x", "probability": "high", "catalysts_or_risks": []},
            "bear_case": {"title": "Bear", "description": "x", "probability": "low", "catalysts_or_risks": []},
            "key_watchpoints": [],
            "valuation_matrix": {
                "current_quadrant": "C",
                "quadrants": {
                    "A": {"title": "A", "description": "A"},
                    "B": {"title": "B", "description": "B"},
                    "C": {"title": "C", "description": "C"},
                    "D": {"title": "D", "description": "D"},
                },
                "momentum": {"signal": "wait", "label": "Wait", "reasoning": "x"},
            },
            "interpretation": "Interpretacja",
        },
    }


class ExtractParsedPayloadTests(unittest.TestCase):
    def test_detects_truncated_json_validation_errors(self) -> None:
        error = Exception("Invalid JSON: EOF while parsing a string [type=json_invalid]")
        self.assertTrue(_is_likely_truncated_json_error(error))

    def test_does_not_treat_regular_schema_error_as_truncation(self) -> None:
        error = Exception("value is not a valid enum [type=literal_error]")
        self.assertFalse(_is_likely_truncated_json_error(error))

    def test_extracts_from_content_parsed(self) -> None:
        response = SimpleNamespace(
            output_parsed=None,
            output=[
                SimpleNamespace(
                    type="message",
                    status="completed",
                    content=[SimpleNamespace(type="output_text", parsed=_payload_dict(), text=None)],
                )
            ],
            output_text=None,
        )
        parsed = _extract_parsed_payload(response)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.company.name, "PBX")

    def test_extracts_from_output_text_json(self) -> None:
        response = SimpleNamespace(
            output_parsed=None,
            output=[
                SimpleNamespace(
                    type="web_search_call",
                    status="completed",
                    content=[],
                )
            ],
            output_text=json.dumps(_payload_dict()),
        )
        parsed = _extract_parsed_payload(response)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.verdict.recommendation, "hold")


class OpenAIClientGenerateTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        OpenAIEquityReportClient._models_without_temperature.clear()

    async def test_generate_passes_explicit_temperature(self) -> None:
        response = SimpleNamespace(
            output_parsed=_payload_dict(),
            output=[],
            output_text=None,
            usage=SimpleNamespace(input_tokens=123, output_tokens=456),
            model="gpt-5.4",
        )
        fake_parse = AsyncMock(return_value=response)
        client = OpenAIEquityReportClient()
        client.client = SimpleNamespace(responses=SimpleNamespace(parse=fake_parse))

        await client.generate(system_prompt="system", user_prompt="user")

        self.assertEqual(fake_parse.await_count, 1)
        kwargs = fake_parse.await_args.kwargs
        self.assertIn("temperature", kwargs)
        self.assertEqual(kwargs["temperature"], 0.0)

    async def test_generate_retries_without_temperature_when_model_rejects_it(self) -> None:
        response = SimpleNamespace(
            output_parsed=_payload_dict(),
            output=[],
            output_text=None,
            usage=SimpleNamespace(input_tokens=123, output_tokens=456),
            model="gpt-5.4",
        )
        httpx_request = httpx.Request("POST", "https://api.openai.com/v1/responses")
        httpx_response = httpx.Response(
            400,
            request=httpx_request,
            text=(
                '{"error":{"message":"Unsupported parameter: '
                '\\"temperature\\" is not supported with this model.","type":"invalid_request_error"}}'
            ),
        )
        error = APIStatusError(
            "Unsupported parameter: 'temperature' is not supported with this model.",
            response=httpx_response,
            body=None,
        )
        fake_parse = AsyncMock(side_effect=[error, response])
        client = OpenAIEquityReportClient()
        client.client = SimpleNamespace(responses=SimpleNamespace(parse=fake_parse))

        result = await client.generate(system_prompt="system", user_prompt="user")

        self.assertEqual(result.model, "gpt-5.4")
        self.assertEqual(fake_parse.await_count, 2)
        first_kwargs = fake_parse.await_args_list[0].kwargs
        second_kwargs = fake_parse.await_args_list[1].kwargs
        self.assertIn("temperature", first_kwargs)
        self.assertNotIn("temperature", second_kwargs)

    async def test_generate_remembers_model_without_temperature_after_first_failure(self) -> None:
        response = SimpleNamespace(
            output_parsed=_payload_dict(),
            output=[],
            output_text=None,
            usage=SimpleNamespace(input_tokens=123, output_tokens=456),
            model="gpt-5.4",
        )
        httpx_request = httpx.Request("POST", "https://api.openai.com/v1/responses")
        httpx_response = httpx.Response(
            400,
            request=httpx_request,
            text=(
                '{"error":{"message":"Unsupported parameter: '
                '\\"temperature\\" is not supported with this model.","type":"invalid_request_error"}}'
            ),
        )
        error = APIStatusError(
            "Unsupported parameter: 'temperature' is not supported with this model.",
            response=httpx_response,
            body=None,
        )
        fake_parse = AsyncMock(side_effect=[error, response, response])
        client = OpenAIEquityReportClient()
        client.client = SimpleNamespace(responses=SimpleNamespace(parse=fake_parse))

        await client.generate(system_prompt="system", user_prompt="user")
        await client.generate(system_prompt="system", user_prompt="user")

        self.assertEqual(fake_parse.await_count, 3)
        third_kwargs = fake_parse.await_args_list[2].kwargs
        self.assertNotIn("temperature", third_kwargs)


if __name__ == "__main__":  
    unittest.main()
