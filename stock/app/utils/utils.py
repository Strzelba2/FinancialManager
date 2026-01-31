import asyncio
from typing import Optional
from datetime import date
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from app.exceptions import UpstreamDownloadError
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


async def download_text_csv(url: str, timeout_s: float = 30.0, retries: int = 3) -> str:
    """
    Download CSV (or text) content from a URL and return it as a string.

    Args:
        url: Absolute URL of the resource to download.
        timeout_s: Per-request timeout in seconds (applies to the underlying httpx client).
        retries: Maximum number of attempts for transient failures. Must be >= 1 to make a request.

    Returns:
        The response body decoded as text (`httpx.Response.text`).

    Raises:
        UpstreamDownloadError:
            - If the server returns a non-success HTTP status (non-2xx).
            - If all retry attempts fail due to transient network/timeout/protocol errors.
        Exception:
            Any unexpected exception types are not handled here and will propagate to the caller.
    """
    logger.info(f"Request: download_text_csv url={url}")
    last_exc: Exception | None = None

    for attempt in range(1, retries + 1):
        try:
            async with httpx.AsyncClient(timeout=timeout_s, follow_redirects=True) as client:
                r = await client.get(url, headers={"Accept": "text/csv,text/plain,*/*"})
                r.raise_for_status()
                return r.text

        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout, httpx.RemoteProtocolError) as e:
            last_exc = e
            logger.warning(f"download_text_csv failed (attempt {attempt}/{retries}) url={url} err={e!r}")

            if attempt < retries:
                await asyncio.sleep(0.5 * (2 ** (attempt - 1)))  # 0.5s, 1s, 2s
                continue

            break

        except httpx.HTTPStatusError as e:
            logger.error(f"download_text_csv bad status url={url} status={e.response.status_code}")
            raise UpstreamDownloadError(f"CSV download failed: {e.response.status_code} for {url}") from e

    raise UpstreamDownloadError(f"CSV download failed after {retries} retries: {url}; last={last_exc!r}") from last_exc
