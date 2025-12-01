from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload
from sqlmodel import select
from typing import Optional, List
import logging

from app.models.models import Instrument, QuoteLatest
from app.schemas.schemas import QuoteLatesInput

logger = logging.getLogger(__name__)


async def upsert_quote_latest(session: AsyncSession, instrument_id, qin: QuoteLatesInput) -> QuoteLatest:
    """
    Insert or update the latest quote for a given instrument.

    The row in `QuoteLatest` is locked (FOR UPDATE) to avoid concurrent write issues.
    If no row exists for the given `instrument_id`, it is created; otherwise it is updated.

    Args:
        session: Async SQLAlchemy session.
        instrument_id: ID of the instrument whose latest quote is being upserted.
        qin: Input payload with the latest quote data.

    Returns:
        The up-to-date `QuoteLatest` instance.

    Raises:
        ValueError: If the upsert violates a database constraint (e.g. unique/index).
    """
    logger.debug(
        f"upsert_quote_latest: instrument_id={instrument_id}, "
        f"payload={qin.model_dump()}"
    )
    stmt = (
        select(QuoteLatest)
        .where(QuoteLatest.instrument_id == instrument_id)
        .with_for_update(of=QuoteLatest, nowait=False, skip_locked=False)
    )
    ql = (await session.execute(stmt)).scalar_one_or_none()
    if ql is None:
        ql = QuoteLatest(instrument_id=instrument_id, **qin.model_dump())
        session.add(ql)
    else:
        ql.last_price = qin.last_price
        ql.change_pct = qin.change_pct
        ql.volume = qin.volume
        ql.last_trade_at = qin.last_trade_at
        
    try:
        await session.flush()
    except IntegrityError as e:
        await session.rollback()
        raise ValueError("Upsert for QuoteLatest violated a database constraint.") from e

    await session.refresh(ql)
    return ql


async def fetch_latest_quote(session: AsyncSession, mic: str, symbol: str) -> Optional[QuoteLatest]:
    """
    Fetch the latest quote for a given MIC and symbol.

    The query joins `QuoteLatest` with `Instrument` and eagerly loads the instrument
    relationship. Only a single row (limit 1) is returned if present.

    Args:
        session: Async SQLAlchemy session.
        mic: Market MIC code (e.g. 'XWAR').
        symbol: Instrument symbol (e.g. 'PKN').

    Returns:
        The matching `QuoteLatest` instance (with `instrument` loaded), or None.
    """
    logger.debug(
        f"fetch_latest_quote: mic={mic!r}, symbol={symbol!r}"
    )

    stmt = (
        select(QuoteLatest)
        .join(Instrument, Instrument.id == QuoteLatest.instrument_id)
        .options(joinedload(QuoteLatest.instrument)) 
        .where(Instrument.mic == mic, Instrument.symbol == symbol)
        .limit(1)
    )
    res = await session.execute(stmt)
    return res.scalar_one_or_none()


async def fetch_latest_for_mic(session: AsyncSession, mic: str) -> List[QuoteLatest]:
    """
    Fetch all latest quotes for a given MIC, with instruments eagerly loaded.

    Args:
        session: Async SQLAlchemy session.
        mic: Market MIC code (e.g. 'XWAR').

    Returns:
        A list of `QuoteLatest` instances for all instruments in the given MIC.
    """
    logger.info(f"fetch_latest_for_mic: mic={mic!r}")
    
    stmt = (
        select(QuoteLatest)
        .join(Instrument, Instrument.id == QuoteLatest.instrument_id)
        .options(joinedload(QuoteLatest.instrument))
        .where(Instrument.mic == mic)
        .order_by(Instrument.symbol)
    )
    res = await session.execute(stmt)
    return list(res.scalars().all())