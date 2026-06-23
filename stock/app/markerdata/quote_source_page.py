from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
import logging
import re
from typing import Iterable
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

from playwright.async_api import Page

from app.core.config import settings
from app.utils.numbers import parse_float_pl, parse_int_pl
from app.markerdata.schemas import QuoteSourcePage

logger = logging.getLogger(__name__)


def _build_allowed_hosts() -> frozenset[str]:
    hosts: set[str] = set()
    for url_str in [settings.ST_BASE_URL]:
        if not url_str:
            continue
        netloc = urlsplit(url_str.strip()).netloc.lower()
        if not netloc:
            continue
        bare = netloc.removeprefix("www.")
        hosts.add(bare)
        hosts.add(f"www.{bare}")
    return frozenset(hosts)


ALLOWED_QUOTE_HOSTS: frozenset[str] = _build_allowed_hosts()


def normalize_quote_source_url(url: str) -> str:
    raw = (url or "").strip()
    if not raw:
        raise ValueError("quote_source URL is empty")

    parsed = urlsplit(raw)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("quote_source must be a full http(s) URL")
    if parsed.netloc.lower() not in ALLOWED_QUOTE_HOSTS:
        raise ValueError("quote_source host is not in the allowed list")
    path = parsed.path.rstrip("/").lower()
    if path != "/q" and not path.startswith("/q/"):
        raise ValueError("quote_source must point to quote page /q/")

    symbol = parse_qs(parsed.query).get("s", [""])[0].strip()
    if not symbol:
        raise ValueError("quote_source must contain symbol query parameter 's'")

    return urlunsplit((parsed.scheme, parsed.netloc, "/q/", urlencode({"s": symbol}), ""))


def quote_source_fetch_url(url: str) -> str:
    normalized = normalize_quote_source_url(url)
    parsed = urlsplit(url.strip())
    path = parsed.path or "/q/"
    normalized_path = path.rstrip("/").lower()
    if normalized_path.startswith("/q/d"):
        return normalized

    symbol = parse_qs(parsed.query).get("s", [""])[0].strip()
    return urlunsplit((parsed.scheme, parsed.netloc, path, urlencode({"s": symbol}), ""))


def validate_quote_source_url(url: str) -> str:
    return normalize_quote_source_url(url)


def _extract_symbol(url: str) -> str:
    parsed = urlsplit(url)
    symbol = parse_qs(parsed.query).get("s", [""])[0].strip()
    if not symbol:
        raise ValueError("quote_source must contain symbol query parameter 's'")
    return symbol.upper()


def _decimal(value: float | int | str | Decimal) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


def _normalize_label(value: str) -> str:
    text = re.sub(r"\s+", " ", value or "").strip().lower()
    text = text.replace("ą", "a").replace("ć", "c").replace("ę", "e")
    text = text.replace("ł", "l").replace("ń", "n").replace("ó", "o")
    text = text.replace("ś", "s").replace("ż", "z").replace("ź", "z")
    return text


def _extract_percent_value(value: str) -> str | None:
    percent_matches = re.findall(r"[-+]?\d+(?:[,.]\d+)?\s*%", value or "")
    if not percent_matches:
        return None
    return percent_matches[-1].replace(" ", "")


def _value_from_row_cells(label: str, values: list[str]) -> str | None:
    normalized_label = _normalize_label(label)
    candidates = [value for value in values if value]
    if not candidates:
        return None

    if "zmiana" in normalized_label:
        for value in candidates:
            percent_value = _extract_percent_value(value)
            if percent_value is not None and parse_float_pl(percent_value) is not None:
                return percent_value

    if "wolumen" in normalized_label or "volume" in normalized_label:
        for value in candidates:
            if parse_int_pl(value) is not None:
                return value

    if any(keyword in normalized_label for keyword in ("kurs", "last", "ostatnio", "price", "cena")):
        for value in candidates:
            if parse_float_pl(value) is not None:
                return value

    return " ".join(candidates)


def _first_value(mapping: dict[str, str], labels: Iterable[str]) -> str | None:
    normalized_labels = [_normalize_label(label) for label in labels]
    for label in normalized_labels:
        if label in mapping:
            return mapping[label]
    for key, value in mapping.items():
        if any(label in key for label in normalized_labels):
            return value
    return None


def _parse_datetime(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)

    text = re.sub(r"\s+", " ", value.strip())
    formats = (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%d.%m.%Y %H:%M:%S",
        "%d.%m.%Y %H:%M",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
    )
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue

    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            parsed_time = datetime.strptime(text, fmt).time()
            now = datetime.now(timezone.utc)
            return datetime.combine(now.date(), parsed_time, tzinfo=timezone.utc)
        except ValueError:
            continue

    return datetime.now(timezone.utc)


async def _page_table_pairs(page: Page) -> dict[str, str]:
    """Extract label→value pairs from all table rows via Playwright JS evaluation."""
    rows: list[list[str]] = await page.evaluate("""() => {
        const out = [];
        for (const tr of document.querySelectorAll('tr')) {
            const cells = [...tr.querySelectorAll('td, th')]
                .map(c => c.innerText.trim())
                .filter(Boolean);
            if (cells.length >= 2) out.push(cells);
        }
        return out;
    }""")
    pairs: dict[str, str] = {}
    for cells in (rows or []):
        value = _value_from_row_cells(cells[0], cells[1:])
        if value:
            pairs[_normalize_label(cells[0])] = value
    return pairs


async def _locate_text(page: Page, selectors: list[str]) -> str | None:
    """Return inner text of the first matching non-empty element."""
    for sel in selectors:
        el = page.locator(sel).first
        if await el.count():
            text = (await el.inner_text()).strip()
            if text and text not in {"-", ""}:
                return text
    return None


async def parse_quote_source_page(page: Page, source_url: str) -> QuoteSourcePage:
    """Parse a quote page directly from a live Playwright page (production path)."""
    source_url = validate_quote_source_url(source_url)

    pairs = await _page_table_pairs(page)
    logger.info(f"pairs extracted from page: {pairs}")

    price_raw = _first_value(pairs, ("kurs", "last", "ostatnio", "last price", "cena")) or await _locate_text(
        page, ["#c2", "#c5", '[id$="_c5"]', '[id$="_c2"]', '[id$="_c1"]', '[id$="_l"]']
    )
    price = parse_float_pl(price_raw)
    if price is None:
        raise ValueError("Quote source page does not contain last price")

    change_raw = (
        _first_value(pairs, ("zmiana %", "zmiana", "change %", "% change", "zmiana procentowa"))
        or await _locate_text(page, ['[id$="_m3"]', '[id$="_cp"]', '[id$="_c3"]'])
        or "0"
    )
    change_pct = parse_float_pl(change_raw) or 0.0

    volume_raw = _first_value(pairs, ("wolumen", "volume", "cumulated volume")) or await _locate_text(
        page, ['[id$="_v"]', '[id$="_vol"]']
    )
    volume = parse_int_pl(volume_raw)

    trade_at_raw = _first_value(
        pairs, ("ostatni handel", "last trade", "data", "czas", "date", "time")
    ) or await _locate_text(page, ['[id$="_t2"]', '[id$="_t"]', '[id$="_time"]', '[id$="_d3"]'])

    return QuoteSourcePage(
        symbol=_extract_symbol(source_url),
        source_url=source_url,
        last_price=_decimal(price),
        change_pct=_decimal(change_pct),
        volume=volume,
        last_trade_at=_parse_datetime(trade_at_raw),
    )
