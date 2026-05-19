from __future__ import annotations

import asyncio
import io
import json
import logging
import re
import unicodedata
from calendar import monthrange
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any, Iterable
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from app.core.config import settings

from .ai_schema import EquityAiPayload
from .local_metrics import min_confidence, to_float
from .schemas import EquityReport


logger = logging.getLogger(__name__)


_SUPPORTED_MICS = {"XWAR", "XNCO"}
_MONTHS = {
    "sty": 1,
    "lut": 2,
    "mar": 3,
    "kwi": 4,
    "maj": 5,
    "cze": 6,
    "lip": 7,
    "sie": 8,
    "wrz": 9,
    "paz": 10,
    "lis": 11,
    "gru": 12,
}
_PLACEHOLDERS = {"", "-", "--", "brak", "null", "none", "n/a", "na"}
_NUMERIC_HTML_UNITS = {
    "rzis": "thousand_pln",
    "balance": "thousand_pln",
    "cashflow": "thousand_pln",
    "profitability": "ratio",
    "debt": "ratio",
    "liquidity": "ratio",
}
_BROWSER_LIKE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/136.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "Accept-Language": "pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}


class EquityWebSourceError(RuntimeError):
    pass


@dataclass
class WebMetric:
    value: float | int | None
    as_of: str
    unit: str | None = None
    confidence: str = "high"
    note: str | None = None

    def to_metric_value(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "as_of": self.as_of,
            "source": "manual",
            "confidence": self.confidence,
            "unit": self.unit,
            "note": self.note or "Uzupelniono z publicznego zrodla web dla GPW/NC.",
        }


@dataclass
class WebDividendRecord:
    year: int
    dividend_per_share: float | None
    payout_ratio_pct: float | None
    paid: bool
    yield_pct: float | None = None
    ex_date: str | None = None
    pay_date: str | None = None

    def to_history_item(self) -> dict[str, Any]:
        return {
            "year": self.year,
            "dividend_per_share": self.dividend_per_share,
            "yield_pct": self.yield_pct,
            "payout_ratio_pct": self.payout_ratio_pct,
            "paid": self.paid,
        }


@dataclass
class WebShareholder:
    name: str
    stake_pct: float
    as_of: str | None = None
    holder_type: str = "institutional"

    def to_shareholder_item(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "stake_pct": self.stake_pct,
            "type": self.holder_type,
            "change_direction": "unchanged",
        }


@dataclass
class WebNewsEvent:
    date: str
    title: str
    description: str
    impact: str
    confidence: str
    polarity: str
    source_name: str | None = None
    source_url: str | None = None

    def to_key_event_item(self) -> dict[str, Any]:
        source_parts = []
        if self.source_name:
            source_parts.append(self.source_name)
        if self.source_url:
            source_parts.append(self.source_url)
        source_note = f" Źródło: {'; '.join(source_parts)}." if source_parts else ""
        return {
            "date": self.date,
            "title": self.title,
            "description": f"{self.description}{source_note}",
            "impact": self.impact,
            "confidence": self.confidence,
        }

    def to_prompt_item(self) -> dict[str, Any]:
        return _prune_empty(asdict(self))


@dataclass
class WebInsiderTransaction:
    date: str
    insider: str
    role: str
    transaction_type: str
    shares: int
    price: float
    value: float
    currency: str
    source_url: str | None = None

    def to_schema_item(self) -> dict[str, Any]:
        return {
            "date": self.date,
            "insider": self.insider,
            "role": self.role,
            "type": self.transaction_type,
            "shares": self.shares,
            "price": self.price,
            "value": self.value,
            "currency": self.currency,
            "source_url": self.source_url,
        }

    def to_prompt_item(self) -> dict[str, Any]:
        return _prune_empty(asdict(self))


@dataclass
class WebUpcomingDate:
    date: str
    event: str
    date_type: str = "other"
    source_name: str | None = None
    source_url: str | None = None

    def to_upcoming_item(self) -> dict[str, Any]:
        source_parts = []
        if self.source_name:
            source_parts.append(self.source_name)
        if self.source_url:
            source_parts.append(self.source_url)
        source_note = f" (źródło: {'; '.join(source_parts)})" if source_parts else ""
        return {
            "date": self.date,
            "event": f"{self.event}{source_note}",
            "type": self.date_type,
        }

    def to_prompt_item(self) -> dict[str, Any]:
        return _prune_empty(asdict(self))


@dataclass
class WebHistoryRow:
    year: int
    revenue: float | None = None
    ebitda: float | None = None
    ebitda_margin_pct: float | None = None
    net_income: float | None = None
    eps: float | None = None
    roe_pct: float | None = None
    net_debt_ebitda: float | None = None
    dividend_per_share: float | None = None
    direction: str = "flat"

    def to_history_item(self) -> dict[str, Any]:
        return {
            "year": self.year,
            "revenue": self.revenue,
            "ebitda": self.ebitda,
            "ebitda_margin_pct": self.ebitda_margin_pct,
            "net_income": self.net_income,
            "eps": self.eps,
            "roe_pct": self.roe_pct,
            "net_debt_ebitda": self.net_debt_ebitda,
            "dividend_per_share": self.dividend_per_share,
            "direction": self.direction,
        }


@dataclass
class EquityWebSourceFacts:
    slug: str
    company_name: str | None = None
    full_name: str | None = None
    description: str | None = None
    sector: str | None = None
    industry: str | None = None
    country: str | None = "Polska"
    exchange: str | None = None
    headquarters: str | None = None
    website: str | None = None
    isin: str | None = None
    ceo: str | None = None
    shares_outstanding: WebMetric | None = None
    market_cap: WebMetric | None = None
    enterprise_value: WebMetric | None = None
    revenue_ttm: WebMetric | None = None
    ebitda_ttm: WebMetric | None = None
    net_income_ttm: WebMetric | None = None
    eps_ttm: WebMetric | None = None
    ebitda_margin: WebMetric | None = None
    roe: WebMetric | None = None
    roic: WebMetric | None = None
    ocf: WebMetric | None = None
    fcf: WebMetric | None = None
    bvps: WebMetric | None = None
    cash_and_equivalents: WebMetric | None = None
    net_debt: WebMetric | None = None
    net_debt_ebitda: WebMetric | None = None
    current_ratio: WebMetric | None = None
    quick_ratio: WebMetric | None = None
    interest_coverage: WebMetric | None = None
    de_ratio: WebMetric | None = None
    capex: WebMetric | None = None
    capex_to_depreciation: WebMetric | None = None
    total_assets: WebMetric | None = None
    equity: WebMetric | None = None
    payout_ratio: WebMetric | None = None
    pe_ratio: WebMetric | None = None
    ev_ebitda_ratio: WebMetric | None = None
    pb_ratio: WebMetric | None = None
    ps_ratio: WebMetric | None = None
    industry_pe_ratio: WebMetric | None = None
    industry_ev_ebitda_ratio: WebMetric | None = None
    industry_pb_ratio: WebMetric | None = None
    industry_ps_ratio: WebMetric | None = None
    dividend_history: list[WebDividendRecord] = field(default_factory=list)
    major_shareholders: list[WebShareholder] = field(default_factory=list)
    insider_transactions: list[WebInsiderTransaction] = field(default_factory=list)
    trend_history: list[WebHistoryRow] = field(default_factory=list)
    news_events: list[WebNewsEvent] = field(default_factory=list)
    upcoming_dates: list[WebUpcomingDate] = field(default_factory=list)

    def has_material_data(self) -> bool:
        metric_fields = (
            self.shares_outstanding,
            self.market_cap,
            self.enterprise_value,
            self.revenue_ttm,
            self.ebitda_ttm,
            self.net_income_ttm,
            self.ocf,
            self.fcf,
            self.cash_and_equivalents,
            self.net_debt,
            self.current_ratio,
            self.quick_ratio,
            self.de_ratio,
            self.total_assets,
            self.equity,
            self.bvps,
            self.payout_ratio,
            self.pe_ratio,
            self.ev_ebitda_ratio,
            self.pb_ratio,
            self.ps_ratio,
        )
        return any(item is not None and item.value is not None for item in metric_fields) or bool(
            self.dividend_history
            or self.major_shareholders
            or self.insider_transactions
            or self.trend_history
            or self.news_events
            or self.upcoming_dates
        )

    def to_prompt_dict(self) -> dict[str, Any]:
        peer_pe_anchor = _peer_price_anchor_from_eps(
            peer_ratio=self.industry_pe_ratio,
            eps=self.eps_ttm,
            metric_label="EPS TTM",
        )
        peer_ev_ebitda_anchor = _peer_price_anchor_from_ev_ebitda(
            peer_ratio=self.industry_ev_ebitda_ratio,
            ebitda=self.ebitda_ttm,
            net_debt=self.net_debt,
            shares=self.shares_outstanding,
        )
        peer_pb_anchor = _peer_price_anchor_from_equity_multiple(
            peer_ratio=self.industry_pb_ratio,
            base_metric=self.equity,
            shares=self.shares_outstanding,
            method_note="Peer P/B branzy * kapital wlasny / liczba akcji.",
        )
        peer_ps_anchor = _peer_price_anchor_from_equity_multiple(
            peer_ratio=self.industry_ps_ratio,
            base_metric=self.revenue_ttm,
            shares=self.shares_outstanding,
            method_note="Peer P/S branzy * przychody TTM / liczba akcji.",
        )
        payload = {
            "slug": self.slug,
            "company": {
                "name": self.company_name,
                "full_name": self.full_name,
                "description": self.description,
                "sector": self.sector,
                "industry": self.industry,
                "country": self.country,
                "exchange": self.exchange,
                "headquarters": self.headquarters,
                "website": self.website,
                "isin": self.isin,
                "ceo": self.ceo,
                "shares_outstanding": asdict(self.shares_outstanding) if self.shares_outstanding else None,
                "market_cap": asdict(self.market_cap) if self.market_cap else None,
                "enterprise_value": asdict(self.enterprise_value) if self.enterprise_value else None,
            },
            "fundamentals": {
                "revenue_ttm": asdict(self.revenue_ttm) if self.revenue_ttm else None,
                "ebitda_ttm": asdict(self.ebitda_ttm) if self.ebitda_ttm else None,
                "net_income_ttm": asdict(self.net_income_ttm) if self.net_income_ttm else None,
                "eps_ttm": asdict(self.eps_ttm) if self.eps_ttm else None,
                "ebitda_margin": asdict(self.ebitda_margin) if self.ebitda_margin else None,
                "roe": asdict(self.roe) if self.roe else None,
                "roic": asdict(self.roic) if self.roic else None,
                "ocf": asdict(self.ocf) if self.ocf else None,
                "fcf": asdict(self.fcf) if self.fcf else None,
                "bvps": asdict(self.bvps) if self.bvps else None,
            },
            "debt_balance": {
                "cash_and_equivalents": asdict(self.cash_and_equivalents) if self.cash_and_equivalents else None,
                "net_debt": asdict(self.net_debt) if self.net_debt else None,
                "net_debt_ebitda": asdict(self.net_debt_ebitda) if self.net_debt_ebitda else None,
                "current_ratio": asdict(self.current_ratio) if self.current_ratio else None,
                "quick_ratio": asdict(self.quick_ratio) if self.quick_ratio else None,
                "interest_coverage": asdict(self.interest_coverage) if self.interest_coverage else None,
                "de_ratio": asdict(self.de_ratio) if self.de_ratio else None,
                "capex": asdict(self.capex) if self.capex else None,
                "capex_to_depreciation": asdict(self.capex_to_depreciation) if self.capex_to_depreciation else None,
                "total_assets": asdict(self.total_assets) if self.total_assets else None,
                "equity": asdict(self.equity) if self.equity else None,
            },
            "dividend": {
                "payout_ratio": asdict(self.payout_ratio) if self.payout_ratio else None,
                "history": [item.to_history_item() for item in self.dividend_history[-5:]],
            },
            "shareholders": {
                "major_shareholders": [item.to_shareholder_item() for item in self.major_shareholders[:8]],
                "insider_transactions": [item.to_prompt_item() for item in self.insider_transactions[:8]],
            },
            "recent_news": [item.to_prompt_item() for item in self.news_events[:10]],
            "upcoming_dates": [item.to_prompt_item() for item in self.upcoming_dates[:8]],
            "valuation_ratios": {
                "pe_ratio": asdict(self.pe_ratio) if self.pe_ratio else None,
                "ev_ebitda": asdict(self.ev_ebitda_ratio) if self.ev_ebitda_ratio else None,
                "pb_ratio": asdict(self.pb_ratio) if self.pb_ratio else None,
                "ps_ratio": asdict(self.ps_ratio) if self.ps_ratio else None,
            },
            "valuation_benchmarks": {
                "industry_pe_ratio": asdict(self.industry_pe_ratio) if self.industry_pe_ratio else None,
                "industry_ev_ebitda": asdict(self.industry_ev_ebitda_ratio) if self.industry_ev_ebitda_ratio else None,
                "industry_pb_ratio": asdict(self.industry_pb_ratio) if self.industry_pb_ratio else None,
                "industry_ps_ratio": asdict(self.industry_ps_ratio) if self.industry_ps_ratio else None,
            },
            "valuation_anchors": {
                "peer_pe_implied_price": asdict(peer_pe_anchor) if peer_pe_anchor else None,
                "peer_ev_ebitda_implied_price": asdict(peer_ev_ebitda_anchor) if peer_ev_ebitda_anchor else None,
                "peer_pb_implied_price": asdict(peer_pb_anchor) if peer_pb_anchor else None,
                "peer_ps_implied_price": asdict(peer_ps_anchor) if peer_ps_anchor else None,
            },
            "trend_history": [item.to_history_item() for item in self.trend_history[-5:]],
        }
        return _prune_empty(payload)


@dataclass
class _TableRow:
    data_field: str | None
    label: str
    values: list[str | None]


@dataclass
class _ParsedTable:
    headers: list[str]
    rows: list[_TableRow]


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text).strip()
    if text.lower() in _PLACEHOLDERS:
        return None
    return text


def _normalize_key(value: str | None) -> str:
    raw = _clean_text(value) or ""
    normalized = unicodedata.normalize("NFKD", raw)
    normalized = normalized.encode("ascii", "ignore").decode("ascii")
    normalized = normalized.lower()
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return normalized.strip()


def _prune_empty(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, child in value.items():
            pruned = _prune_empty(child)
            if pruned in (None, "", [], {}):
                continue
            cleaned[key] = pruned
        return cleaned
    if isinstance(value, list):
        cleaned_items = []
        for child in value:
            pruned = _prune_empty(child)
            if pruned in (None, "", [], {}):
                continue
            cleaned_items.append(pruned)
        return cleaned_items
    return value


def _parse_decimal(value: str | None) -> float | int | None:
    text = _clean_text(value)
    if text is None:
        return None
    text = text.replace("\u2212", "-")
    text = re.sub(r"\s+", "", text)
    text = text.replace("%", "")
    text = text.replace("zł", "").replace("PLN", "").replace("x", "")
    text = text.replace(",", ".")
    if not text or text.lower() in _PLACEHOLDERS:
        return None
    match = re.search(r"[-+]?\d+(?:\.\d+)?", text)
    if match:
        text = match.group(0)
    try:
        number = float(text)
    except ValueError:
        return None
    if number.is_integer():
        return int(number)
    return number


def _scale_metric_value(raw: float | int | None, source_kind: str) -> float | int | None:
    if raw is None:
        return None
    if source_kind != "thousand_pln":
        return raw
    return int(float(raw) * 1000.0)


def _history_amount_from_thousand_pln(raw: float | int | None) -> float | None:
    if raw is None:
        return None
    return round(float(raw) / 1000.0, 1)


def _parse_date_iso_from_ddmmyyyy(value: str | None) -> str | None:
    text = _clean_text(value)
    if text is None:
        return None
    match = re.fullmatch(r"(\d{2})\.(\d{2})\.(\d{4})", text)
    if not match:
        return None
    day, month, year = match.groups()
    return f"{year}-{month}-{day}"


def _parse_iso_date_prefix(value: str | None) -> str | None:
    text = _clean_text(value)
    if text is None:
        return None
    match = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", text)
    if match:
        year, month, day = match.groups()
        return f"{year}-{month}-{day}"
    return _parse_date_iso_from_ddmmyyyy(text)


def _end_of_quarter(year: int, quarter: int) -> str:
    month = quarter * 3
    return f"{year:04d}-{month:02d}-{monthrange(year, month)[1]:02d}"


def _parse_header_as_of(header: str | None) -> str | None:
    text = _clean_text(header)
    if text is None:
        return None

    quarter_match = re.search(r"(\d{4})\s*/\s*Q([1-4])", text, flags=re.IGNORECASE)
    if quarter_match:
        return _end_of_quarter(int(quarter_match.group(1)), int(quarter_match.group(2)))

    o4k_match = re.search(r"O4K\s*\(([^)]+)\)", text, flags=re.IGNORECASE)
    if o4k_match:
        period_hint = o4k_match.group(1).lower()
        hint_match = re.search(r"([a-z]{3})\s*(\d{2})", period_hint)
        if hint_match:
            month_key, year_two_digits = hint_match.groups()
            month = _MONTHS.get(month_key)
            if month is not None:
                year = 2000 + int(year_two_digits)
                return f"{year:04d}-{month:02d}-{monthrange(year, month)[1]:02d}"

    year_month_match = re.search(r"(\d{4})\s*\(([a-z]{3})\s*(\d{2})\)", text, flags=re.IGNORECASE)
    if year_month_match:
        year, month_key, _ = year_month_match.groups()
        month = _MONTHS.get(month_key.lower())
        if month is not None:
            year_int = int(year)
            return f"{year_int:04d}-{month:02d}-{monthrange(year_int, month)[1]:02d}"

    year_match = re.fullmatch(r"(\d{4})", text)
    if year_match:
        return f"{int(year_match.group(1)):04d}-12-31"
    return None


def _parse_annual_year(header: str | None) -> int | None:
    text = _clean_text(header)
    if text is None:
        return None
    if "/Q" in text.upper() or text.upper().startswith("O4K"):
        return None
    match = re.match(r"(\d{4})", text)
    if not match:
        return None
    return int(match.group(1))


def _parse_quarter_header(header: str | None) -> tuple[int, int] | None:
    text = _clean_text(header)
    if text is None:
        return None
    match = re.search(r"(\d{4})\s*/\s*Q([1-4])", text, flags=re.IGNORECASE)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def _parse_trailing_period_year(header: str | None) -> int | None:
    text = _clean_text(header)
    if text is None:
        return None
    if not text.upper().startswith("O4K"):
        return None
    as_of = _parse_header_as_of(text)
    if as_of is None:
        return None
    return int(as_of[:4])


def _extract_profile_description(soup: BeautifulSoup) -> str | None:
    label = soup.find("label", string=re.compile(r"Profil działalności", re.IGNORECASE))
    if label is None:
        return None
    container = label.find_parent()
    if container is None:
        return None
    text = _clean_text(container.get_text(" ", strip=True))
    if text is None:
        return None
    text = re.sub(r"^Profil działalności[:\s]*", "", text, flags=re.IGNORECASE)
    return _clean_text(text)


def _extract_kv_mapping(soup: BeautifulSoup) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for row in soup.find_all("tr"):
        header_cell = row.find("th")
        value_cell = row.find("td")
        if header_cell is None or value_cell is None:
            continue
        key = _clean_text(header_cell.get_text(" ", strip=True))
        value = _clean_text(value_cell.get_text(" ", strip=True))
        if key is None or value is None:
            continue
        mapping[key.rstrip(":")] = value
    return mapping


def _classify_news_event(title: str) -> tuple[str, str, str]:
    normalized = _normalize_key(title)
    negative_keywords = (
        "zbycie akcji",
        "wypowiedzenie",
        "rezygnacja",
        "odwolanie",
        "spadek",
        "strata",
        "naruszenie",
        "kara",
        "pozew",
    )
    positive_keywords = (
        "nabycie akcji",
        "zawarcie znaczacej umowy",
        "znaczaca umowa",
        "wybuduje",
        "wzrost",
        "produkcji",
        "dywidenda",
    )
    high_keywords = ("znaczacej umowy", "wypowiedzenie", "nabycie akcji", "zbycie akcji")

    if any(keyword in normalized for keyword in negative_keywords):
        polarity = "negative"
    elif any(keyword in normalized for keyword in positive_keywords):
        polarity = "positive"
    else:
        polarity = "positive"

    impact = "medium" if any(keyword in normalized for keyword in high_keywords) else "low"
    return polarity, impact, "high"


def _is_insider_notice(title: str | None) -> bool:
    normalized = _normalize_key(title)
    return "nabycie akcji" in normalized or "zbycie akcji" in normalized


def _parse_compact_int(value: str | None) -> int | None:
    text = _clean_text(value)
    if text is None:
        return None
    text = re.sub(r"[^\d-]", "", text)
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _parse_polish_date_token(value: str | None) -> str | None:
    text = _clean_text(value)
    if text is None:
        return None
    iso_match = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", text)
    if iso_match:
        year, month, day = iso_match.groups()
        return f"{year}-{month}-{day}"
    match = re.fullmatch(r"(\d{2})[.-](\d{2})[.-](\d{4})", text)
    if not match:
        return _parse_date_iso_from_ddmmyyyy(text)
    day, month, year = match.groups()
    return f"{year}-{month}-{day}"


def _normalize_pdf_text(value: str) -> str:
    text = value.replace("\xa0", " ")
    text = text.replace("\u2212", "-")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _first_content_line(value: str | None) -> str | None:
    if value is None:
        return None
    for line in value.splitlines():
        cleaned = _clean_text(line)
        if cleaned:
            return cleaned
    return None


def _pdf_candidate_url(url: str | None) -> bool:
    if not url:
        return False
    normalized = url.lower()
    return (
        ".pdf" in normalized
        or "format=pdf" in normalized
        or "mime=application/pdf" in normalized
        or "/pdf/" in normalized
        or "/files/download/" in normalized
        or "/download/" in normalized
    )


def _pdf_candidate_hint(value: str | None) -> bool:
    normalized = _normalize_key(value)
    if not normalized:
        return False
    return any(
        token in normalized
        for token in ("pdf", "pobierz pdf", "zalacznik pdf", "attachment pdf", "application/pdf")
    )


def _extract_attachment_links(html: str, base_url: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    links: list[str] = []
    candidates = (
        ("a[href]", "href"),
        ("iframe[src]", "src"),
        ("embed[src]", "src"),
        ("object[data]", "data"),
    )
    for selector, attr_name in candidates:
        for node in soup.select(selector):
            target = node.get(attr_name) or ""
            if not target:
                continue
            hint_parts = [
                node.get_text(" ", strip=True),
                node.get("title"),
                node.get("aria-label"),
                node.get("type"),
            ]
            if not _pdf_candidate_url(target) and not any(_pdf_candidate_hint(part) for part in hint_parts):
                continue
            links.append(urljoin(base_url, target))
    for raw_target in re.findall(
        r"""["']([^"']*(?:\.pdf(?:\?[^"']*)?|/files/download/\d+|/download/[^"']+))["']""",
        html,
        flags=re.IGNORECASE,
    ):
        links.append(urljoin(base_url, raw_target))
    return _dedupe_by_key(links, lambda item: item)


def _extract_notice_text_from_html(html: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    for node in soup(["script", "style", "noscript"]):
        node.decompose()

    candidate_selectors = (
        "article",
        ".node",
        ".content",
        ".field--name-body",
        "#block-system-main",
        "main",
        "body",
    )
    for selector in candidate_selectors:
        node = soup.select_one(selector)
        if node is None:
            continue
        text = _normalize_pdf_text(node.get_text("\n", strip=True))
        if text:
            return text
    text = _normalize_pdf_text(soup.get_text("\n", strip=True))
    return text or None


def _extract_pdf_text(content: bytes) -> str | None:
    try:
        from pypdf import PdfReader
    except ImportError:
        logger.info("Cannot parse MAR PDF because optional dependency pypdf is not installed.")
        return None

    try:
        reader = PdfReader(io.BytesIO(content))
        pages = [page.extract_text() or "" for page in reader.pages]
    except Exception as exc:  # pragma: no cover - defensive around PDF parser internals
        logger.warning("Failed to parse MAR PDF attachment: %s", exc)
        return None
    text = _normalize_pdf_text("\n".join(pages))
    return text or None


def _parse_insider_transaction_from_text(
    text: str,
    fallback_title: str | None = None,
) -> WebInsiderTransaction | None:
    normalized_text = _normalize_pdf_text(text)
    normalized_key = _normalize_key(normalized_text)
    if not any(
        token in normalized_key
        for token in ("cena i wolumen", "cena oraz wolumen", "laczny wolumen", "wolumen")
    ):
        return None

    insider_match = re.search(
        r"a\)\s*Nazwa/Nazwisko\s*(.*?)\s*2\s+Powód powiadomienia",
        normalized_text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    insider = _first_content_line(insider_match.group(1) if insider_match else None)
    if insider is None:
        direct_insider_match = re.search(
            r"1\.?\s*Dane osoby.*?a\)\s*Nazwa(?:/Nazwisko)?\s*:?\s*(.*?)\s*2\.?\s*Powód powiadomienia",
            normalized_text,
            flags=re.DOTALL | re.IGNORECASE,
        )
        insider = _first_content_line(direct_insider_match.group(1) if direct_insider_match else None)
    if insider is None:
        # The ESPI/PAP MAR PDF is table-based and text extraction often places the
        # name after the section number rather than directly below the label.
        fallback_insider_match = re.search(
            r"\n3\s*\n+(.*?)\n",
            normalized_text,
            flags=re.DOTALL | re.IGNORECASE,
        )
        insider = _first_content_line(fallback_insider_match.group(1) if fallback_insider_match else None)

    role_match = re.search(
        r"a\)\s*Stanowisko/status\s*(.*?)\s*b\)\s*Pierwotne powiadomienie",
        normalized_text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    role = _clean_text(role_match.group(1).replace("\n", " ") if role_match else None)
    if role is None:
        fallback_role_match = re.search(
            r"(Osoba blisko związana.*?)(?:Pierwotne powiadomienie|Dane emitenta)",
            normalized_text,
            flags=re.DOTALL | re.IGNORECASE,
        )
        role = _clean_text(fallback_role_match.group(1).replace("\n", " ") if fallback_role_match else None)
    if role is None:
        manager_context_match = re.search(
            r"a\)\s*Imię\s+i\s+Nazwisko:\s*(.*?)\s*b\)\s*Stanowisko/Status:\s*(.*?)\s*c\)",
            normalized_text,
            flags=re.DOTALL | re.IGNORECASE,
        )
        manager_name = _first_content_line(manager_context_match.group(1) if manager_context_match else None)
        manager_role = _clean_text(manager_context_match.group(2).replace("\n", " ") if manager_context_match else None)
        if manager_name and manager_role:
            role = f"Osoba blisko związana z {manager_name}, {manager_role}"
        elif manager_role:
            role = f"Osoba blisko związana z osobą pełniącą obowiązki zarządcze ({manager_role})"

    type_match = re.search(
        r"b\)\s*Rodzaj transakcji\s*(Nabycie|Zbycie)",
        normalized_text,
        flags=re.IGNORECASE,
    )
    transaction_label = type_match.group(1).lower() if type_match else _normalize_key(fallback_title)
    if "nabycie" in transaction_label:
        transaction_type = "buy"
    elif "zbycie" in transaction_label:
        transaction_type = "sell"
    else:
        return None

    section_match = re.search(
        r"c\)\s*Cena(?:\s+i|\s+oraz)?\s+wolumen\s*(.*?)\s*d\)\s*Informacje zbiorcze",
        normalized_text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    section = section_match.group(1) if section_match else normalized_text
    price_entries = re.findall(
        r"(\d{2}[.-]\d{2}[.-]\d{4})\s*:\s*([0-9]+(?:[,.][0-9]+)?)\s*([A-Z]{3})",
        section,
    )
    volume_block_match = re.search(r"Wolumen\s*(.*)$", section, flags=re.DOTALL | re.IGNORECASE)
    volume_block = volume_block_match.group(1) if volume_block_match else ""
    volumes = [_parse_compact_int(item) for item in re.findall(r"(?m)^\s*(\d[\d\s]*)\s*$", volume_block)]
    volumes = [item for item in volumes if item is not None]

    transaction_parts: list[tuple[str, float, int, str]] = []
    if price_entries and len(price_entries) == len(volumes):
        for (raw_date, raw_price, currency), volume in zip(price_entries, volumes, strict=True):
            parsed_date = _parse_polish_date_token(raw_date)
            price = to_float(_parse_decimal(raw_price))
            if parsed_date is None or price is None:
                continue
            transaction_parts.append((parsed_date, float(price), volume, currency))

    if not transaction_parts:
        aggregate_volume_match = re.search(
            r"(?:Łączny|Laczny)\s+wolumen\s*:?\s*([0-9][0-9\s]*)",
            normalized_text,
            flags=re.IGNORECASE,
        )
        aggregate_volume = _parse_compact_int(aggregate_volume_match.group(1) if aggregate_volume_match else None)
        aggregate_price_lines = re.findall(
            r"([0-9\s]+)\s+akcji:\s*([0-9]+(?:[,.][0-9]+)?)\s*([A-Z]{3})",
            normalized_text,
            flags=re.IGNORECASE,
        )
        date_match = re.search(
            r"e\)\s*Data(?:\s+zawarcia)?(?:\s+transakcji)?\s*:?\s*(.*?)\s*f\)",
            normalized_text,
            flags=re.DOTALL | re.IGNORECASE,
        )
        date_tokens = re.findall(
            r"(?:\d{4}-\d{2}-\d{2}|\d{2}[.-]\d{2}[.-]\d{4})",
            date_match.group(1) if date_match else "",
        )
        parsed_dates = [_parse_polish_date_token(item) for item in date_tokens]
        parsed_dates = [item for item in parsed_dates if item is not None]
        if aggregate_price_lines and parsed_dates:
            for idx, (raw_volume, raw_price, currency) in enumerate(aggregate_price_lines):
                volume = _parse_compact_int(raw_volume)
                price = to_float(_parse_decimal(raw_price))
                parsed_date = parsed_dates[min(idx, len(parsed_dates) - 1)]
                if volume is None or price is None:
                    continue
                transaction_parts.append((parsed_date, float(price), volume, currency))
        elif aggregate_volume is not None and parsed_dates:
            price_match = re.search(
                r"(?:[-–—−]\s*)?Cena\s*:?\s*([0-9]+(?:[,.][0-9]+)?)\s*([A-Z]{3})",
                normalized_text,
                flags=re.IGNORECASE,
            )
            price = to_float(_parse_decimal(price_match.group(1) if price_match else None))
            currency = price_match.group(2) if price_match else "PLN"
            if price is not None:
                transaction_parts.append((parsed_dates[-1], float(price), aggregate_volume, currency))
        elif parsed_dates:
            aggregate_section_match = re.search(
                r"d\)\s*Informacje zbiorcze:?\s*(.*?)\s*e\)",
                normalized_text,
                flags=re.DOTALL | re.IGNORECASE,
            )
            aggregate_section = aggregate_section_match.group(1) if aggregate_section_match else section
            simple_aggregate_match = re.search(
                r"Cena:\s*([0-9]+(?:[,.][0-9]+)?)\s*([A-Z]{3}).*?Wolumen:\s*([0-9\s]+)",
                aggregate_section,
                flags=re.DOTALL | re.IGNORECASE,
            )
            price = to_float(_parse_decimal(simple_aggregate_match.group(1) if simple_aggregate_match else None))
            currency = simple_aggregate_match.group(2) if simple_aggregate_match else "PLN"
            volume = _parse_compact_int(simple_aggregate_match.group(3) if simple_aggregate_match else None)
            if price is not None and volume is not None:
                transaction_parts.append((parsed_dates[-1], float(price), volume, currency))

    if not transaction_parts or insider is None:
        return None

    shares = sum(item[2] for item in transaction_parts)
    if shares <= 0:
        return None
    total_value = sum(price * volume for _, price, volume, _ in transaction_parts)
    currency = transaction_parts[0][3]
    latest_date = max(item[0] for item in transaction_parts)
    weighted_price = total_value / shares

    return WebInsiderTransaction(
        date=latest_date,
        insider=insider,
        role=role or "Osoba blisko związana z osobą pełniącą obowiązki zarządcze",
        transaction_type=transaction_type,
        shares=shares,
        price=round(weighted_price, 4),
        value=round(total_value, 2),
        currency=currency,
    )


def _dedupe_by_key(items: Iterable[Any], key_factory) -> list[Any]:
    seen: set[str] = set()
    result: list[Any] = []
    for item in items:
        key = key_factory(item)
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _annual_row_value_by_year(table: _ParsedTable | None, row: _TableRow | None, year: int) -> float | int | None:
    if table is None or row is None:
        return None
    for idx, header in enumerate(table.headers):
        annual_year = _parse_annual_year(header)
        quarter = _parse_quarter_header(header)
        trailing_year = _parse_trailing_period_year(header)
        is_year_match = annual_year == year
        is_q4_match = quarter == (year, 4)
        is_trailing_match = trailing_year == year
        if not (is_year_match or is_q4_match or is_trailing_match):
            continue
        if idx >= len(row.values):
            return None
        return _parse_decimal(row.values[idx])
    return None


def _extract_table(html: str) -> _ParsedTable | None:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", class_=re.compile(r"report-table"))
    if table is None:
        table = soup.find("table")
    if table is None:
        return None

    header_row = table.find("tr")
    if header_row is None:
        return None
    header_cells = header_row.find_all(["th", "td"], recursive=False)
    headers = [_clean_text(cell.get_text(" ", strip=True)) or "" for cell in header_cells[1:]]

    rows: list[_TableRow] = []
    for row in table.find_all("tr")[1:]:
        cells = row.find_all("td", recursive=False)
        if len(cells) < 2:
            continue
        label_cell = cells[0]
        label = _clean_text(label_cell.get_text(" ", strip=True)) or ""
        values: list[str | None] = []
        for cell in cells[1:]:
            value_node = cell.select_one(".value")
            raw_value = value_node.get_text(" ", strip=True) if value_node is not None else cell.get_text(" ", strip=True)
            values.append(_clean_text(raw_value))
        rows.append(
            _TableRow(
                data_field=row.get("data-field"),
                label=label,
                values=values,
            )
        )
    return _ParsedTable(headers=headers, rows=rows)


def _find_row(table: _ParsedTable | None, *keys: str, label_contains: Iterable[str] = ()) -> _TableRow | None:
    if table is None:
        return None

    normalized_keys = {_normalize_key(item) for item in keys if item}
    normalized_contains = [_normalize_key(item) for item in label_contains if item]

    for row in table.rows:
        row_keys = {
            _normalize_key(row.data_field),
            _normalize_key(row.label),
        }
        if normalized_keys.intersection(row_keys):
            return row
        label_key = _normalize_key(row.label)
        if any(item in label_key for item in normalized_contains):
            return row
    return None


def _latest_metric_from_table(
    table: _ParsedTable | None,
    source_kind: str,
    unit: str | None,
    confidence: str = "high",
    keys: tuple[str, ...] = (),
    label_contains: tuple[str, ...] = (),
) -> WebMetric | None:
    row = _find_row(table, *keys, label_contains=label_contains)
    if row is None or not row.values or not table.headers:
        return None
    last_idx = min(len(row.values), len(table.headers)) - 1
    for idx in range(last_idx, -1, -1):
        as_of = _parse_header_as_of(table.headers[idx])
        if as_of is None:
            continue
        raw_value = _parse_decimal(row.values[idx])
        value = _scale_metric_value(raw_value, source_kind=source_kind)
        if value is None:
            continue
        return WebMetric(value=value, as_of=as_of, unit=unit, confidence=confidence)
    return None


def _parse_peer_decimal(value: str | None) -> float | int | None:
    text = _clean_text(value)
    if text is None:
        return None
    match = re.search(r"~\s*bran(?:za|ża)\s*([-+]?\d+(?:[,.]\d+)?)", text, flags=re.IGNORECASE)
    if not match:
        return None
    return _parse_decimal(match.group(1))


def _latest_peer_metric_from_table(
    table: _ParsedTable | None,
    unit: str | None,
    confidence: str = "medium",
    keys: tuple[str, ...] = (),
    label_contains: tuple[str, ...] = (),
) -> WebMetric | None:
    row = _find_row(table, *keys, label_contains=label_contains)
    if row is None or not row.values or not table.headers:
        return None
    last_idx = min(len(row.values), len(table.headers)) - 1
    for idx in range(last_idx, -1, -1):
        as_of = _parse_header_as_of(table.headers[idx])
        if as_of is None:
            continue
        value = _parse_peer_decimal(row.values[idx])
        if value is None:
            continue
        return WebMetric(
            value=value,
            as_of=as_of,
            unit=unit,
            confidence=confidence,
            note="Benchmark ~branza z publicznego zrodla web dla GPW/NC.",
        )
    return None


def _peer_price_anchor_from_equity_multiple(
    peer_ratio: WebMetric | None,
    base_metric: WebMetric | None,
    shares: WebMetric | None,
    method_note: str,
) -> WebMetric | None:
    peer_value = to_float(peer_ratio.value) if peer_ratio else None
    base_value = to_float(base_metric.value) if base_metric else None
    shares_value = to_float(shares.value) if shares else None
    if peer_value is None or base_value is None or shares_value in (None, 0):
        return None
    if base_value <= 0 or peer_value <= 0:
        return None
    implied_price = (peer_value * base_value) / shares_value
    if implied_price <= 0:
        return None
    return WebMetric(
        value=round(implied_price, 2),
        as_of=(peer_ratio.as_of if peer_ratio else "") or (base_metric.as_of if base_metric else "") or (shares.as_of if shares else ""),
        unit="PLN",
        confidence=min_confidence(
            peer_ratio.confidence if peer_ratio else None,
            base_metric.confidence if base_metric else None,
            shares.confidence if shares else None,
        ),
        note=method_note,
    )


def _peer_price_anchor_from_eps(
    peer_ratio: WebMetric | None,
    eps: WebMetric | None,
    metric_label: str = "EPS TTM",
) -> WebMetric | None:
    peer_value = to_float(peer_ratio.value) if peer_ratio else None
    eps_value = to_float(eps.value) if eps else None
    if peer_value is None or eps_value is None:
        return None
    if peer_value <= 0 or eps_value <= 0:
        return None
    implied_price = peer_value * eps_value
    return WebMetric(
        value=round(implied_price, 2),
        as_of=(peer_ratio.as_of if peer_ratio else "") or (eps.as_of if eps else ""),
        unit="PLN",
        confidence=min_confidence(
            peer_ratio.confidence if peer_ratio else None,
            eps.confidence if eps else None,
        ),
        note=f"Peer P/E branzy * {metric_label}.",
    )


def _peer_price_anchor_from_ev_ebitda(
    peer_ratio: WebMetric | None,
    ebitda: WebMetric | None,
    net_debt: WebMetric | None,
    shares: WebMetric | None,
) -> WebMetric | None:
    peer_value = to_float(peer_ratio.value) if peer_ratio else None
    ebitda_value = to_float(ebitda.value) if ebitda else None
    net_debt_value = to_float(net_debt.value) if net_debt else None
    shares_value = to_float(shares.value) if shares else None
    if peer_value is None or ebitda_value is None or net_debt_value is None or shares_value in (None, 0):
        return None
    if peer_value <= 0 or ebitda_value <= 0:
        return None
    implied_equity_value = (peer_value * ebitda_value) - net_debt_value
    if implied_equity_value <= 0:
        return None
    implied_price = implied_equity_value / shares_value
    if implied_price <= 0:
        return None
    return WebMetric(
        value=round(implied_price, 2),
        as_of=(peer_ratio.as_of if peer_ratio else "") or (ebitda.as_of if ebitda else "") or (net_debt.as_of if net_debt else ""),
        unit="PLN",
        confidence=min_confidence(
            peer_ratio.confidence if peer_ratio else None,
            ebitda.confidence if ebitda else None,
            net_debt.confidence if net_debt else None,
            shares.confidence if shares else None,
        ),
        note="Peer EV/EBITDA branzy * EBITDA TTM, potem EV - dlug netto, podzielone przez liczbe akcji.",
    )


def _guess_shareholder_type(name: str) -> str:
    normalized = _normalize_key(name)
    if any(token in normalized for token in ("ofe", "tfi", "fund", "investment", "asset", "allianz", "nationale")):
        return "institutional"
    if any(token in normalized for token in ("skarb panstwa", "state")):
        return "state"
    return "strategic"


def _history_direction(current: WebHistoryRow, previous: WebHistoryRow | None) -> str:
    if previous is None:
        return "flat"
    positive = 0
    negative = 0
    for current_value, previous_value in (
        (current.revenue, previous.revenue),
        (current.ebitda, previous.ebitda),
        (current.net_income, previous.net_income),
    ):
        if current_value is None or previous_value is None:
            continue
        if current_value > previous_value:
            positive += 1
        elif current_value < previous_value:
            negative += 1
    if positive > negative:
        return "up"
    if negative > positive:
        return "down"
    return "flat"


def merge_web_source_facts(
    payload: EquityAiPayload,
    facts: EquityWebSourceFacts | None,
) -> EquityAiPayload:
    if facts is None or not facts.has_material_data():
        return payload

    data = payload.model_dump(mode="json")

    def _metric_missing(metric: dict[str, Any] | None) -> bool:
        if not metric:
            return True
        return metric.get("value") is None

    def _text_missing(value: Any) -> bool:
        cleaned = _clean_text(str(value) if value is not None else None)
        return cleaned is None

    def _dividend_history_missing(history: list[dict[str, Any]] | None) -> bool:
        if not history:
            return True
        for item in history:
            if item.get("dividend_per_share") is not None or item.get("payout_ratio_pct") is not None:
                return False
        return True

    def _trend_history_missing(history: list[dict[str, Any]] | None) -> bool:
        if not history:
            return True
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
        for item in history:
            if any(item.get(key) is not None for key in numeric_keys):
                return False
        return True

    def _apply_metric(section: dict[str, Any], key: str, metric: WebMetric | None, override: bool = True) -> None:
        if metric is None or metric.value is None:
            return
        if override or _metric_missing(section.get(key)):
            section[key] = metric.to_metric_value()

    company = data["company"]
    if _text_missing(company.get("name")) and facts.company_name:
        company["name"] = facts.company_name
    if _text_missing(company.get("full_name")) and facts.full_name:
        company["full_name"] = facts.full_name
    if _text_missing(company.get("description")) and facts.description:
        company["description"] = facts.description
    if _text_missing(company.get("sector")) and facts.sector:
        company["sector"] = facts.sector
    if _text_missing(company.get("industry")) and facts.industry:
        company["industry"] = facts.industry
    if _text_missing(company.get("country")) and facts.country:
        company["country"] = facts.country
    if _text_missing(company.get("exchange")) and facts.exchange:
        company["exchange"] = facts.exchange
    if _text_missing(company.get("headquarters")) and facts.headquarters:
        company["headquarters"] = facts.headquarters
    if _text_missing(company.get("website")) and facts.website:
        company["website"] = facts.website
    if _text_missing(company.get("isin")) and facts.isin:
        company["isin"] = facts.isin
    if _text_missing(company.get("ceo")) and facts.ceo:
        company["ceo"] = facts.ceo
    _apply_metric(company, "shares_outstanding", facts.shares_outstanding)

    fundamentals = data["fundamentals"]
    _apply_metric(fundamentals, "revenue_ttm", facts.revenue_ttm)
    _apply_metric(fundamentals, "ebitda_ttm", facts.ebitda_ttm)
    _apply_metric(fundamentals, "net_income_ttm", facts.net_income_ttm)
    _apply_metric(fundamentals, "eps_ttm", facts.eps_ttm)
    _apply_metric(fundamentals, "ebitda_margin", facts.ebitda_margin)
    _apply_metric(fundamentals, "roe", facts.roe)
    _apply_metric(fundamentals, "roic", facts.roic)
    _apply_metric(fundamentals, "ocf", facts.ocf)
    _apply_metric(fundamentals, "fcf", facts.fcf)
    _apply_metric(fundamentals, "bvps", facts.bvps)

    debt_balance = data["debt_balance"]
    _apply_metric(debt_balance, "cash_and_equivalents", facts.cash_and_equivalents)
    _apply_metric(debt_balance, "net_debt", facts.net_debt)
    _apply_metric(debt_balance, "net_debt_ebitda", facts.net_debt_ebitda)
    _apply_metric(debt_balance, "current_ratio", facts.current_ratio)
    _apply_metric(debt_balance, "quick_ratio", facts.quick_ratio)
    _apply_metric(debt_balance, "interest_coverage", facts.interest_coverage)
    _apply_metric(debt_balance, "de_ratio", facts.de_ratio)
    _apply_metric(debt_balance, "capex", facts.capex)
    _apply_metric(debt_balance, "capex_to_depreciation", facts.capex_to_depreciation)
    _apply_metric(debt_balance, "total_assets", facts.total_assets)
    _apply_metric(debt_balance, "equity", facts.equity)

    if _metric_missing(fundamentals.get("eps_ttm")):
        net_income_value = to_float((fundamentals.get("net_income_ttm") or {}).get("value"))
        shares_value = to_float((company.get("shares_outstanding") or {}).get("value"))
        if net_income_value is not None and shares_value not in (None, 0):
            fundamentals["eps_ttm"] = WebMetric(
                value=round(net_income_value / shares_value, 4),
                as_of=(fundamentals.get("net_income_ttm") or {}).get("as_of") or (company.get("shares_outstanding") or {}).get("as_of") or "",
                unit="PLN",
                confidence=min_confidence(
                    (fundamentals.get("net_income_ttm") or {}).get("confidence"),
                    (company.get("shares_outstanding") or {}).get("confidence"),
                ),
                note="Wyliczone z zysku netto i liczby akcji z publicznego zrodla web dla GPW/NC.",
            ).to_metric_value()

    if _metric_missing(fundamentals.get("ebitda_margin")):
        revenue_value = to_float((fundamentals.get("revenue_ttm") or {}).get("value"))
        ebitda_value = to_float((fundamentals.get("ebitda_ttm") or {}).get("value"))
        if revenue_value not in (None, 0) and ebitda_value is not None:
            fundamentals["ebitda_margin"] = WebMetric(
                value=round((ebitda_value / revenue_value) * 100.0, 2),
                as_of=(fundamentals.get("revenue_ttm") or {}).get("as_of") or "",
                unit="%",
                confidence=min_confidence(
                    (fundamentals.get("revenue_ttm") or {}).get("confidence"),
                    (fundamentals.get("ebitda_ttm") or {}).get("confidence"),
                ),
                note="Wyliczone z przychodow i EBITDA z publicznego zrodla web dla GPW/NC.",
            ).to_metric_value()

    if _metric_missing(fundamentals.get("ocf")):
        fcf_value = to_float((fundamentals.get("fcf") or {}).get("value"))
        capex_value = to_float((debt_balance.get("capex") or {}).get("value"))
        if fcf_value is not None and capex_value is not None:
            fundamentals["ocf"] = WebMetric(
                value=round(fcf_value + capex_value, 2),
                as_of=(fundamentals.get("fcf") or {}).get("as_of") or (debt_balance.get("capex") or {}).get("as_of") or "",
                unit="PLN",
                confidence=min_confidence(
                    (fundamentals.get("fcf") or {}).get("confidence"),
                    (debt_balance.get("capex") or {}).get("confidence"),
                ),
                note="Przyblizenie: OCF ~= FCF + CAPEX, gdy brak osobnej pozycji CFO.",
            ).to_metric_value()

    if _metric_missing(fundamentals.get("bvps")):
        equity_value = to_float((debt_balance.get("equity") or {}).get("value"))
        shares_value = to_float((company.get("shares_outstanding") or {}).get("value"))
        if equity_value is not None and shares_value not in (None, 0):
            fundamentals["bvps"] = WebMetric(
                value=round(equity_value / shares_value, 4),
                as_of=(debt_balance.get("equity") or {}).get("as_of") or (company.get("shares_outstanding") or {}).get("as_of") or "",
                unit="PLN",
                confidence=min_confidence(
                    (debt_balance.get("equity") or {}).get("confidence"),
                    (company.get("shares_outstanding") or {}).get("confidence"),
                ),
                note="Wyliczone z kapitalu wlasnego i liczby akcji z publicznego zrodla web dla GPW/NC.",
            ).to_metric_value()

    if _metric_missing(debt_balance.get("capex_to_depreciation")):
        capex_value = to_float((debt_balance.get("capex") or {}).get("value"))
        if capex_value is not None and facts.capex_to_depreciation is not None and facts.capex_to_depreciation.value is not None:
            _apply_metric(debt_balance, "capex_to_depreciation", facts.capex_to_depreciation)

    dividend = data["dividend"]
    _apply_metric(dividend, "payout_ratio", facts.payout_ratio)
    if facts.dividend_history:
        dividend["history"] = [item.to_history_item() for item in sorted(facts.dividend_history, key=lambda row: row.year)]
    if facts.dividend_history:
        latest_paid = max(
            (row for row in facts.dividend_history if row.dividend_per_share is not None and row.paid),
            key=lambda row: row.year,
            default=None,
        )
        if latest_paid is not None and latest_paid.ex_date and latest_paid.pay_date:
            dividend["last_dividend"] = {
                "amount": latest_paid.dividend_per_share,
                "currency": "PLN",
                "ex_date": latest_paid.ex_date,
                "pay_date": latest_paid.pay_date,
            }
    if facts.dividend_history:
        paid_years = [row for row in sorted(facts.dividend_history, key=lambda item: item.year) if row.paid and row.dividend_per_share]
        if paid_years:
            dividend["is_dividend_stock"] = True
            dividend["dividend_consistency"] = (
                "consistent"
                if len(paid_years) >= 3 and all(row.year == paid_years[-1].year - idx for idx, row in enumerate(reversed(paid_years[-3:])))
                else "irregular"
            )

    shareholders = data["shareholders"]
    if not shareholders.get("major_shareholders") and facts.major_shareholders:
        shareholders["major_shareholders"] = [
            item.to_shareholder_item() for item in facts.major_shareholders if item.stake_pct >= 5.0
        ]
    if facts.insider_transactions:
        existing_transactions = shareholders.get("insider_transactions", [])
        fact_transactions = [item.to_schema_item() for item in facts.insider_transactions]
        shareholders["insider_transactions"] = _dedupe_by_key(
            [*fact_transactions, *existing_transactions],
            lambda item: (
                f"{item.get('date')}:{_normalize_key(item.get('insider'))}:"
                f"{item.get('type')}:{item.get('shares')}:{item.get('value')}"
            ),
        )[:8]

    holder_items = shareholders.get("major_shareholders") or []
    if holder_items:
        holder_as_of = max((item.as_of for item in facts.major_shareholders if item.as_of), default=None) or date.today().isoformat()
        known_stake = sum(float(item.get("stake_pct") or 0.0) for item in holder_items)
        free_float = max(0.0, min(100.0, 100.0 - known_stake))
        shareholders["free_float_pct"] = WebMetric(
            value=round(free_float, 2),
            as_of=holder_as_of,
            unit="%",
            note="Wyliczone jako 100% minus suma ujawnionych pakietow >5%.",
        ).to_metric_value()
        institutional = sum(
            float(item.get("stake_pct") or 0.0)
            for item in holder_items
            if item.get("type") == "institutional"
        )
        shareholders["institutional_ownership_pct"] = WebMetric(
            value=round(institutional, 2) if institutional > 0 else None,
            as_of=holder_as_of,
            unit="%",
            confidence="medium" if institutional > 0 else "low",
            note="Suma ujawnionych akcjonariuszy instytucjonalnych >5%.",
        ).to_metric_value()

    trend_condition = data["trend_condition"]
    if facts.trend_history:
        trend_condition["history"] = [item.to_history_item() for item in facts.trend_history]

    key_events = data["key_events"]
    if facts.news_events:
        existing_positive = key_events.get("positive", [])
        existing_negative = key_events.get("negative", [])
        fact_positive = [item.to_key_event_item() for item in facts.news_events if item.polarity == "positive"]
        fact_negative = [item.to_key_event_item() for item in facts.news_events if item.polarity == "negative"]
        key_events["positive"] = _dedupe_by_key(
            [*fact_positive, *existing_positive],
            lambda item: f"{item.get('date')}:{_normalize_key(item.get('title'))}",
        )[:8]
        key_events["negative"] = _dedupe_by_key(
            [*fact_negative, *existing_negative],
            lambda item: f"{item.get('date')}:{_normalize_key(item.get('title'))}",
        )[:8]

    if facts.upcoming_dates:
        existing_upcoming = key_events.get("upcoming_dates", [])
        fact_upcoming = [item.to_upcoming_item() for item in facts.upcoming_dates]
        key_events["upcoming_dates"] = _dedupe_by_key(
            [*fact_upcoming, *existing_upcoming],
            lambda item: f"{item.get('date')}:{_normalize_key(item.get('event'))}",
        )[:8]

    return EquityAiPayload.model_validate(data)


def merge_web_source_report_metrics(
    report: EquityReport,
    facts: EquityWebSourceFacts | None,
) -> EquityReport:
    if facts is None or not facts.has_material_data():
        return report

    data = report.model_dump(mode="json")

    def _apply_report_metric(section: dict[str, Any], key: str, metric: WebMetric | None, allow_null: bool = False) -> None:
        if metric is None:
            return
        if metric.value is None and not allow_null:
            return
        section[key] = metric.to_metric_value()

    fundamentals = data["fundamentals"]
    _apply_report_metric(fundamentals, "ocf", facts.ocf)
    _apply_report_metric(fundamentals, "pe_ratio", facts.pe_ratio, allow_null=True)
    _apply_report_metric(fundamentals, "ev_ebitda", facts.ev_ebitda_ratio)
    _apply_report_metric(fundamentals, "pb_ratio", facts.pb_ratio)
    _apply_report_metric(fundamentals, "ps_ratio", facts.ps_ratio)
    _apply_report_metric(fundamentals, "bvps", facts.bvps)

    if facts.market_cap is not None and facts.market_cap.value is not None:
        data["company"]["price"]["market_cap"] = round(float(facts.market_cap.value), 2)

    return EquityReport.model_validate(data)


class EquityWebSourceClient:
    def __init__(self) -> None:
        self.base_url = settings.EQUITY_WEB_SOURCE_BASE_URL.rstrip("/")
        self.timeout_s = settings.EQUITY_WEB_SOURCE_TIMEOUT_S
        # Use browser-like defaults so upstream HTML sources do not see an obvious custom bot signature.
        self._client = httpx.AsyncClient(
            timeout=self.timeout_s,
            follow_redirects=True,
            headers=_BROWSER_LIKE_HEADERS,
        )
        self._listing_cache: dict[str, dict[str, str]] = {}

    async def aclose(self) -> None:
        await self._client.aclose()

    async def fetch_facts(
        self,
        mic: str,
        symbol: str,
        shortname: str | None = None,
    ) -> EquityWebSourceFacts | None:
        if mic not in _SUPPORTED_MICS:
            return None

        slug = await self._resolve_slug(mic=mic, symbol=symbol, shortname=shortname)
        if slug is None:
            logger.info("Equity web source could not resolve slug mic=%s symbol=%s shortname=%s", mic, symbol, shortname)
            return None

        pages = await self._fetch_pages(slug)
        facts = EquityWebSourceFacts(slug=slug, company_name=shortname or symbol, exchange=mic)
        self._parse_profile_page(facts, pages.get("profile"))
        self._parse_financial_pages(
            facts,
            market_html=pages.get("market"),
            profitability_html=pages.get("profitability"),
            debt_html=pages.get("debt"),
            liquidity_html=pages.get("liquidity"),
            rzis_html=pages.get("rzis"),
            balance_html=pages.get("balance"),
            cashflow_html=pages.get("cashflow"),
        )
        self._parse_dividend_page(facts, pages.get("dividend"))
        self._parse_shareholders_page(facts, pages.get("shareholders"))
        self._parse_news_page(facts, pages.get("news"))
        await self._fetch_insider_transactions(facts)
        self._derive_history(facts, profitability_html=pages.get("profitability"), rzis_html=pages.get("rzis"), debt_html=pages.get("debt"))

        if not facts.has_material_data():
            return None
        return facts

    async def _fetch_pages(self, slug: str) -> dict[str, str | None]:
        page_paths = {
            "profile": f"/notowania/{slug}",
            "rzis": f"/raporty-finansowe-rachunek-zyskow-i-strat/{slug}",
            "balance": f"/raporty-finansowe-bilans/{slug}",
            "cashflow": f"/raporty-finansowe-przeplywy-pieniezne/{slug}",
            "dividend": f"/dywidenda/{slug}",
            "shareholders": f"/akcjonariat/{slug}",
            "news": f"/wiadomosci/{slug}",
            "market": f"/wskazniki-wartosci-rynkowej/{slug}",
            "profitability": f"/wskazniki-rentownosci/{slug}",
            "cashflow_indicators": f"/wskazniki-przeplywow-pienieznych/{slug}",
            "debt": f"/wskazniki-zadluzenia/{slug}",
            "liquidity": f"/wskazniki-plynnosci/{slug}",
        }
        results = await asyncio.gather(
            *(self._safe_get(path) for path in page_paths.values()),
            return_exceptions=False,
        )
        return dict(zip(page_paths.keys(), results, strict=True))

    async def _safe_get(self, path: str) -> str | None:
        url = urljoin(f"{self.base_url}/", path.lstrip("/"))
        try:
            response = await self._client.get(url)
            response.raise_for_status()
            return response.text
        except httpx.HTTPError as exc:
            logger.warning("Equity web source request failed url=%s error=%s", url, exc)
            return None

    async def _safe_get_bytes(self, url: str) -> bytes | None:
        try:
            response = await self._client.get(url)
            response.raise_for_status()
            return response.content
        except httpx.HTTPError as exc:
            logger.warning("Equity web source binary request failed url=%s error=%s", url, exc)
            return None

    async def _resolve_slug(self, mic: str, symbol: str, shortname: str | None) -> str | None:
        listing_path = settings.EQUITY_WEB_SOURCE_GPW_LISTING_PATH if mic == "XWAR" else settings.EQUITY_WEB_SOURCE_NC_LISTING_PATH
        cache_key = f"{mic}:{listing_path}"
        if cache_key not in self._listing_cache:
            html = await self._safe_get(listing_path)
            if html is None:
                return None
            self._listing_cache[cache_key] = self._parse_listing(html)

        symbol_key = _normalize_key(symbol)
        shortname_key = _normalize_key(shortname)
        listing = self._listing_cache[cache_key]
        if symbol_key in listing:
            return listing[symbol_key]
        if shortname_key and shortname_key in listing:
            return listing[shortname_key]
        return None

    def _parse_listing(self, html: str) -> dict[str, str]:
        soup = BeautifulSoup(html, "html.parser")
        mapping: dict[str, str] = {}
        for link in soup.select('a[href^="/notowania/"]'):
            href = link.get("href") or ""
            slug = href.split("/notowania/")[-1].split("?")[0].strip("/")
            if not slug:
                continue
            text = _clean_text(link.get_text(" ", strip=True))
            if text is None:
                continue
            match = re.match(r"^([A-Z0-9-]+)\s+\((.+)\)$", text)
            if match:
                symbol, shortname = match.groups()
                mapping[_normalize_key(symbol)] = slug
                mapping[_normalize_key(shortname)] = slug
                continue
            mapping[_normalize_key(text)] = slug
        return mapping

    def _parse_profile_page(self, facts: EquityWebSourceFacts, html: str | None) -> None:
        if html is None:
            return
        soup = BeautifulSoup(html, "html.parser")
        mapping = _extract_kv_mapping(soup)
        description = _extract_profile_description(soup)

        facts.full_name = facts.full_name or mapping.get("Nazwa")
        facts.description = facts.description or description
        facts.sector = facts.sector or mapping.get("Branża")
        facts.industry = facts.industry or mapping.get("Branża")
        facts.headquarters = facts.headquarters or mapping.get("Adres")
        facts.website = facts.website or mapping.get("WWW")
        facts.isin = facts.isin or mapping.get("ISIN")
        facts.ceo = facts.ceo or mapping.get("CEO")
        shares_outstanding = _parse_decimal(mapping.get("Liczba akcji"))
        if shares_outstanding is not None:
            facts.shares_outstanding = WebMetric(
                value=shares_outstanding,
                as_of=date.today().isoformat(),
                unit="akcji",
            )
        market_cap = _parse_decimal(mapping.get("Kapitalizacja"))
        if market_cap is not None:
            facts.market_cap = WebMetric(
                value=market_cap,
                as_of=date.today().isoformat(),
                unit="PLN",
            )
        enterprise_value = _parse_decimal(mapping.get("Enterprise Value"))
        if enterprise_value is not None:
            facts.enterprise_value = WebMetric(
                value=enterprise_value,
                as_of=date.today().isoformat(),
                unit="PLN",
            )

        page_text = soup.get_text(" ", strip=True)
        next_report_match = re.search(
            r"Najbliższy raport okresowy:\s*(.+?)\s+(\d{4}-\d{2}-\d{2})",
            page_text,
            flags=re.IGNORECASE,
        )
        if next_report_match:
            report_name, report_date = next_report_match.groups()
            event_name = _clean_text(report_name) or "Najbliższy raport okresowy"
            facts.upcoming_dates.append(
                WebUpcomingDate(
                    date=report_date,
                    event=event_name,
                    date_type="earnings",
                    source_name="publiczne źródło web GPW/NC",
                    source_url=urljoin(f"{self.base_url}/", f"notowania/{facts.slug}"),
                )
            )

    def _parse_financial_pages(
        self,
        facts: EquityWebSourceFacts,
        market_html: str | None,
        profitability_html: str | None,
        debt_html: str | None,
        liquidity_html: str | None,
        rzis_html: str | None,
        balance_html: str | None,
        cashflow_html: str | None,
    ) -> None:
        market = _extract_table(market_html) if market_html else None
        profitability = _extract_table(profitability_html) if profitability_html else None
        debt = _extract_table(debt_html) if debt_html else None
        liquidity = _extract_table(liquidity_html) if liquidity_html else None
        rzis = _extract_table(rzis_html) if rzis_html else None
        balance = _extract_table(balance_html) if balance_html else None
        cashflow = _extract_table(cashflow_html) if cashflow_html else None

        facts.pe_ratio = _latest_metric_from_table(
            market,
            source_kind="ratio",
            unit="x",
            keys=("CZ",),
            label_contains=("Cena / Zysk",),
        )
        facts.industry_pe_ratio = _latest_peer_metric_from_table(
            market,
            unit="x",
            keys=("CZ",),
            label_contains=("Cena / Zysk",),
        )
        facts.ev_ebitda_ratio = _latest_metric_from_table(
            market,
            source_kind="ratio",
            unit="x",
            keys=("EVEBITDA",),
            label_contains=("EV / EBITDA",),
        )
        facts.industry_ev_ebitda_ratio = _latest_peer_metric_from_table(
            market,
            unit="x",
            keys=("EVEBITDA",),
            label_contains=("EV / EBITDA",),
        )
        facts.pb_ratio = _latest_metric_from_table(
            market,
            source_kind="ratio",
            unit="x",
            keys=("CWK",),
            label_contains=("Cena / Wartość księgowa",),
        )
        facts.industry_pb_ratio = _latest_peer_metric_from_table(
            market,
            unit="x",
            keys=("CWK",),
            label_contains=("Cena / Wartość księgowa",),
        )
        facts.ps_ratio = _latest_metric_from_table(
            market,
            source_kind="ratio",
            unit="x",
            keys=("CP",),
            label_contains=("Cena / Przychody",),
        )
        market_eps = _latest_metric_from_table(
            market,
            source_kind="absolute",
            unit="PLN",
            keys=("EarningsPerShare", "EPS", "Zysk na akcję"),
        )
        facts.industry_ps_ratio = _latest_peer_metric_from_table(
            market,
            unit="x",
            keys=("CP",),
            label_contains=("Cena / Przychody",),
        )
        market_shares = _latest_metric_from_table(
            market,
            source_kind="absolute",
            unit="akcji",
            keys=("ShareAmount",),
            label_contains=("Liczba akcji",),
        )
        if market_shares is not None and market_shares.value is not None:
            facts.shares_outstanding = market_shares

        facts.revenue_ttm = _latest_metric_from_table(
            rzis,
            source_kind=_NUMERIC_HTML_UNITS["rzis"],
            unit="PLN",
            keys=("IncomeRevenues",),
        )
        facts.ebitda_ttm = _latest_metric_from_table(
            rzis,
            source_kind=_NUMERIC_HTML_UNITS["rzis"],
            unit="PLN",
            keys=("IncomeEBITDA",),
        )
        facts.net_income_ttm = _latest_metric_from_table(
            rzis,
            source_kind=_NUMERIC_HTML_UNITS["rzis"],
            unit="PLN",
            keys=("IncomeShareholderNetProfit",),
        )
        if market_eps is not None and market_eps.value is not None:
            facts.eps_ttm = market_eps
        facts.cash_and_equivalents = _latest_metric_from_table(
            balance,
            source_kind=_NUMERIC_HTML_UNITS["balance"],
            unit="PLN",
            keys=("BalanceCash",),
        )
        facts.total_assets = _latest_metric_from_table(
            balance,
            source_kind=_NUMERIC_HTML_UNITS["balance"],
            unit="PLN",
            keys=("BalanceTotalAssets",),
        )
        facts.equity = _latest_metric_from_table(
            balance,
            source_kind=_NUMERIC_HTML_UNITS["balance"],
            unit="PLN",
            keys=("BalanceCapital",),
        )
        facts.fcf = _latest_metric_from_table(
            cashflow,
            source_kind=_NUMERIC_HTML_UNITS["cashflow"],
            unit="PLN",
            keys=("CashflowFCM",),
        )
        facts.ocf = _latest_metric_from_table(
            cashflow,
            source_kind=_NUMERIC_HTML_UNITS["cashflow"],
            unit="PLN",
            keys=(
                "CashflowOperating",
                "CashflowOperational",
                "CashflowOperations",
                "CashflowNetOperating",
                "Przepływy pieniężne z działalności operacyjnej",
                "Przepływy pieniężne netto z działalności operacyjnej",
            ),
        )
        facts.capex = _latest_metric_from_table(
            cashflow,
            source_kind=_NUMERIC_HTML_UNITS["cashflow"],
            unit="PLN",
            keys=("CashflowCapex",),
        )
        amortization = _latest_metric_from_table(
            cashflow,
            source_kind=_NUMERIC_HTML_UNITS["cashflow"],
            unit="PLN",
            keys=("CashflowAmortization",),
        )
        facts.roe = _latest_metric_from_table(
            profitability,
            source_kind=_NUMERIC_HTML_UNITS["profitability"],
            unit="%",
            keys=("ROE",),
            label_contains=("ROE",),
        )
        facts.roic = _latest_metric_from_table(
            profitability,
            source_kind=_NUMERIC_HTML_UNITS["profitability"],
            unit="%",
            keys=("ROIC",),
            label_contains=("ROIC",),
        )
        facts.quick_ratio = _latest_metric_from_table(
            liquidity,
            source_kind=_NUMERIC_HTML_UNITS["liquidity"],
            unit="x",
            keys=("QR",),
            label_contains=("Płynność szybka",),
        )
        facts.current_ratio = _latest_metric_from_table(
            liquidity,
            source_kind=_NUMERIC_HTML_UNITS["liquidity"],
            unit="x",
            keys=("CR",),
            label_contains=("Płynność bieżąca",),
        )
        facts.de_ratio = _latest_metric_from_table(
            debt,
            source_kind=_NUMERIC_HTML_UNITS["debt"],
            unit="x",
            keys=("CG",),
            label_contains=("Zadłużenie kapitału własnego",),
        )
        facts.net_debt = _latest_metric_from_table(
            debt,
            source_kind="absolute",
            unit="PLN",
            keys=("DebtFin",),
            label_contains=("Zadłużenie finansowe netto",),
        )
        facts.net_debt_ebitda = _latest_metric_from_table(
            debt,
            source_kind=_NUMERIC_HTML_UNITS["debt"],
            unit="x",
            keys=("DebtFinEBITDA",),
            label_contains=("Zadłużenie finansowe netto / EBITDA",),
        )
        facts.interest_coverage = _latest_metric_from_table(
            debt,
            source_kind=_NUMERIC_HTML_UNITS["debt"],
            unit="x",
            keys=("InterestCoverage", "IC"),
            label_contains=("Pokrycie odsetek", "Interest coverage"),
        )

        if facts.revenue_ttm and facts.ebitda_ttm and facts.revenue_ttm.value not in (None, 0) and facts.ebitda_ttm.value is not None:
            facts.ebitda_margin = WebMetric(
                value=round((float(facts.ebitda_ttm.value) / float(facts.revenue_ttm.value)) * 100.0, 2),
                as_of=facts.revenue_ttm.as_of,
                unit="%",
                confidence=min_confidence(facts.revenue_ttm.confidence, facts.ebitda_ttm.confidence),
                note="Wyliczone z przychodow i EBITDA z publicznego zrodla web dla GPW/NC.",
            )

        if facts.eps_ttm is None and facts.net_income_ttm and facts.shares_outstanding and facts.net_income_ttm.value is not None and facts.shares_outstanding.value not in (None, 0):
            facts.eps_ttm = WebMetric(
                value=round(float(facts.net_income_ttm.value) / float(facts.shares_outstanding.value), 4),
                as_of=facts.net_income_ttm.as_of,
                unit="PLN",
                confidence=min_confidence(facts.net_income_ttm.confidence, facts.shares_outstanding.confidence),
                note="Wyliczone z zysku netto i liczby akcji z publicznego zrodla web dla GPW/NC.",
            )

        if facts.ocf is None and facts.fcf and facts.capex and facts.fcf.value is not None and facts.capex.value is not None:
            ocf_confidence = min_confidence(facts.fcf.confidence, facts.capex.confidence)
            if ocf_confidence == "high":
                ocf_confidence = "medium"
            facts.ocf = WebMetric(
                value=round(float(facts.fcf.value) + float(facts.capex.value), 2),
                as_of=facts.fcf.as_of or facts.capex.as_of,
                unit="PLN",
                confidence=ocf_confidence,
                note="Przyblizenie: OCF ~= FCF + CAPEX, gdy zrodlo nie publikuje osobnej pozycji CFO.",
            )

        if facts.equity and facts.shares_outstanding and facts.equity.value is not None and facts.shares_outstanding.value not in (None, 0):
            facts.bvps = WebMetric(
                value=round(float(facts.equity.value) / float(facts.shares_outstanding.value), 4),
                as_of=facts.equity.as_of or facts.shares_outstanding.as_of,
                unit="PLN",
                confidence=min_confidence(facts.equity.confidence, facts.shares_outstanding.confidence),
                note="Wyliczone z kapitalu wlasnego i liczby akcji z publicznego zrodla web dla GPW/NC.",
            )

        if facts.capex and amortization and facts.capex.value is not None and amortization.value not in (None, 0):
            facts.capex_to_depreciation = WebMetric(
                value=round(float(facts.capex.value) / float(amortization.value), 2),
                as_of=facts.capex.as_of,
                unit="x",
                confidence=min_confidence(facts.capex.confidence, amortization.confidence),
                note="Wyliczone z CAPEX i amortyzacji z publicznego zrodla web dla GPW/NC.",
            )

    def _parse_dividend_page(self, facts: EquityWebSourceFacts, html: str | None) -> None:
        if html is None:
            return
        soup = BeautifulSoup(html, "html.parser")

        chart_match = re.search(r"var\s+chartsDataAll\s*=\s*(\{.*?\});", html, flags=re.DOTALL)
        payout_by_year: dict[int, float | None] = {}
        if chart_match:
            try:
                raw_chart_data = json.loads(chart_match.group(1))
            except json.JSONDecodeError:
                raw_chart_data = {}
            for year_text, row in raw_chart_data.items():
                if not str(year_text).isdigit():
                    continue
                payout = row.get("UZN")
                payout_by_year[int(year_text)] = round(float(payout) * 100.0, 2) if payout not in (None, 0, 0.0) else None

        table = soup.find("table")
        if table is None:
            return

        header_cells = [
            _normalize_key(cell.get_text(" ", strip=True))
            for cell in table.find("tr").find_all(["th", "td"], recursive=False)
        ] if table.find("tr") is not None else []

        def _index_by_label(*labels: str, fallback: int) -> int:
            normalized_labels = [_normalize_key(label) for label in labels]
            for idx, header in enumerate(header_cells):
                if any(label in header for label in normalized_labels):
                    return idx
            return fallback

        records: list[WebDividendRecord] = []
        for row in table.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) < 3:
                continue
            year = _parse_decimal(cells[0].get_text(" ", strip=True))
            if not isinstance(year, int):
                continue
            dps_idx = _index_by_label("łącznie dywidenda na akcję", "dywidenda na akcję", fallback=2 if len(cells) >= 10 else 1)
            yield_idx = _index_by_label("stopa dywidendy", fallback=5)
            status_idx = _index_by_label("status", fallback=6)
            ex_idx = _index_by_label("ostatnie notowanie z prawem do dywidendy", "prawo do dywidendy", fallback=8 if len(cells) >= 10 else 3)
            pay_idx = _index_by_label("dzień wypłaty", "dzien wyplaty", fallback=9 if len(cells) >= 10 else 4)

            dps = to_float(_parse_decimal(cells[dps_idx].get_text(" ", strip=True))) if dps_idx < len(cells) else None
            yield_pct = to_float(_parse_decimal(cells[yield_idx].get_text(" ", strip=True))) if yield_idx < len(cells) else None
            status = _clean_text(cells[status_idx].get_text(" ", strip=True)) if status_idx < len(cells) else None
            ex_date = _parse_date_iso_from_ddmmyyyy(cells[ex_idx].get_text(" ", strip=True)) if ex_idx < len(cells) else None
            pay_date = _parse_date_iso_from_ddmmyyyy(cells[pay_idx].get_text(" ", strip=True)) if pay_idx < len(cells) else None
            paid = dps is not None and dps > 0 and (status is None or _normalize_key(status) != "brak")
            records.append(
                WebDividendRecord(
                    year=year,
                    dividend_per_share=dps,
                    payout_ratio_pct=payout_by_year.get(year),
                    paid=paid,
                    yield_pct=yield_pct,
                    ex_date=ex_date,
                    pay_date=pay_date,
                )
            )

        facts.dividend_history = sorted(records, key=lambda item: item.year)
        latest_with_payout = next(
            (
                item for item in reversed(facts.dividend_history)
                if item.payout_ratio_pct is not None
            ),
            None,
        )
        if latest_with_payout is not None:
            latest_as_of = latest_with_payout.pay_date or latest_with_payout.ex_date or f"{latest_with_payout.year}-12-31"
            facts.payout_ratio = WebMetric(
                value=latest_with_payout.payout_ratio_pct,
                as_of=latest_as_of,
                unit="%",
            )

    def _parse_shareholders_page(self, facts: EquityWebSourceFacts, html: str | None) -> None:
        if html is None:
            return
        soup = BeautifulSoup(html, "html.parser")
        sections = soup.find_all("table")
        holders: list[WebShareholder] = []
        for table in sections:
            for row in table.find_all("tr"):
                cells = row.find_all("td")
                if len(cells) < 7:
                    continue
                name = _clean_text(cells[0].get_text(" ", strip=True))
                stake_pct = to_float(_parse_decimal(cells[1].get_text(" ", strip=True)))
                updated_at = _parse_date_iso_from_ddmmyyyy(cells[6].get_text(" ", strip=True))
                if name is None or stake_pct is None:
                    continue
                if _normalize_key(name) == "razem":
                    continue
                holders.append(
                    WebShareholder(
                        name=name,
                        stake_pct=round(float(stake_pct), 4),
                        as_of=updated_at,
                        holder_type=_guess_shareholder_type(name),
                    )
                )

        deduped: dict[str, WebShareholder] = {}
        for item in holders:
            deduped[_normalize_key(item.name)] = item
        facts.major_shareholders = sorted(
            (item for item in deduped.values() if item.stake_pct >= 5.0),
            key=lambda item: item.stake_pct,
            reverse=True,
        )

    def _parse_news_page(self, facts: EquityWebSourceFacts, html: str | None) -> None:
        if html is None:
            return
        soup = BeautifulSoup(html, "html.parser")

        news_events: list[WebNewsEvent] = []
        upcoming_dates: list[WebUpcomingDate] = list(facts.upcoming_dates)
        for record in soup.select(".record.record-type-NEWS"):
            link = record.select_one(".record-header a[href]")
            if link is None:
                continue
            title = _clean_text(link.get_text(" ", strip=True))
            if title is None:
                continue
            date_text = _clean_text(record.select_one(".record-date").get_text(" ", strip=True)) if record.select_one(".record-date") else None
            event_date = _parse_iso_date_prefix(date_text)
            if event_date is None:
                continue
            source_link = record.select_one(".record-author")
            source_name = _clean_text(source_link.get_text(" ", strip=True)) if source_link else None
            source_url = urljoin(f"{self.base_url}/", link.get("href") or "")
            polarity, impact, confidence = _classify_news_event(title)
            normalized_title = _normalize_key(title)

            if not any(
                keyword in normalized_title
                for keyword in (
                    "nabycie akcji",
                    "zbycie akcji",
                    "znaczaca umowa",
                    "zawarcie znaczacej umowy",
                    "wypowiedzenie",
                    "produkcji",
                    "wybuduje",
                    "dywidenda",
                    "termin publikacji",
                    "terminu publikacji",
                )
            ):
                continue

            news_events.append(
                WebNewsEvent(
                    date=event_date,
                    title=title,
                    description="Komunikat lub publikacja powiazana ze spolka znaleziona w publicznym kanale wiadomosci.",
                    impact=impact,
                    confidence=confidence,
                    polarity=polarity,
                    source_name=source_name,
                    source_url=source_url,
                )
            )

        facts.news_events = _dedupe_by_key(
            sorted(news_events, key=lambda item: item.date, reverse=True),
            lambda item: f"{item.date}:{_normalize_key(item.title)}",
        )[:10]
        facts.upcoming_dates = _dedupe_by_key(
            sorted(upcoming_dates, key=lambda item: item.date),
            lambda item: f"{item.date}:{_normalize_key(item.event)}",
        )[:8]

    async def _fetch_insider_transactions(self, facts: EquityWebSourceFacts) -> None:
        insider_events = [
            event for event in facts.news_events
            if event.source_url and _is_insider_notice(event.title)
        ][:5]
        if not insider_events:
            return

        async def _fetch_event(event: WebNewsEvent) -> WebInsiderTransaction | None:
            html = await self._safe_get(event.source_url or "")
            if html is None:
                logger.debug(
                    "Insider notice page missing html title=%s url=%s",
                    event.title,
                    event.source_url,
                )
                return None
            attachment_links = _extract_attachment_links(html, event.source_url or self.base_url)
            logger.debug(
                "Insider notice candidate title=%s url=%s attachment_count=%s",
                event.title,
                event.source_url,
                len(attachment_links),
            )
            for attachment_url in attachment_links[:3]:
                content = await self._safe_get_bytes(attachment_url)
                if not content:
                    logger.debug(
                        "Insider notice attachment missing content title=%s attachment=%s",
                        event.title,
                        attachment_url,
                    )
                    continue
                text = _extract_pdf_text(content)
                text_source = "pdf"
                if text is None:
                    html_fallback = _extract_notice_text_from_html(content.decode("utf-8", errors="ignore"))
                    text = html_fallback
                    text_source = "html_attachment"
                if text is None:
                    logger.debug(
                        "Insider notice attachment yielded no text title=%s attachment=%s",
                        event.title,
                        attachment_url,
                    )
                    continue
                transaction = _parse_insider_transaction_from_text(text, fallback_title=event.title)
                if transaction is not None:
                    transaction.source_url = attachment_url
                    return transaction
                logger.debug(
                    "Insider notice attachment text not parsed title=%s attachment=%s source=%s",
                    event.title,
                    attachment_url,
                    text_source,
                )
            notice_text = _extract_notice_text_from_html(html)
            if notice_text is None:
                logger.debug(
                    "Insider notice page yielded no fallback text title=%s url=%s",
                    event.title,
                    event.source_url,
                )
                return None
            transaction = _parse_insider_transaction_from_text(notice_text, fallback_title=event.title)
            if transaction is not None:
                transaction.source_url = event.source_url
                return transaction
            logger.debug(
                "Insider notice page text not parsed title=%s url=%s",
                event.title,
                event.source_url,
            )
            return None

        parsed = await asyncio.gather(*(_fetch_event(event) for event in insider_events), return_exceptions=True)
        transactions: list[WebInsiderTransaction] = []
        for item in parsed:
            if isinstance(item, Exception):
                logger.warning("Failed to parse insider transaction notice: %s", item)
                continue
            if item is not None:
                transactions.append(item)
        logger.debug(
            "Parsed insider transactions slug=%s parsed=%s requested=%s",
            facts.slug,
            len(transactions),
            len(insider_events),
        )
        facts.insider_transactions = _dedupe_by_key(
            sorted(transactions, key=lambda item: item.date, reverse=True),
            lambda item: f"{item.date}:{_normalize_key(item.insider)}:{item.transaction_type}:{item.shares}:{item.value}",
        )[:8]

    def _derive_history(
        self,
        facts: EquityWebSourceFacts,
        profitability_html: str | None,
        rzis_html: str | None,
        debt_html: str | None,
    ) -> None:
        profitability = _extract_table(profitability_html) if profitability_html else None
        rzis = _extract_table(rzis_html) if rzis_html else None
        debt = _extract_table(debt_html) if debt_html else None
        if rzis is None:
            return

        annual_indexes: list[tuple[int, int]] = []
        for idx, header in enumerate(rzis.headers):
            year = _parse_annual_year(header)
            if year is not None:
                annual_indexes.append((idx, year))

        latest_trailing_index: tuple[int, int] | None = None
        for idx, header in enumerate(rzis.headers):
            trailing_year = _parse_trailing_period_year(header)
            if trailing_year is not None:
                latest_trailing_index = (idx, trailing_year)

        selected_indexes = annual_indexes[-5:]
        if latest_trailing_index is not None:
            trailing_idx, trailing_year = latest_trailing_index
            if not selected_indexes or selected_indexes[-1][1] < trailing_year:
                selected_indexes = [*selected_indexes[-4:], (trailing_idx, trailing_year)]

        if not selected_indexes:
            return

        revenue_row = _find_row(rzis, "IncomeRevenues")
        ebitda_row = _find_row(rzis, "IncomeEBITDA")
        net_income_row = _find_row(rzis, "IncomeShareholderNetProfit")
        roe_row = _find_row(profitability, "ROE", label_contains=("ROE",))
        nde_row = _find_row(debt, "DebtFinEBITDA", label_contains=("Zadłużenie finansowe netto / EBITDA",))
        dividends_by_year = {row.year: row.dividend_per_share for row in facts.dividend_history}
        shares_value = to_float(facts.shares_outstanding.value) if facts.shares_outstanding else None

        history: list[WebHistoryRow] = []
        for idx, year in selected_indexes:
            revenue_raw = _parse_decimal(revenue_row.values[idx] if revenue_row and idx < len(revenue_row.values) else None)
            ebitda_raw = _parse_decimal(ebitda_row.values[idx] if ebitda_row and idx < len(ebitda_row.values) else None)
            net_income_raw = _parse_decimal(net_income_row.values[idx] if net_income_row and idx < len(net_income_row.values) else None)
            revenue = _history_amount_from_thousand_pln(revenue_raw)
            ebitda = _history_amount_from_thousand_pln(ebitda_raw)
            net_income = _history_amount_from_thousand_pln(net_income_raw)
            if latest_trailing_index is not None and idx == latest_trailing_index[0]:
                roe = to_float(facts.roe.value) if facts.roe else None
                nde = to_float(facts.net_debt_ebitda.value) if facts.net_debt_ebitda else None
            else:
                roe = to_float(_annual_row_value_by_year(profitability, roe_row, year))
                nde = to_float(_annual_row_value_by_year(debt, nde_row, year))
            ebitda_margin = (
                round((float(ebitda_raw) / float(revenue_raw)) * 100.0, 2)
                if revenue_raw not in (None, 0) and ebitda_raw is not None
                else None
            )
            eps = (
                round((net_income * 1_000_000.0) / shares_value, 4)
                if net_income is not None and shares_value not in (None, 0)
                else None
            )
            history.append(
                WebHistoryRow(
                    year=year,
                    revenue=revenue,
                    ebitda=ebitda,
                    ebitda_margin_pct=ebitda_margin,
                    net_income=net_income,
                    eps=eps,
                    roe_pct=roe,
                    net_debt_ebitda=nde,
                    dividend_per_share=dividends_by_year.get(year),
                )
            )

        previous: WebHistoryRow | None = None
        for row in history:
            row.direction = _history_direction(row, previous)
            previous = row
        facts.trend_history = history


def report_payload_needs_enrichment(payload: EquityAiPayload | dict[str, Any] | None) -> bool:
    if payload is None:
        return True
    if not isinstance(payload, EquityAiPayload):
        payload = EquityAiPayload.model_validate(payload)

    missing_count = 0
    for metric in (
        payload.company.shares_outstanding,
        payload.fundamentals.revenue_ttm,
        payload.fundamentals.ebitda_ttm,
        payload.fundamentals.net_income_ttm,
        payload.fundamentals.ocf,
        payload.fundamentals.fcf,
        payload.fundamentals.bvps,
        payload.debt_balance.cash_and_equivalents,
        payload.debt_balance.net_debt,
        payload.debt_balance.current_ratio,
        payload.debt_balance.quick_ratio,
        payload.debt_balance.total_assets,
        payload.debt_balance.equity,
        payload.dividend.payout_ratio,
    ):
        if metric.value is None or metric.source == "openai":
            missing_count += 1

    if _dividend_history_is_sparse(payload.dividend.history):
        missing_count += 2
    if not payload.shareholders.major_shareholders:
        missing_count += 2
    if _trend_history_is_sparse(payload.trend_condition.history):
        missing_count += 2
    return missing_count >= 4


def final_report_payload_needs_enrichment(payload: EquityReport | dict[str, Any] | None) -> bool:
    if payload is None:
        return True
    if not isinstance(payload, EquityReport):
        payload = EquityReport.model_validate(payload)

    missing_count = 0
    for metric in (
        payload.fundamentals.revenue_ttm,
        payload.fundamentals.ebitda_ttm,
        payload.fundamentals.net_income_ttm,
        payload.fundamentals.ocf,
        payload.fundamentals.fcf,
        payload.fundamentals.bvps,
        payload.debt_balance.cash_and_equivalents,
        payload.debt_balance.net_debt,
        payload.debt_balance.current_ratio,
        payload.debt_balance.quick_ratio,
        payload.debt_balance.total_assets,
        payload.debt_balance.equity,
        payload.dividend.payout_ratio,
    ):
        if metric.value is None or metric.source == "openai":
            missing_count += 1

    for metric in (
        payload.fundamentals.pe_ratio,
        payload.fundamentals.ev_ebitda,
        payload.fundamentals.pb_ratio,
        payload.fundamentals.ps_ratio,
    ):
        if metric.source == "local":
            missing_count += 1

    if _dividend_history_is_sparse(payload.dividend.history):
        missing_count += 2
    if not payload.shareholders.major_shareholders:
        missing_count += 2
    if _trend_history_is_sparse(payload.trend_condition.history):
        missing_count += 2
    return missing_count >= 4


def _dividend_history_is_sparse(history: Iterable[Any] | None) -> bool:
    if not history:
        return True
    for item in history:
        dividend_per_share = getattr(item, "dividend_per_share", None)
        payout_ratio_pct = getattr(item, "payout_ratio_pct", None)
        if isinstance(item, dict):
            dividend_per_share = item.get("dividend_per_share")
            payout_ratio_pct = item.get("payout_ratio_pct")
        if dividend_per_share is not None or payout_ratio_pct is not None:
            return False
    return True


def _trend_history_is_sparse(history: Iterable[Any] | None) -> bool:
    if not history:
        return True
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
    for item in history:
        if isinstance(item, dict):
            if any(item.get(key) is not None for key in numeric_keys):
                return False
            continue
        if any(getattr(item, key, None) is not None for key in numeric_keys):
            return False
    return True
