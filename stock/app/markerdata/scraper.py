from datetime import datetime
from playwright.async_api import Page
from typing import Optional, List, AsyncIterator
from contextlib import suppress
import asyncio
import logging

from .config import MarketConfig
from .schemas import IndexRow
from .parser import parse_time_to_utc
from .consent import dismiss_cookies_if_present
from app.utils.regex_check import NEXT_RE
from app.utils.text import txt
from app.utils.numbers import parse_float_pl, parse_int_pl

logger = logging.getLogger(__name__)


async def find_next_href(page: Page, cfg: MarketConfig) -> Optional[str]:
    """
    Find the href of the "next" page, if any.

    The function tries, in order:
    1. An `<a rel="next">` element.
    2. Any `<a>` element whose text matches `NEXT_RE`.
    3. A `<font>` element with matching text as a stop condition.

    All relative URLs are resolved against `cfg.base_url`.

    Args:
        page: Playwright `Page` instance.
        cfg: Market configuration containing `base_url`.

    Returns:
        The absolute URL of the next page, or None if not found.
    """
    a = page.locator('a[rel="next"]').first
    base = str(cfg.base_url).rstrip("/")
    logger.info(f"find_next_href: searching for next href on base={base!r}")
    
    if await a.count():
        href = await a.get_attribute("href")
        logger.debug(f"find_next_href: rel=next href={href!r}")
        if href:
            return href if href.startswith("http") else base + (href if href.startswith("/") else f"/{href}")

    rx = NEXT_RE
    a2 = page.locator("a").filter(has_text=rx).first
    if await a2.count():
        href = await a2.get_attribute("href")
        logger.debug(f"find_next_href: text-matched <a> href={href!r}")
        if href:
            return href if href.startswith("http") else base + (href if href.startswith("/") else f"/{href}")

    font_next = page.locator("font").filter(has_text=rx).first
    if await font_next.count():
        logger.info("find_next_href: <font> with 'next' text found -> assuming no next page")
        return None

    return None


async def rows_from_page(page: Page, cfg: MarketConfig) -> List[IndexRow]:
    """
    Parse all instrument rows from the current WSE/GPW page.

    The function:
    - Waits for DOM to load and for table rows with id starting 'r_'.
    - Extracts symbol, name, last price, change %, volume, and last trade time.
    - Converts each valid row to an `IndexRow`.

    Args:
        page: Playwright `Page` instance currently showing the listing.
        cfg: Market configuration, used for timezone and provider URL.

    Returns:
        A list of `IndexRow` objects parsed from the page.
    """
    logger.info("rows_from_page: waiting for page content")
    
    await page.wait_for_load_state("domcontentloaded")
    await page.wait_for_selector('tr[id^="r_"]', timeout=30000)

    rows = page.locator('tr[id^="r_"]')
    count = await rows.count()
    today_pl = datetime.now(cfg.time_zone).date()
    logger.info(f"rows_from_page: found {count} candidate rows, today_pl={today_pl}")

    out: List[IndexRow] = []
    L = cfg.layout

    for i in range(count):
        tr = rows.nth(i)
        tds = tr.locator("td")
        td_n = await tds.count()
        if td_n < L.min_cols:
            logger.info(f"rows_from_page: skipping row index={i}, td_count={td_n}")
            continue 
        
        sym_a = tds.nth(L.symbol_col).locator("a")
        has_a = await sym_a.count() > 0
        
        tstr = txt(await tds.nth(L.time_col).inner_text())
        ts_utc = parse_time_to_utc(tstr, page_dt=today_pl, tz=cfg.time_zone)
        if not ts_utc:
            logger.info(
                f"rows_from_page: skipping row index={i}, invalid time string={tstr!r}"
            )
            continue

        symbol = txt(await (sym_a.inner_text() if has_a else tds.nth(L.symbol_col).inner_text()))
        href = txt(await (sym_a.get_attribute("href") if has_a else None))
        name = txt(await tds.nth(L.name_col).inner_text())
        price = parse_float_pl(await tds.nth(L.price_col).inner_text())
        chg_pct = parse_float_pl(await tds.nth(L.change_pct_col).inner_text()) 
        volume = None
        if L.volume_col is not None and td_n > L.volume_col:
            volume = parse_int_pl(await tds.nth(L.volume_col).inner_text())
        if symbol:
            out.append(
                IndexRow(
                    symbol=symbol,
                    name=name,
                    last_price=price,
                    change_pct=chg_pct,
                    volume=volume,
                    last_trade_at=ts_utc,
                    href=href,         
                    provider=str(cfg.base_url),
                )
            )
    logger.info(f"rows_from_page: parsed {len(out)} valid rows")
    return out


async def iter_wse_rows(page: Page, cfg: MarketConfig) -> AsyncIterator[IndexRow]:
    """
    Iterate over all WSE rows across paginated listing pages.

    The function:
    - Navigates starting from `cfg.start_path`.
    - For each page:
        * Loads the page and waits for basic network idle.
        * On first page, tries to dismiss cookie banners.
        * Ensures helper link (`td a[href="pomoc/"]`) is visible (sanity check).
        * Collects rows via `rows_from_page`.
        * Yields each `IndexRow`.
    - Follows "next" links using `find_next_href`.
    - Stops when no further "next" link is found.

    Args:
        page: Playwright `Page` instance to use for navigation and parsing.
        cfg: Market configuration containing `start_path` and `time_zone`.

    Yields:
        `IndexRow` objects representing instruments/quotes from each page.
    """

    url = cfg.start_path
    page_no = 0
    
    logger.info(f"iter_wse_rows: starting iteration from url={url!r}")

    while url:
        page_no += 1
        logger.info(f"iter_wse_rows: loading page_no={page_no}, url={url!r}")
        resp = await page.goto(url, wait_until="domcontentloaded")
        if resp and not resp.ok:
            raise RuntimeError(f"HTTP {resp.status} at {url}")

        try:
            await page.wait_for_load_state("networkidle", timeout=3000)
        except Exception as e:
            logger.debug(
                f"iter_wse_rows: networkidle wait failed/timeout on page_no={page_no}: {e}"
            )
        
        if page_no == 1:
            logger.info("iter_wse_rows: first page -> attempting to dismiss cookies")
            with suppress(Exception):
                await dismiss_cookies_if_present(page, prefer_reject=True, overall_timeout_ms=4000)
        
        await page.wait_for_selector('td a[href="pomoc/"]', state="visible", timeout=30000)

        rows = await rows_from_page(page, cfg)
        if not rows:
            logger.warning(f"iter_wse_rows: no rows parsed on page {page_no}.")
            
        for pair in rows:
            yield pair

        next_url = await find_next_href(page, cfg)
        if not next_url:
            logger.info("iter_wse_rows: no next page link found; stopping.")
            break
        
        url = next_url
        logger.info(f"url: {url}")

        await asyncio.sleep(0.10)
