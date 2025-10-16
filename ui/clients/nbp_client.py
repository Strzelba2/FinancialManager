from __future__ import annotations
import httpx
import time
from typing import Iterable, Mapping
from utils.money import invert_rate, dec, quantize
import logging

logger = logging.getLogger(__name__)


class NBPClient:
    """
    Async client for the National Bank of Poland (NBP) public API.

    Caches the latest exchange-table response for a short TTL to limit network calls.
    """
    BASE_URL = "https://api.nbp.pl/api"

    def __init__(self, *, timeout: float = 5.0):
        """
        Initialize the NBP client.

        Args:
            timeout: Per-request timeout passed to the underlying httpx.AsyncClient.
        """
        self._client = httpx.AsyncClient(timeout=timeout, headers={"Accept": "application/json"})
        self._cache: dict[str, tuple[float, dict]] = {}
        self._ttl = 60 
        logger.debug("NBPClient initialized")

    async def aclose(self) -> None:
        """
        Close the underlying HTTP client.

        Call this when you are done with the instance (or use an async context manager).
        """
        logger.debug("Closing httpx.AsyncClient")
        await self._client.aclose()

    async def get_table(self, table: str = "A") -> list[dict]:
        """
        Fetch an exchange-rate table from NBP.

        Args:
            table: NBP table identifier, e.g. "A" (average/mid) or "C" (bid/ask).

        Returns:
            Parsed JSON payload as a list of dicts (NBP returns a list with one item).

        Raises:
            httpx.HTTPStatusError: if the HTTP response indicates an error.
            httpx.RequestError: for network/transport errors.
        """
        cache_key = f"table:{table}"
        now = time.time()
        if cache_key in self._cache and now - self._cache[cache_key][0] < self._ttl:
            return self._cache[cache_key][1]
        
        logger.info("Requesting NBP table '%s'", table)

        url = f"{self.BASE_URL}/exchangerates/tables/{table}?format=json"
        resp = await self._client.get(url)
        resp.raise_for_status()
        data = resp.json()
        self._cache[cache_key] = (now, data)
        return data

    async def get_rates(self, codes: Iterable[str], table: str = "A") -> Mapping[str, float]:
        """
        Get selected currency rates from a given table.

        Args:
            codes: ISO currency codes to extract (e.g., ["USD", "EUR"]).
            table: NBP table ("A" for 'mid', "C" for 'bid').

        Returns:
            Mapping of code -> rate as float. (For table "A" uses 'mid', for "C" uses 'bid'.)
        """
        data = await self.get_table(table)
        if not data:
            logger.warning("Empty payload for table '%s'", table)
            return {}
        
        rates = data[0]["rates"]
        wanted = set(codes)
        out: dict[str, float] = {}
        for it in rates:
            code = it.get("code")
            if code in wanted:
                if table.upper() == "A":
                    out[code] = float(it["mid"])
                elif table.upper() == "C":
                    out[code] = float(it["bid"])
        return out

    async def get_usd_eur_pln(self) -> dict[str, float]:
        """
        Convenience method returning common FX crosses among USD, EUR, and PLN.

        Returns:
            A dict with:
                - "USD/PLN", "EUR/PLN"
                - "PLN/USD", "PLN/EUR" (inverses, 4 d.p.)
                - "USD/EUR", "EUR/USD" (cross and its inverse, 4 d.p.)
        """
        logger.debug("Computing USD/EUR/PLN crosses from table 'A'")
        r = await self.get_rates(["USD", "EUR"], table="A")
        
        usd_pln = dec(r.get("USD"))
        eur_pln = dec(r.get("EUR"))
        usd_eur = usd_pln / eur_pln
        
        return {
            "USD/PLN": usd_pln, 
            "EUR/PLN": eur_pln,
            "PLN/USD": invert_rate(usd_pln, 4),
            "PLN/EUR": invert_rate(eur_pln, 4),
            "USD/EUR": quantize(usd_eur, 4),
            "EUR/USD": invert_rate(usd_eur, 4)
            }