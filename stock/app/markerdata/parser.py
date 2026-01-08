from datetime import datetime, date, timezone
from urllib.parse import urljoin, urlparse, parse_qs, urlencode, urlunparse
from typing import Literal, Optional
import csv
import logging
from zoneinfo import ZoneInfo
import html

from app.core.config import settings
from app.utils.dates import PL_MONTHS, try_parse_date
from app.utils.regex_check import TIME_RE, DATE_RE
from app.utils.text import strip_accents
from app.utils.numbers import dec2, to_int_opt
from app.schemas.quates import DailyRow
from .config import MarketConfig

logger = logging.getLogger(__name__)


def parse_time_to_utc(
    time_str: Optional[str], 
    page_dt: Optional[date] = None, 
    tz: ZoneInfo = settings.TIME_ZONE
) -> Optional[datetime]:
    """
    Parse a GPW-style time or date string into a UTC datetime.

    Supports:
    - Time-only strings (e.g. "10:45") -> combined with `page_dt` (or today in `tz`)
    - Date strings with Polish month names (e.g. "12 stycznia") -> midnight in `tz`

    If parsing fails or the string is empty, returns `None`.

    Args:
        time_str: Raw time/date string from the page (may be None or empty).
        page_dt: Reference date of the page (e.g. quote date). If None, uses today's
                 date in the given `tz`.
        tz: Local timezone to interpret the parsed time/date before converting to UTC.

    Returns:
        A timezone-aware UTC `datetime`, or `None` if parsing is not possible.
    """
    
    if not time_str:
        return None
    t = str(time_str).strip()

    ref_date = page_dt or datetime.now(tz).date()

    m = TIME_RE.match(t)
    if m:
        hh, mm = int(m.group(1)), int(m.group(2))
        local_dt = datetime(ref_date.year, ref_date.month, ref_date.day, hh, mm, tzinfo=tz)
        return local_dt.astimezone(timezone.utc)

    m = DATE_RE.match(t)
    if m:
        day = int(m.group(1))
        mon_token = strip_accents(m.group(2).lower().rstrip("."))
        if mon_token not in PL_MONTHS:
            for k in sorted(PL_MONTHS.keys(), key=len, reverse=True):
                if mon_token.startswith(k):
                    mon_token = k
                    break

        month = PL_MONTHS.get(mon_token)
        if not month:
            return None

        year = ref_date.year

        if month >= 11 and ref_date.month <= 2:
            year -= 1
        else:
            try:
                parsed_candidate = date(year, month, day)
                if (parsed_candidate - ref_date).days > 40:
                    year -= 1
            except ValueError:
                return None
        try:
            local_dt = datetime(year, month, day, 0, 0, tzinfo=tz)
        except ValueError:
            return None
        return local_dt.astimezone(timezone.utc)
    return None


def historical_url(quote_href: str, cfg: MarketConfig, interval: Literal['d', 'w', 'm'] = 'd') -> str:
    """
    Build a normalized historical data URL from a quote href and market config.

    The function:
    - Unescapes HTML entities in `quote_href`.
    - Resolves relative paths against `cfg.base_url`.
    - Extracts the `s` symbol parameter from the query string.
    - Produces a canonical historical URL of the form:
        <base>/q/d/l/?s=<symbol>&i=<interval>

    Args:
        quote_href: The raw href from the quote page (may be relative or absolute).
        cfg: Market configuration containing at least `base_url`.
        interval: Historical interval:
            - 'd' -> daily
            - 'w' -> weekly
            - 'm' -> monthly

    Returns:
        A fully qualified historical data URL as string.

    Raises:
        ValueError: If `quote_href` is empty or does not contain a symbol parameter.
    """
    logger.info(
        f"historical_url: building URL from quote_href={quote_href!r}, "
        f"base_url={cfg.base_url}, interval={interval!r}"
    )
    
    href = html.unescape((quote_href or "").strip())
    base = str(cfg.base_url).rstrip("/")
    if not href:
        raise ValueError("quote_href is empty")

    abs_url = href if href.startswith(("http://", "https://")) else urljoin(base + "/", href)

    parsed = urlparse(abs_url)
    qs = parse_qs(parsed.query)
    symbol_list = qs.get("s") or qs.get("S") or []
    if not symbol_list or not symbol_list[0].strip():
        raise ValueError(f"Could not find 's' param in quote href: {quote_href!r}")
    symbol = symbol_list[0].strip()

    hist_path = "/q/d/l/" 
    hist_qs = urlencode({"s": symbol, "i": interval})

    base_parts = urlparse(base) 
    final = urlunparse((
        base_parts.scheme,
        base_parts.netloc,
        hist_path,
        "", 
        hist_qs,
        ""   
    ))
    return final


def parse_daily_csv(text: str) -> list[DailyRow]:
    """
    Parse daily candle CSV text into sorted `DailyRow` objects.

    The function:
    - Reads CSV lines
    - Skips malformed rows and rows with an invalid date
    - Converts numeric columns using `dec2` and `to_int_opt`
    - Sorts output by `date_quote` ascending

    Args:
        text: Raw CSV content as a string.

    Returns:
        A list of `DailyRow` objects sorted by `date_quote` ascending.

    Raises:
        Exception: Propagates unexpected parsing/conversion errors after logging.
    """
    out: list[DailyRow] = []
    reader = csv.reader(text.splitlines())

    for row in reader:
        if not row or len(row) < 5:
            continue

        d = try_parse_date(row[0])
        if d is None:
            continue

        out.append(
            DailyRow(
                date_quote=d,
                open=dec2(row[1]),
                high=dec2(row[2]),
                low=dec2(row[3]),
                close=dec2(row[4]),
                volume=to_int_opt(row[5]) if len(row) >= 6 else None,
            )
        )

    out.sort(key=lambda x: x.date_quote)
    return out