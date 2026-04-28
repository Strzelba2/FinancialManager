from __future__ import annotations

from typing import Any

from .ai_schema import EquityAiPayload


_NULLISH = {
    "",
    "-",
    "--",
    "n/a",
    "na",
    "none",
    "null",
    "unknown",
    "brak",
    "brak danych",
    "brak informacji",
    "nieznane",
    "nie dotyczy",
}


def _clean_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.lower() in _NULLISH:
        return None
    return text


def _clean_string_list(values: list[Any] | None, drop_question_mark_items: bool = False) -> list[str]:
    items: list[str] = []
    for raw in values or []:
        cleaned = _clean_optional_text(raw)
        if cleaned is None:
            continue
        if "?" in cleaned:
            if drop_question_mark_items:
                continue
            cleaned = cleaned.replace("?", "").strip()
        if not cleaned or cleaned.lower() in _NULLISH:
            continue
        if cleaned not in items:
            items.append(cleaned)
    return items


def _normalize_score(value: Any, default: float = 5.0) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return default
    if 10.0 < numeric <= 100.0:
        numeric = numeric / 10.0
    return round(min(max(numeric, 1.0), 10.0), 1)


def _history_row_has_numbers(row: dict[str, Any]) -> bool:
    numeric_keys = (
        "revenue",
        "ebitda",
        "ebitda_margin_pct",
        "net_income",
        "eps",
        "roe_pct",
        "net_debt_ebitda",
        "dividend_per_share",
    )
    return any(row.get(key) is not None for key in numeric_keys)


def sanitize_equity_ai_payload(
    payload: EquityAiPayload,
    symbol: str,
    mic: str,
    instrument_name: str | None,
    instrument_shortname: str | None,
    instrument_isin: str | None,
) -> EquityAiPayload:
    data = payload.model_dump(mode="json")

    company = data["company"]
    company["name"] = _clean_optional_text(company.get("name")) or instrument_shortname or symbol
    company["full_name"] = (
        _clean_optional_text(company.get("full_name"))
        or instrument_name
        or instrument_shortname
        or symbol
    )
    company["description"] = _clean_optional_text(company.get("description"))
    company["sector"] = _clean_optional_text(company.get("sector"))
    company["industry"] = _clean_optional_text(company.get("industry"))
    company["country"] = _clean_optional_text(company.get("country"))
    company["exchange"] = _clean_optional_text(company.get("exchange")) or mic
    company["founded"] = _clean_optional_text(company.get("founded"))
    company["ceo"] = _clean_optional_text(company.get("ceo"))
    company["ceo_since"] = _clean_optional_text(company.get("ceo_since"))
    company["headquarters"] = _clean_optional_text(company.get("headquarters"))
    company["is_leader_in"] = _clean_string_list(company.get("is_leader_in"))
    company["main_products"] = _clean_string_list(company.get("main_products"))
    company["key_competitors"] = _clean_string_list(
        company.get("key_competitors"),
        drop_question_mark_items=True,
    )
    company["market_position"] = _clean_optional_text(company.get("market_position"))
    company["website"] = _clean_optional_text(company.get("website"))
    company["isin"] = _clean_optional_text(company.get("isin")) or instrument_isin

    trend_condition = data["trend_condition"]
    trend_condition["positive_signals"] = _clean_string_list(trend_condition.get("positive_signals"))
    trend_condition["negative_signals"] = _clean_string_list(trend_condition.get("negative_signals"))
    trend_condition["history"] = [
        row for row in trend_condition.get("history", []) if _history_row_has_numbers(row)
    ]
    trend_scores = trend_condition["scores"]
    for score_key in (
        "profitability",
        "balance_sheet",
        "earnings_quality",
        "revenue_growth",
        "market_valuation",
        "management_quality",
        "competitive_advantage",
        "industry_outlook",
    ):
        trend_scores[score_key]["score"] = _normalize_score(trend_scores[score_key].get("score"))
    trend_scores["overall"] = _normalize_score(trend_scores.get("overall"))

    key_events = data["key_events"]
    for bucket in ("positive", "negative"):
        filtered: list[dict[str, Any]] = []
        for item in key_events.get(bucket, []):
            title = _clean_optional_text(item.get("title"))
            description = _clean_optional_text(item.get("description"))
            event_date = _clean_optional_text(item.get("date"))
            if title is None or description is None or event_date is None:
                continue
            item["title"] = title
            item["description"] = description
            item["date"] = event_date
            filtered.append(item)
        key_events[bucket] = filtered
    upcoming_dates: list[dict[str, Any]] = []
    for item in key_events.get("upcoming_dates", []):
        event = _clean_optional_text(item.get("event"))
        event_date = _clean_optional_text(item.get("date"))
        if event is None or event_date is None:
            continue
        item["event"] = event
        item["date"] = event_date
        upcoming_dates.append(item)
    key_events["upcoming_dates"] = upcoming_dates

    advantages_risks = data["advantages_risks"]
    advantages_risks["moat_score"] = _normalize_score(advantages_risks.get("moat_score"), default=5.0)
    advantages: list[dict[str, Any]] = []
    for item in advantages_risks.get("advantages", []):
        title = _clean_optional_text(item.get("title"))
        description = _clean_optional_text(item.get("description"))
        if title is None or description is None:
            continue
        item["title"] = title
        item["description"] = description
        advantages.append(item)
    advantages_risks["advantages"] = advantages
    risks: list[dict[str, Any]] = []
    for item in advantages_risks.get("risks", []):
        title = _clean_optional_text(item.get("title"))
        description = _clean_optional_text(item.get("description"))
        if title is None or description is None:
            continue
        item["title"] = title
        item["description"] = description
        risks.append(item)
    advantages_risks["risks"] = risks

    shareholders = data["shareholders"]
    major_shareholders: list[dict[str, Any]] = []
    for item in shareholders.get("major_shareholders", []):
        name = _clean_optional_text(item.get("name"))
        if name is None or "?" in name:
            continue
        item["name"] = name
        major_shareholders.append(item)
    shareholders["major_shareholders"] = major_shareholders
    insider_transactions: list[dict[str, Any]] = []
    for item in shareholders.get("insider_transactions", []):
        insider = _clean_optional_text(item.get("insider"))
        role = _clean_optional_text(item.get("role"))
        tx_date = _clean_optional_text(item.get("date"))
        if insider is None or role is None or tx_date is None:
            continue
        source_url = _clean_optional_text(item.get("source_url"))
        item["insider"] = insider
        item["role"] = role
        item["date"] = tx_date
        item["source_url"] = source_url
        insider_transactions.append(item)
    shareholders["insider_transactions"] = insider_transactions

    verdict = data["verdict"]
    verdict["overall_score"] = _normalize_score(verdict.get("overall_score"))
    verdict["key_watchpoints"] = _clean_string_list(verdict.get("key_watchpoints"))
    for case_key in ("bull_case", "base_case", "bear_case"):
        verdict[case_key]["title"] = _clean_optional_text(verdict[case_key].get("title")) or verdict[case_key]["title"]
        verdict[case_key]["description"] = (
            _clean_optional_text(verdict[case_key].get("description"))
            or verdict[case_key]["description"]
        )
        verdict[case_key]["catalysts_or_risks"] = _clean_string_list(
            verdict[case_key].get("catalysts_or_risks")
        )
    verdict["valuation_matrix"]["momentum"]["label"] = (
        _clean_optional_text(verdict["valuation_matrix"]["momentum"].get("label"))
        or verdict["valuation_matrix"]["momentum"]["label"]
    )
    verdict["valuation_matrix"]["momentum"]["reasoning"] = (
        _clean_optional_text(verdict["valuation_matrix"]["momentum"].get("reasoning"))
        or verdict["valuation_matrix"]["momentum"]["reasoning"]
    )

    return EquityAiPayload.model_validate(data)
