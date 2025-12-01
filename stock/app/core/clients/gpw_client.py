import asyncio
from io import StringIO
from typing import Any, Dict, List
from urllib.parse import urljoin
import httpx
import pandas as pd
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)


class GpwListingsClient:
    """
    Client for fetching and normalizing instrument listings from GPW and NewConnect.

    This client:
    - Fetches HTML tables from configured GPW / NewConnect endpoints.
    - Normalizes column names into a unified schema.
    - Exposes high-level helpers to get records and symbol maps.
    """
    
    GPW_BASE_URL: str = settings.GPW_BASE_URL
    GPW_PATH: str = settings.GPW_PATH

    NC_BASE_URL: str = settings.NC_BASE_URL
    NC_PATH: str = (
        "ajaxindex.php?action=NCExternalDataFrontController"
        "&start=showTable&type=ALL&system_type=&tab=all&lang=EN&full=1&format=html&download_xls=1"
    )
    
    def __init__(self) -> None:
        """
        Initialize the HTTP client for GPW listings.

        Creates an `httpx.AsyncClient` with a default timeout and
        redirect-following behavior.
        """
        logger.info("Initializing GpwListingsClient")
        self._client = httpx.AsyncClient(timeout=30.0, follow_redirects=True)
        logger.debug("httpx.AsyncClient created for GpwListingsClient")

    async def aclose(self) -> None:
        """
        Close the underlying HTTP client.

        Should be called when the client is no longer needed, to properly
        release network resources.
        """
        logger.info("Closing GpwListingsClient httpx.AsyncClient")
        await self._client.aclose()
        logger.debug("GpwListingsClient httpx.AsyncClient closed")
        
    def _subset_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Select and clean a subset of relevant columns from a GPW/NC DataFrame.

        The function:
        - Keeps only a known set of columns (if present).
        - Strips whitespace from string/object columns.

        Args:
            df: Raw DataFrame parsed from GPW/NC HTML tables.

        Returns:
            A cleaned DataFrame containing only relevant columns.
        """

        wanted = [
            "Name",
            "Shortcut",
            "ISIN",
            "Last / Closing",
            "% change",
            "Cumulated volume",
            "Last transaction time",
        ]
        cols = [c for c in wanted if c in df.columns]
        subset = df[cols].copy()

        for c in cols:
            if subset[c].dtype == object:
                subset[c] = subset[c].astype(str).str.strip()
            
        logger.debug(
            f"_subset_columns: resulting shape={subset.shape}, columns={list(subset.columns)!r}"
        )

        return subset
          
    async def get_gpw_records(self) -> List[Dict[str, Any]]:
        """
        Fetch the list of instruments from GPW as a list of dictionaries.

        Returns:
            A list of records, each record representing a single instrument row.
        """
        logger.info("Fetching GPW records")
        
        df = await self._fetch_and_normalize_table(
            base_url=self.GPW_BASE_URL,
            path=self.GPW_PATH,
        )
        subset = self._subset_columns(df)
        return subset.to_dict(orient="records")
    
    async def get_newconnect_records(self) -> List[Dict[str, Any]]:
        """
        Fetch the list of instruments from NewConnect as a list of dictionaries.

        Returns:
            A list of records, each record representing a single instrument row.
        """
        logger.info("Fetching NewConnect records")

        df = await self._fetch_and_normalize_table(
            base_url=self.NC_BASE_URL,
            path=self.NC_PATH,
        )
        subset = self._subset_columns(df)
        return subset.to_dict(orient="records")
    
    async def get_all_records(self) -> List[Dict[str, Any]]:
        """
        Fetch and combine instrument records from both GPW and NewConnect.

        Returns:
            A combined list of instrument records from GPW and NC.
        """
        logger.info("Fetching all records from GPW and NewConnect (concurrently)")
        
        gpw, nc = await asyncio.gather(
            self.get_gpw_records(),
            self.get_newconnect_records(),
        )
        return gpw + nc

    async def get_symbol_map(self, mic=None) -> Dict[str, Dict[str, Any]]:
        """
        Build a mapping: symbol (Shortcut) -> full record.

        Args:
            mic: Market MIC filter:
                - None      -> use both GPW and NC
                - "XWAR"    -> only GPW
                - "XNCO"    -> only NewConnect
                - other     -> currently treated like None (GPW + NC).

        Returns:
            Dictionary mapping `Shortcut` symbol -> record dict.
        """
        logger.info(f"Building symbol map for mic={mic!r}")
        
        if mic is None:
            records = await self.get_all_records()
        elif mic == "XWAR":
            records = await self.get_gpw_records()
        elif mic == "XNCO":
            records = await self.get_newconnect_records()
        else:
            records = await self.get_all_records()
            
        return {
            r["Shortcut"]: r
            for r in records
            if r.get("Shortcut")
        }
    
    async def _fetch_and_normalize_table(self, base_url: str, path: str) -> pd.DataFrame:
        """
        Fetch an HTML table from a GPW/NC endpoint and normalize its columns.

        Steps:
        - GET the page via httpx.
        - Parse tables using `pandas.read_html`.
        - Pick the first table.
        - Flatten MultiIndex columns, if present.
        - Rename various vendor-specific headers into a unified schema.

        Args:
            base_url: Base URL of the endpoint.
            path: Path / query part appended to the base URL.

        Returns:
            A normalized `pandas.DataFrame` with consistent column names.

        Raises:
            httpx.HTTPStatusError: If the HTTP response status is not 2xx.
            RuntimeError: If no tables are found in the HTML response.
        """

        url = urljoin(base_url, path)
        logger.info(f"Fetching table from URL={url!r}")
        
        resp = await self._client.get(url)
        resp.raise_for_status()

        tables = pd.read_html(StringIO(resp.text))
        if not tables:
            raise RuntimeError(f"No tables found in response from {url}")

        df = tables[0]

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(-1)

        for col in list(df.columns):
            if str(col).startswith("Unnamed:"):
                df = df.rename(columns={col: "idx"})
                
        if "Abbreviation" in df.columns and "Shortcut" not in df.columns:
            df = df.rename(columns={"Abbreviation": "Shortcut"})
            
        if "Time of last trans." in df.columns and "Last transaction time" not in df.columns:
            df = df.rename(columns={"Time of last trans.": "Last transaction time"})
            
        if "Last trans. price" in df.columns and "Last / Closing" not in df.columns:
            df = df.rename(columns={"Last trans. price": "Last / Closing"})
            
        if "Change v. ref. price" in df.columns and "% change" not in df.columns:
            df = df.rename(columns={"Change v. ref. price": "% change"})
            
        if "Aggr. trade vol." in df.columns and "Cumulated volume" not in df.columns:
            df = df.rename(columns={"Aggr. trade vol.": "Cumulated volume"})

        return df