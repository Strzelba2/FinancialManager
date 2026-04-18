from __future__ import annotations

import logging
from datetime import date
from urllib.parse import parse_qs, urlparse

from playwright.async_api import async_playwright

from app.exceptions import UpstreamDownloadError
from app.markerdata.consent import dismiss_cookies_if_present
from app.utils.utils import build_st_url as build_historical_csv_url

logger = logging.getLogger(__name__)

SEARCH_SELECTORS = [
    'input[name="s"]',
    'input[placeholder*="Symbol"]',
    'input[aria-label*="Symbol"]',
    'form input[type="text"]',
]

BLOCK_MARKERS = [
    "Przekroczony dzienny limit wywołań strony",
    "Dane zostały ukryte",
    "Odblokuj dostęp",
    "Przepisz powyższy kod",
    "captcha",
    "Uzyskaj apikey",
]


def _normalize_source(source: str) -> str:
    src = (source or "").strip()
    if src.startswith("//"):
        return "https:" + src
    if "://" not in src:
        return "https://" + src.lstrip("/")
    return src


def requires_browser_fetch(historical_source: str) -> bool:
    parsed = urlparse(_normalize_source(historical_source))
    path = (parsed.path or "").rstrip("/").lower()
    qs = parse_qs(parsed.query)
    symbol = ((qs.get("s") or qs.get("S") or [""])[0]).strip()
    return bool(symbol) and path == "/q/d/l"


def extract_symbol(historical_source: str) -> str:
    parsed = urlparse(_normalize_source(historical_source))
    qs = parse_qs(parsed.query)
    symbol = ((qs.get("s") or qs.get("S") or [""])[0]).strip()
    if not symbol:
        raise ValueError(f"Could not determine symbol from {historical_source!r}")
    return symbol


def _origin(historical_source: str) -> str:
    parsed = urlparse(_normalize_source(historical_source))
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"Could not determine source origin from {historical_source!r}")
    return f"{parsed.scheme}://{parsed.netloc}"


def build_quote_page_url(historical_source: str) -> str:
    return f"{_origin(historical_source)}/q/?s={extract_symbol(historical_source)}"


def build_history_page_url(historical_source: str) -> str:
    return f"{_origin(historical_source)}/q/d/?s={extract_symbol(historical_source)}"


def _has_block_marker(text: str) -> bool:
    lower = (text or "").lower()
    return any(marker.lower() in lower for marker in BLOCK_MARKERS)


def _snippet(text: str, limit: int = 240) -> str:
    compact = " ".join(part.strip() for part in (text or "").splitlines() if part.strip())
    return compact[:limit]


async def _warm_up_session(page, base_url: str, symbol: str) -> None:
    await page.goto(f"{base_url}/", wait_until="domcontentloaded")
    await page.wait_for_timeout(1200)
    await dismiss_cookies_if_present(page)
    await page.wait_for_timeout(1200)

    for selector in SEARCH_SELECTORS:
        locator = page.locator(selector).first
        if not await locator.count():
            continue

        try:
            await locator.click()
            await locator.fill(symbol)
            await locator.press("Enter")
            await page.wait_for_timeout(1800)
            if "/q/?s=" in page.url.lower():
                logger.info("browser_csv_fetch: warm-up search landed on %s", page.url)
                return
        except Exception:
            logger.debug(
                "browser_csv_fetch: search selector failed selector=%s",
                selector,
                exc_info=True,
            )


async def fetch_csv_via_browser(
    historical_source: str,
    start: date | None,
    end: date | None,
    timeout_ms: int = 30000,
) -> str:
    if not requires_browser_fetch(historical_source):
        raise ValueError(f"Browser fetch is not supported for source {historical_source!r}")

    symbol = extract_symbol(historical_source)
    base_url = _origin(historical_source)
    quote_url = build_quote_page_url(historical_source)
    history_url = build_history_page_url(historical_source)
    csv_url = build_historical_csv_url(historical_source, start=start, end=end, interval="d")

    logger.info(
        "browser_csv_fetch: symbol=%s quote_url=%s history_url=%s csv_url=%s",
        symbol,
        quote_url,
        history_url,
        csv_url,
    )

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-setuid-sandbox",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        context = await browser.new_context(
            locale="pl-PL",
            timezone_id="Europe/Warsaw",
            viewport={"width": 1440, "height": 1024},
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
            ),
            extra_http_headers={
                "Accept-Language": "pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7",
                "DNT": "1",
            },
        )
        await context.add_init_script(
            """
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'languages', {get: () => ['pl-PL', 'pl', 'en-US', 'en']});
            Object.defineProperty(navigator, 'platform', {get: () => 'Linux x86_64'});
            """
        )
        page = await context.new_page()
        page.set_default_timeout(timeout_ms)
        page.set_default_navigation_timeout(timeout_ms)

        try:
            await _warm_up_session(page, base_url, symbol)

            await page.goto(quote_url, wait_until="domcontentloaded")
            await page.wait_for_timeout(1200)
            await dismiss_cookies_if_present(page)
            await page.wait_for_timeout(1200)

            await page.goto(history_url, wait_until="domcontentloaded")
            await page.wait_for_timeout(1400)
            history_body = await page.locator("body").inner_text()
            if _has_block_marker(history_body):
                raise UpstreamDownloadError(
                    f"Historical data page blocked for {symbol}: {_snippet(history_body)}"
                )

            resp = await context.request.get(
                csv_url,
                headers={
                    "Referer": history_url,
                    "Accept": "text/csv,text/plain,*/*",
                },
            )
            text = await resp.text()
            content_disposition = (resp.headers.get("content-disposition") or "").lower()

            if resp.status >= 400:
                raise UpstreamDownloadError(
                    f"Browser CSV request failed: HTTP {resp.status} for {csv_url}"
                )

            if "blad.txt" in content_disposition or _has_block_marker(text):
                raise UpstreamDownloadError(
                    f"Browser CSV request blocked for {symbol}: {_snippet(text)}"
                )

            return text

        finally:
            await page.close()
            await context.close()
            await browser.close()
