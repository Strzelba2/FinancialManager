from datetime import datetime, timezone
from decimal import Decimal
import uuid
from .schemas import IndexRow
from .parser import historical_url
from .config import MarketConfig
from app.schemas.schemas import InstrumentCreate, QuoteLatesInput
from app.models.enums import InstrumentType, InstrumentStatus


def row_to_instrument(row: IndexRow, cfg: MarketConfig, market_id: uuid.UUID) -> InstrumentCreate:
    """
    Convert an index row into an `InstrumentCreate` payload.

    - Truncates `symbol` and `shortname` to 12 characters.
    - Builds a `historical_source` URL using `historical_url(row.href, cfg)`.
    - Sets default values such as type=STOCK and status=ACTIVE.

    Args:
        row: Parsed index row with basic instrument data (symbol, name, href, etc.).
        cfg: Market configuration used to build the historical URL.
        market_id: UUID of the market to which this instrument belongs.

    Returns:
        An `InstrumentCreate` instance ready for persistence.
    """

    return InstrumentCreate(
        isin=None,        
        market_id=market_id,
        symbol=row.symbol[:12],
        shortname=row.name[:12],
        name=None,
        type=cfg.instrument_type,      
        status=InstrumentStatus.ACTIVE,  
        historical_source=historical_url(row.href, cfg), 
        popularity=0,
        last_seen_at=datetime.now(timezone.utc),
    )
    
    
def row_to_quote_latest(row: IndexRow) -> QuoteLatesInput:
    """
    Convert an index row into a `QuoteLatesInput` payload.

    - Fills missing `last_price` and `change_pct` with Decimal('0').
    - Fills missing `last_trade_at` with the current UTC time.
    - Passes through provider and href from the row.

    Args:
        row: Parsed index row containing quote data.

    Returns:
        A `QuoteLatesInput` instance representing the latest quote.
    """

    return QuoteLatesInput(
        last_price=row.last_price or Decimal("0"),
        change_pct=row.change_pct or Decimal("0"),
        volume=row.volume,
        last_trade_at=row.last_trade_at or datetime.now(timezone.utc),
        provider=row.provider,
        href=row.href
    )