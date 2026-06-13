"""Parser for the alternative (card-style, JavaScript-rendered) quote source.

This is the second supported `quote_source` provider alongside the table-based
one in ``quote_source_page.py``. Pages here render their values client-side, use
US/English number formatting (``76,738.00``) and expose values through stable
``data-ref`` hooks rather than table rows. The provider host/path is configured
via ``settings.ST_BASE_URL_ALT`` so the source is never hard-coded by name.
"""

from __future__ import annotations

from contextlib import suppress
from datetime import datetime, timezone
import logging
import re
from urllib.parse import urlsplit, urlunsplit

from playwright.async_api import Page

from app.core.config import settings
from app.markerdata.quote_source_page import QuoteSourcePage, _decimal
from app.utils.numbers import parse_float_en, parse_int_en

logger = logging.getLogger(__name__)


def _build_alt_allowed_hosts() -> frozenset[str]:
    hosts: set[str] = set()
    for url_str in [settings.ST_BASE_URL_ALT]:
        if not url_str:
            continue
        netloc = urlsplit(url_str.strip()).netloc.lower()
        if not netloc:
            continue
        bare = netloc.removeprefix("www.")
        hosts.add(bare)
        hosts.add(f"www.{bare}")
    return frozenset(hosts)


def _alt_path_prefix() -> str:
    raw = (settings.ST_BASE_URL_ALT or "").strip()
    if not raw:
        return ""
    return urlsplit(raw).path.rstrip("/").lower()


ALT_ALLOWED_HOSTS: frozenset[str] = _build_alt_allowed_hosts()
ALT_PATH_PREFIX: str = _alt_path_prefix()
ALT_PRICE_SELECTOR = 'span[data-ref="instrument-details-card__current-price"]'
ALT_CHANGE_SELECTOR = 'span[data-ref="instrument-details-card__percent-change"]'
ALT_VOLUME_SELECTOR = 'span[data-ref="instrument-details-quote__volume"]'
ALT_TIME_SELECTOR = 'span[data-ref="instrument-details-card__last-updated"]'

_ACCEPT_BUTTON_RX = re.compile(r"Accept all", re.IGNORECASE)
_DISCLAIMER_SELECTOR = 'button[data-ref="disclaimer__update-btn"]'

_PRICE_HYDRATED_JS = """(sel) => {
    const el = document.querySelector(sel);
    if (!el) return false;
    const t = (el.innerText || '').trim();
    return t.length > 0 && /[1-9]/.test(t);
}"""


def is_alt_quote_url(url: str) -> bool:
    """Return True when `url` belongs to the alternative quote source host."""
    if not url:
        return False
    return urlsplit(url.strip()).netloc.lower() in ALT_ALLOWED_HOSTS


def normalize_alt_quote_url(url: str) -> str:
    """Validate and canonicalise an alternative-source instrument URL.

    Requires an http(s) scheme, an allowed host, and a path inside the configured
    instrument section with a trailing instrument slug. Query/fragment are dropped.
    """
    raw = (url or "").strip()
    if not raw:
        raise ValueError("alt quote_source URL is empty")

    parsed = urlsplit(raw)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("alt quote_source must be a full http(s) URL")
    if parsed.netloc.lower() not in ALT_ALLOWED_HOSTS:
        raise ValueError("alt quote_source host is not in the allowed list")

    path = parsed.path.rstrip("/")
    if not [seg for seg in path.split("/") if seg]:
        raise ValueError("alt quote_source must point to an instrument page")
    if ALT_PATH_PREFIX and not path.lower().startswith(ALT_PATH_PREFIX + "/"):
        raise ValueError("alt quote_source path is not in the allowed section")

    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def _alt_symbol_from_url(url: str) -> str:
    segments = [seg for seg in urlsplit(url).path.split("/") if seg]
    if not segments:
        raise ValueError("alt quote_source has no path segment for symbol")
    return segments[-1].upper()


def _parse_alt_datetime(value: str | None) -> datetime:
    """Parse the page's (delayed) quote timestamp into a tz-aware UTC datetime.

    The page renders a local market time such as ``"15:55:00"`` (or ``"15:55"``);
    Central-European exchanges share ``settings.TIME_ZONE``'s offset, so the time
    is interpreted there and converted to UTC. Falls back to now(UTC).
    """
    if value:
        text = re.sub(r"\s+", " ", value).strip()

        m = re.match(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?$", text)
        if m:
            hh, mm, ss = int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)
            if 0 <= hh < 24 and 0 <= mm < 60 and 0 <= ss < 60:
                today = datetime.now(settings.TIME_ZONE).date()
                local_dt = datetime(
                    today.year, today.month, today.day, hh, mm, ss,
                    tzinfo=settings.TIME_ZONE,
                )
                return local_dt.astimezone(timezone.utc)

        for fmt in (
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%d/%m/%Y %H:%M:%S",
            "%d/%m/%Y %H:%M",
        ):
            try:
                local_dt = datetime.strptime(text, fmt).replace(
                    tzinfo=settings.TIME_ZONE
                )
                return local_dt.astimezone(timezone.utc)
            except ValueError:
                continue

    return datetime.now(timezone.utc)


async def _alt_text(page: Page, selector: str) -> str | None:
    """Return inner text of the first matching non-empty element."""
    el = page.locator(selector).first
    if await el.count():
        text = (await el.inner_text()).strip()
        if text and text not in {"-", ""}:
            return text
    return None


async def _dismiss_alt_consent(page: Page) -> None:
    """Click through the cookie banner and the delayed-data disclaimer if shown."""
    with suppress(Exception):
        accept = page.get_by_role("button", name=_ACCEPT_BUTTON_RX).first
        if await accept.count():
            await accept.click(timeout=4000)
            logger.info("navigate_alt_quote_source: accepted cookie consent")
    with suppress(Exception):
        disclaimer = page.locator(_DISCLAIMER_SELECTOR).first
        if await disclaimer.count():
            await disclaimer.click(timeout=3000)
            logger.info("navigate_alt_quote_source: closed data disclaimer")


async def navigate_alt_quote_source(
    url: str, page: Page, *, consent_needed: bool
) -> None:
    """Navigate to an alternative-source quote page and wait for it to hydrate.

    `consent_needed` should be True on the first visit per browser session so the
    cookie/disclaimer dialogs are dismissed once. Raises if the price never loads
    (instrument unavailable or page blocked).
    """
    response = None
    try:
        response = await page.goto(url, wait_until="domcontentloaded")
    except Exception:
        logger.debug(
            "alt quote_source navigation did not complete cleanly", exc_info=True
        )
    if response and not response.ok:
        raise RuntimeError(f"HTTP {response.status} at alt quote_source")

    with suppress(Exception):
        await page.wait_for_load_state("networkidle", timeout=3000)

    if consent_needed:
        logger.info("navigate_alt_quote_source: first page for host -> dismissing dialogs")
        await _dismiss_alt_consent(page)

    await page.wait_for_selector(ALT_PRICE_SELECTOR, state="visible", timeout=30000)
    try:
        await page.wait_for_function(
            _PRICE_HYDRATED_JS, arg=ALT_PRICE_SELECTOR, timeout=20000
        )
    except Exception as exc:
        raise RuntimeError(
            "alt quote_source price did not load (instrument unavailable or blocked)"
        ) from exc


async def parse_alt_quote_source_page(page: Page, source_url: str) -> QuoteSourcePage:
    """Parse an alternative-source quote page from a live Playwright page."""
    price_raw = await _alt_text(page, ALT_PRICE_SELECTOR)
    price = parse_float_en(price_raw)
    if price is None:
        raise ValueError("Alt quote source page does not contain last price")

    change_raw = await _alt_text(page, ALT_CHANGE_SELECTOR)
    change_pct = parse_float_en(change_raw) or 0.0

    volume_raw = await _alt_text(page, ALT_VOLUME_SELECTOR)
    volume = parse_int_en(volume_raw)

    trade_at_raw = await _alt_text(page, ALT_TIME_SELECTOR)

    return QuoteSourcePage(
        symbol=_alt_symbol_from_url(source_url),
        source_url=source_url,
        last_price=_decimal(price),
        change_pct=_decimal(change_pct),
        volume=volume,
        last_trade_at=_parse_alt_datetime(trade_at_raw),
    )
