from typing import Dict, AsyncIterator, Tuple
from playwright.async_api import Page
import logging
import uuid
from .config import MarketConfig
from .scraper import iter_wse_rows
from .mapping import row_to_instrument, row_to_quote_latest
from app.schemas.schemas import InstrumentCreate, QuoteLatesInput

logger = logging.getLogger(__name__)


class MarketProvider:
    """
    Provider responsible for mapping market configuration to instrument and quote rows.

    This provider:
    - Keeps a registry of markets keyed by a string ID (e.g. "pl-wse", "pl-newconnect").
    - Exposes configuration lookup by market ID.
    - Yields `(InstrumentCreate, QuoteLatesInput)` tuples from a Playwright page.
    """
    
    provider_id = "market"
    
    def __init__(self, markets: Dict[str, MarketConfig]):
        """
        Initialize the provider with a dictionary of market configurations.

        Args:
            markets: Mapping from market_id (e.g. "pl-wse") to `MarketConfig`.
        """
        self._markets = markets
        logger.info(
            f"MarketProvider initialized with markets={list(self._markets.keys())}"
        )

    def list_markets(self) -> list[str]:
        """
        Return a list of all configured market IDs.

        Returns:
            List of market IDs (keys of the internal markets mapping).
        """
        return list(self._markets.keys())
    
    def get_config(self, market_id: str) -> MarketConfig:
        """
        Retrieve configuration for a given market ID.

        Args:
            market_id: ID of the market (e.g. "pl-wse", "pl-newconnect").

        Returns:
            The corresponding `MarketConfig`.

        Raises:
            KeyError: If the given market_id is not configured.
        """
        logger.info(f"MarketProvider.get_config: requested market_id={market_id!r}")
        try:
            cfg = self._markets[market_id]
        except KeyError:
            logger.error(
                f"MarketProvider.get_config: unknown market_id={market_id!r}", exc_info=True
            )
            raise
        logger.debug(
            f"MarketProvider.get_config: returning config for market_id={market_id!r}"
        )
        return cfg
    
    async def iter_rows_mapped(
        self, page: Page, cfg: MarketConfig, market_id: uuid.UUID
    ) -> AsyncIterator[Tuple[InstrumentCreate, QuoteLatesInput]]:
        """
        Yield mapped rows for a given market as `(InstrumentCreate, QuoteLatesInput)`.

        The flow:
        - Iterates over raw index rows from `iter_wse_rows(page, cfg)`.
        - Converts each row to:
            * `InstrumentCreate` (with the given `market_id`).
            * `QuoteLatesInput` containing the latest quote data.

        These tuples are then used by the ingestion service to:
        - Upsert `Instrument` (getting an ID).
        - Upsert `QuoteLatest` for that instrument.

        Args:
            page: Playwright `Page` instance with the market listing loaded.
            cfg: Market configuration used to interpret/parse the rows.
            market_id: UUID of the `Market` entity in the database.

        Yields:
            Tuples of `(instrument_create, quote_latest_input)` per instrument.
        """
        logger.info(
            f"MarketProvider.iter_rows_mapped: start for market_id={market_id}, "
            f"cfg={cfg}"
        )
        async for row in iter_wse_rows(page, cfg):

            latest_quote = row_to_quote_latest(row)
            instrument = row_to_instrument(row, cfg, market_id=market_id)
            
            yield (instrument, latest_quote)
