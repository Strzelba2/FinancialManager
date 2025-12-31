import httpx
import logging
from typing import Optional, Dict, Any, List
from nicegui import app

from schemas.quotes import QuoteRow, QuoteBySymbolItem, QuotesBySymbolsResponse

logger = logging.getLogger(__name__)


class StockClient:
    """
    Thin async client for the STOCK service.

    Uses a shared `httpx.AsyncClient` stored in `app.state.stock_httpx`
    and exposes helper methods for quotes, markets and instruments.
    """
    QUOTE_ONE_PATH = "/stock/quotes/latest"
    QUOTE_BULK_PATH = "/stock/quotes/latest/bulk"
    MARKETS_PATH = "/stock/markets"
    INSTRUMENTS_OPTIONS_PATH = "/stock/instruments/options"
    INSTRUMENT_SEARCH_PATH = "/stock/instruments/search"
    QUOTES_BY_SYMBOLS_PATH = "/stock/quotes/latest/symbols"
    
    def __init__(self) -> None:
        """
        Bind this client to a shared AsyncClient stored in `app.state.stock_httpx`.
        """
        self.client: httpx.AsyncClient = app.state.stock_httpx
        logger.info("StockClient initialized with shared httpx.AsyncClient")
        
    async def _request(
        self,
        method: str,
        url: str,
        headers: Optional[dict] = None,
        json_body: Optional[dict] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> httpx.Response | None:
        """
        Perform an HTTP request to the Wallet service.

        Args:
            method: HTTP method (e.g., "GET", "POST", "DELETE").
            url: Path or absolute URL. If path-like, the client's base_url is used.
            headers: Extra headers (merged into the request).
            json_body: JSON-serializable body to send (sets Content-Type automatically).
            params: Query parameters.

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
                params=params
            )
        except (httpx.ConnectTimeout, httpx.ReadTimeout):
            logger.warning(f"Wallet service timeout {url}")
            return None
        except httpx.HTTPError:
            logger.error(f"Wallet service HTTP error {url}")
            return None
        except Exception:
            logger.exception(f"Wallet service unexpected error {url}")
            return None

        return resp
    
    def row_from_symbol_and_payload(self, symbol: str, payload: Any) -> Optional["QuoteRow"]:
        """
        Convert a symbol and raw payload into a `QuoteRow`.

        Uses `QuoteRow.from_redis` to keep parsing identical to the Redis path.

        Args:
            symbol: Instrument symbol.
            payload: Raw data (dict-like) returned from the STOCK service.

        Returns:
            A `QuoteRow` instance if parsing succeeds, otherwise None.
        """
        logger.debug(
            f"row_from_symbol_and_payload: symbol={symbol!r}, "
            f"payload_type={type(payload)}"
        )
        try:
            return QuoteRow.from_redis(symbol, payload)
        except Exception:
            return None

    def rows_from_bulk_dict(self, data: Dict[str, Any]) -> List["QuoteRow"]:
        """
        Convert a bulk quotes dictionary into a list of `QuoteRow` objects.

        Args:
            data: Mapping of {symbol: payload} as returned from bulk API.

        Returns:
            List of successfully parsed `QuoteRow` objects.
        """
        logger.info(
            f"rows_from_bulk_dict: received {len(data)} entries to convert to QuoteRow"
        )
        out: List[QuoteRow] = []
        for sym, payload in data.items():
            row = self.row_from_symbol_and_payload(sym, payload)
            if row is not None:
                out.append(row)
        logger.info(
            f"rows_from_bulk_dict: successfully converted {len(out)} entries to QuoteRow"
        )
        return out
    
    async def get_quote(self, mic: str, symbol: str) -> List["QuoteRow"]:
        """
        Get the latest quote for a single symbol.

        Args:
            mic: Market MIC (e.g. "XWAR").
            symbol: Instrument symbol.

        Returns:
            - A list with a single `QuoteRow` if found and parsed.
            - An empty list if 200 but payload cannot be parsed.
            - None on 404, timeout, or other errors.
        """
        logger.info(f"get_quote: mic={mic!r}, symbol={symbol!r}")
        
        resp = await self._request("GET", self.QUOTE_ONE_PATH, params={"mic": mic, "symbol": symbol})
        if resp is None:
            logger.warning(f"get_quote({mic!r}, {symbol!r}): no response from service")
            return None
        if resp.status_code == 200:
            try:
                data = resp.json()
                row = self.row_from_symbol_and_payload(symbol, data)
                return [row] if row is not None else []
            except Exception:
                logger.exception(f"Failed to decode JSON for get_quote({mic}, {symbol})")
                return None
        if resp.status_code == 404:
            logger.info(f"get_quote({mic!r}, {symbol!r}): received 404 Not Found")
            return None
        logger.error(f"get_quote({mic}, {symbol}) unexpected status {resp.status_code}: {resp.text}")
        return None

    async def get_all_quotes(self, mic: str) -> List["QuoteRow"]:
        """
        Get the latest quotes for all symbols in a MIC.

        Args:
            mic: Market MIC (e.g. "XWAR").

        Returns:
            - List of `QuoteRow` objects on success.
            - Empty list on 404, timeout, or any error.
        """
        logger.info(f"get_all_quotes: mic={mic!r}")
        
        resp = await self._request("GET", self.QUOTE_BULK_PATH, params={"mic": mic})
        if resp is None:
            logger.warning(f"get_all_quotes({mic!r}): no response from service")
            return {}
        if resp.status_code == 200:
            try:
                data = resp.json()
                return self.rows_from_bulk_dict(data) if isinstance(data, dict) else {}
            except Exception:
                logger.exception(f"Failed to decode JSON for get_all_quotes({mic})")
                return {}
        if resp.status_code == 404:
            logger.info(f"get_all_quotes({mic!r}): received 404 Not Found")
            return {}
        logger.error(f"get_all_quotes({mic}) unexpected status {resp.status_code}: {resp.text}")
        return {}
    
    async def get_markets(self) -> list[dict]:
        """
        Retrieve list of available markets.

        Returns (on 200) something like:
            [
                {"mic": "XWAR", "name": "GPW (Główny Rynek)"},
                ...
            ]

        Returns:
            - List of market dicts on success.
            - Empty list on 404, timeout, or any error.
        """
        logger.info("get_markets: requesting markets list")
        
        resp = await self._request("GET", self.MARKETS_PATH)
        if resp is None:
            logger.warning("get_markets: no response from service")
            return {}
        if resp.status_code == 200:
            try:
                data = resp.json()
                return data
            except Exception:
                logger.exception("Failed to decode JSON for get_markets(%s)")
                return {}
        if resp.status_code == 404:
            logger.info("get_markets: received 404 Not Found")
            return {}
        
        logger.error(f"get_markets() unexpected status {resp.status_code}: {resp.text}")
        return {}
    
    async def list_instruments(self, mic: str) -> list[dict]:
        """
        Get a lightweight list of instruments for a given MIC.

        Args:
            mic: Market MIC (e.g. "XWAR").

        Returns (on 200):
            [
                {"symbol": "PKN", "shortname": "ORLEN SA"},
                {"symbol": "PKO", "shortname": "PKO BP SA"},
                ...
            ]

        Returns:
            - List of instrument dicts on success.
            - Empty list on 404, timeout, or any error.
        """
        logger.info(f"list_instruments: mic={mic!r}")
        
        resp = await self._request(
            "GET",
            self.INSTRUMENTS_OPTIONS_PATH,
            params={"mic": mic},
        )
        if resp is None:
            logger.warning(f"list_instruments({mic!r}): no response from service")
            return []
        if resp.status_code == 200:
            try:
                data = resp.json()
                return data if isinstance(data, list) else []
            except Exception:
                logger.exception(f"Failed to decode JSON for list_instruments({mic})")
                return []
        if resp.status_code == 404:
            logger.info(f"list_instruments({mic!r}): received 404 Not Found")
            return []
        logger.error(f"list_instruments({mic}) unexpected status {resp.status_code}: {resp.text}")
        return []
    
    async def search_instrument_by_shortname(
        self,
        shortname: str,
        limit: int = 10,
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Search instruments by shortname fragment.

        Args:
            shortname: Shortname or its fragment.
            limit: Maximum number of results to return.

        Returns:
            - List of instrument dicts on success.
            - None on failure / no response / non-200 status.
        """
        logger.info(
            f"search_instrument_by_shortname: shortname={shortname!r}, limit={limit}"
        )

        params = {"q": shortname, "limit": limit}
        resp = await self._request("GET", self.INSTRUMENT_SEARCH_PATH, params=params)

        if not resp:
            logger.error(f"search_instrument_by_shortname('{shortname}') -> no response")
            return None

        if resp.status_code != 200:
            logger.error(
                f"search_instrument_by_shortname('{shortname}') failed: "
                f"HTTP {resp.status_code} {resp.text}"
            )
            return None

        try:
            data = resp.json()
            logger.info(data)
        except Exception as e: 
            logger.exception(
                f"Failed to decode JSON for search_instrument_by_shortname('{shortname}'): {e}"
            )
            return None

        logger.info(
            f"search_instrument_by_shortname('{shortname}') -> {len(data)} results"
        )
        return data
    
    async def get_latest_quotes_for_symbols(
        self,
        symbols: List[str],
    ) -> Dict[str, QuoteBySymbolItem]:
        """
        Fetch the latest quotes for the given symbols from the stock service.

        Sends a POST request to the stock service endpoint and returns a dictionary
        keyed by symbol.

        Args:
            symbols: List of instrument symbols to query (e.g., ["AAPL", "MSFT"]).

        Returns:
            A dictionary mapping symbol -> `QuoteBySymbolItem`.
            Returns an empty dict on request/response/parsing errors.
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
