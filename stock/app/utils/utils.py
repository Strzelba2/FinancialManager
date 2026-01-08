from typing import Optional
from datetime import date
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
import httpx
import logging

logger = logging.getLogger(__name__)


def build_st_url(
    historical_source: str,
    start: Optional[date],
    end: Optional[date],
    interval: str = "d",
) -> str:
    """
    Build a compatible URL with updated query parameters.

    Normalizes `historical_source` into a full URL, then sets/overrides:
    - `i`  : interval (e.g. "d")
    - `d1` : start date in YYYYMMDD (optional)
    - `d2` : end date in YYYYMMDD (optional)

    Args:
        historical_source: Base URL or URL-like string stored on the instrument.
        start: Optional start date (inclusive), used to set `d1`.
        end: Optional end date (inclusive), used to set `d2`.
        interval: Candle interval ("d" for daily by default).

    Returns:
        A normalized URL string with updated query parameters.

    Raises:
        Exception: Propagates unexpected URL parsing/encoding errors after logging.
    """
    src = historical_source.strip()

    if src.startswith("//"):
        src = "https:" + src
    elif "://" not in src:
        src = "https://" + src.lstrip("/")

    u = urlparse(src)
    q = parse_qs(u.query)

    q["i"] = [interval]

    if start is not None:
        q["d1"] = [start.strftime("%Y%m%d")]
    else:
        q.pop("d1", None)

    if end is not None:
        q["d2"] = [end.strftime("%Y%m%d")]
    else:
        q.pop("d2", None)

    new_query = urlencode({k: v[-1] for k, v in q.items()}, doseq=False)
    return urlunparse((u.scheme, u.netloc, u.path, u.params, new_query, u.fragment))


async def download_text_csv(url: str, timeout_s: float = 30.0) -> str:
    """
    Download CSV (or text) content from a URL and return it as a string.

    Args:
        url: The URL to fetch.
        timeout_s: Request timeout in seconds.

    Returns:
        Response body as text.

    Raises:
        httpx.HTTPError: If the HTTP request fails (network, timeout, non-2xx after raise_for_status()).
        Exception: Propagates unexpected errors after logging.
    """
    logger.info(f"Request: download_text_csv url={url}")
    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            r = await client.get(url, headers={"Accept": "text/csv,text/plain,*/*"})
            r.raise_for_status()
            return r.text
    except httpx.HTTPError as e:
        logger.error(f"download failed: url={url} err={e}")
        raise
