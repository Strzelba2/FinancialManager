import logging
from typing import Any, Dict, Optional, List
from datetime import date

import httpx
from app.schamas.response import (
    QuotesBySymbolsResponse, QuoteBySymbolItem, SyncDailyResponse, SyncDailyRequest
)
from app.core.config import settings

logger = logging.getLogger(__name__)


class StockClient:
    """
    Thin async client for the STOCK service.

    Uses a shared `httpx.AsyncClient` stored in `app.stock_httpx`
    and exposes helper methods for quotes, markets and instruments.
    """

    QUOTES_BY_SYMBOLS_PATH = "/stock/quotes/latest/symbols" 
    SYNC_DAILY_CANDLES_PATH = "/stock/instruments/{symbol}/candles/daily/sync"

    def __init__(self) -> None:
        """Bind this client to a shared AsyncClient stored in `app.state.stock_httpx`."""
        self.client = httpx.AsyncClient(
            base_url=settings.STOCK_API_URL.rstrip('/'),
            timeout=httpx.Timeout(connect=3.0, read=5.0, write=5.0, pool=5.0),
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=100),
            headers={"User-Agent": "wallet-ui/1.0"},
        )
        logger.info("StockClient initialized with shared httpx.AsyncClient")
        
    async def aclose(self) -> None:
        """
        Gracefully close the underlying HTTP client.
        Should be called on shutdown to avoid warnings.
        """
        logger.debug("Closing StockClient connection")
        await self.client.aclose()

    async def _request(
        self,
        method: str,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        json_body: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Optional[httpx.Response]:
        """
        Perform an HTTP request to the STOCK service.

        Returns:
            httpx.Response on success, or None if a timeout/HTTP error/other exception occurred.
        """
        hdrs: Dict[str, str] = {}
        if json_body is not None:
            hdrs["Content-Type"] = "application/json"
        if headers:
            hdrs.update({k: str(v) for k, v in headers.items()})

        try:
            resp = await self.client.request(
                method,
                url,
                headers=hdrs,
                json=json_body,
                params=params,
            )
            return resp
        except (httpx.ConnectTimeout, httpx.ReadTimeout):
            logger.warning(f"Stock service timeout {url}")
        except httpx.HTTPError:
            logger.error(f"Stock service HTTP error {url}")
        except Exception:
            logger.exception(f"Stock service unexpected error {url}")

        return None

    async def get_latest_quotes_for_symbols(
        self,
        symbols: List[str],
    ) -> Dict[str, QuoteBySymbolItem]:
        """
        Fetch latest quotes for given symbols (independent of market).

        Returns:
            dict: symbol -> QuoteBySymbolItem
        """
        if not symbols:
            logger.info("get_latest_quotes_for_symbols called with empty symbols")
            return {}

        payload: Dict[str, Any] = {"symbols": symbols}

        resp = await self._request(
            "POST",
            self.QUOTES_BY_SYMBOLS_PATH,
            json_body=payload,
        )
        if resp is None:
            logger.error("get_latest_quotes_for_symbols: no response from stock service")
            return {}

        if resp.status_code != 200:
            logger.error(
                f"get_latest_quotes_for_symbols: status {resp.status_code}, body={resp.text}"
            )
            return {}

        try:
            data = resp.json()
            parsed = QuotesBySymbolsResponse(quotes=data) 
        except Exception:
            logger.exception("get_latest_quotes_for_symbols: failed to parse response")
            return {}

        result: Dict[str, QuoteBySymbolItem] = {
            q.symbol: q for q in parsed.quotes
        }
        return result
    
    async def sync_daily_candles(
        self,
        symbol: str,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        include_items: bool = False,
        return_all: bool = False,
        overlap_days: int = 7,
    ) -> Optional[SyncDailyResponse]:
        """
        Trigger daily candle sync in stock-service.

        - If include_items=False: endpoint should NOT return candle list (items=None).
        - If include_items=True: returns candles depending on return_all/from/to rules.

        Returns:
            SyncDailyResponse on success, or None on errors/timeouts.
        """
        path = self.SYNC_DAILY_CANDLES_PATH.format(symbol=symbol)

        req = SyncDailyRequest(
            date_from=date_from,
            date_to=date_to,
            include_items=include_items,
            return_all=return_all,
            overlap_days=overlap_days,
    
        )
        payload: Dict[str, Any] = req.model_dump(mode="json", by_alias=True, exclude_none=True)

        resp = await self._request(
            "POST",
            path,
            json_body=payload,
        )
        if resp is None:
            logger.error(f"sync_daily_candles: no response from stock service (symbol={symbol})")
            return None

        if resp.status_code not in (200, 201):
            logger.error(
                f"sync_daily_candles: status {resp.status_code}, symbol={symbol}, body={resp.text}"
            )
            return None

        try:
            data = resp.json()
            return SyncDailyResponse.model_validate(data)
        except Exception:
            logger.exception(f"sync_daily_candles: failed to parse response (symbol={symbol})")
            return None
