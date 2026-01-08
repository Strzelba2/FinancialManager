from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import Optional, List, Tuple, Dict
from datetime import date, datetime
from decimal import Decimal
import uuid

from app.models.models import BrokerageEvent, Instrument, BrokerageAccount, Wallet
from app.schamas.schemas import BrokerageEventCreate
from app.crud.holding_crud import apply_event_to_holding, get_or_create_holding


async def create_brokerage_event(
    session: AsyncSession, 
    data: BrokerageEventCreate, 
    instrument_id: uuid.UUID 
) -> BrokerageEvent:
    """
    Create a BrokerageEvent row.

    Adds the event to the session, flushes to get PK, refreshes, and returns it.

    Args:
        session: SQLAlchemy async session.
        data: Incoming creation payload.
        instrument_id: Resolved instrument UUID (may be looked up/created upstream).

    Returns:
        Created BrokerageEvent ORM object.

    Raises:
        ValueError: on unique constraint / FK violations (keeps your original semantics).
    """
    obj = BrokerageEvent(
        brokerage_account_id=data.brokerage_account_id,
        instrument_id=instrument_id,
        kind=data.kind,
        quantity=data.quantity,
        price=data.price,
        currency=data.currency,
        split_ratio=data.split_ratio,
        trade_at=data.trade_at,
    )
    session.add(obj)
    try:
        await session.flush()
    except IntegrityError as e:
        await session.rollback()
        raise ValueError(f"Broker event already exists for this account & instrument, or invalid FK. {e}") from e
    await session.refresh(obj)
    return obj


async def find_duplicate_brokerage_event(
    session: AsyncSession,
    data: BrokerageEventCreate,
    instrument_id: uuid.UUID,
) -> Optional[BrokerageEvent]:
    """
    Find a potential duplicate BrokerageEvent matching all identifying fields.

    Args:
        session: SQLAlchemy async session.
        data: Candidate event payload.
        instrument_id: Instrument UUID to match.

    Returns:
        Matching BrokerageEvent if found, else None.
    """
    stmt = (
        select(BrokerageEvent)
        .where(
            BrokerageEvent.brokerage_account_id == data.brokerage_account_id,
            BrokerageEvent.instrument_id == instrument_id,
            BrokerageEvent.kind == data.kind,
            BrokerageEvent.trade_at == data.trade_at,
            BrokerageEvent.quantity == data.quantity,
            BrokerageEvent.price == data.price,
            BrokerageEvent.currency == data.currency,
        )
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def list_last_brokerage_events_for_accounts(
    session: AsyncSession,
    account_ids: List[uuid.UUID],
    limit: int = 5,
) -> List[BrokerageEvent]:
    """
    List the most recent brokerage events across multiple accounts.

    Args:
        session: SQLAlchemy async session.
        account_ids: Brokerage account IDs to include.
        limit: Max number of rows to return.

    Returns:
        List of tuples: (BrokerageEvent, Instrument, BrokerageAccount) ordered by trade_at desc.
    """
    if not account_ids:
        return []

    stmt = (
        select(BrokerageEvent, Instrument, BrokerageAccount)
        .join(Instrument, BrokerageEvent.instrument_id == Instrument.id)
        .join(BrokerageAccount, BrokerageEvent.brokerage_account_id == BrokerageAccount.id)
        .where(BrokerageEvent.brokerage_account_id.in_(account_ids))
        .order_by(BrokerageEvent.trade_at.desc())
        .limit(limit)
    )

    result = await session.execute(stmt)
    return result.all()


def _apply_event_filters(
    stmt,
    brokerage_account_ids: Optional[list[uuid.UUID]] = None,
    kinds: Optional[list[str]] = None,
    currencies: Optional[list[str]] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    q: Optional[str] = None,
):
    """
    Apply optional filters to a SQLAlchemy statement for brokerage events.

    Args:
        stmt: SQLAlchemy selectable.
        brokerage_account_ids: Filter by account ids.
        kinds: Filter by event kinds (empty strings are ignored).
        currencies: Filter by currencies (empty strings are ignored).
        date_from: Inclusive lower bound (00:00:00).
        date_to: Inclusive upper bound (23:59:59.999999).
        q: Search by instrument symbol/name (ILIKE %q%).

    Returns:
        Updated statement.
    """
    if brokerage_account_ids:
        stmt = stmt.where(BrokerageEvent.brokerage_account_id.in_(brokerage_account_ids))
    if kinds:
        stmt = stmt.where(BrokerageEvent.kind.in_([k for k in kinds if k]))
    if currencies:
        stmt = stmt.where(BrokerageEvent.currency.in_([c for c in currencies if c]))
    if date_from:
        stmt = stmt.where(BrokerageEvent.trade_at >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        stmt = stmt.where(BrokerageEvent.trade_at <= datetime.combine(date_to, datetime.max.time()))
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            (Instrument.symbol.ilike(like)) | (Instrument.name.ilike(like))
        )
    return stmt


async def list_brokerage_events_page(
    session: AsyncSession,
    user_id: uuid.UUID,
    page: int,
    size: int,
    brokerage_account_ids: Optional[list[uuid.UUID]] = None,
    kinds: Optional[list[str]] = None,
    currencies: Optional[list[str]] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    q: Optional[str] = None,
) -> Tuple[
    List[Tuple["BrokerageEvent", "BrokerageAccount", "Instrument", "Wallet"]],
    int,
    int,
    int,
    Dict[str, Decimal],
]:
    """
    List brokerage events for a user with pagination + filters + per-currency sum.

    Args:
        session: SQLAlchemy async session.
        user_id: Owner user UUID.
        page: 1-based page index (clamped to >= 1).
        size: page size (clamped to 1..200).
        brokerage_account_ids: Optional account filters.
        kinds: Optional event kind filters.
        currencies: Optional currency filters.
        date_from: Optional date lower bound.
        date_to: Optional date upper bound.
        q: Optional search query (symbol/name).

    Returns:
        (rows, total, page, size, sum_by_ccy) where:
            rows: list of (BrokerageEvent, BrokerageAccount, Instrument, Wallet)
            total: total count after filters
            page/size: sanitized page/size
            sum_by_ccy: dict[str, Decimal] currency_code -> sum(quantity*price)
    """
    page = max(1, int(page))
    size = min(200, max(1, int(size)))
    offset = (page - 1) * size

    base = (
        select(BrokerageEvent, BrokerageAccount, Instrument, Wallet)
        .join(BrokerageAccount, BrokerageAccount.id == BrokerageEvent.brokerage_account_id)
        .join(Wallet, Wallet.id == BrokerageAccount.wallet_id)
        .join(Instrument, Instrument.id == BrokerageEvent.instrument_id)
        .where(Wallet.user_id == user_id)
    )
    base = _apply_event_filters(
        base,
        brokerage_account_ids=brokerage_account_ids,
        kinds=kinds,
        currencies=currencies,
        date_from=date_from,
        date_to=date_to,
        q=q,
    )

    count_stmt = select(func.count()).select_from(base.subquery())
    total = int((await session.execute(count_stmt)).scalar_one())

    rows = (
        (await session.execute(base.order_by(BrokerageEvent.trade_at.desc()).offset(offset).limit(size)))
        .all()
    )
    
    sum_stmt = (
        select(
            BrokerageEvent.currency,
            func.coalesce(func.sum(BrokerageEvent.quantity * BrokerageEvent.price), 0),
        )
        .join(BrokerageAccount, BrokerageAccount.id == BrokerageEvent.brokerage_account_id)
        .join(Wallet, Wallet.id == BrokerageAccount.wallet_id)
        .join(Instrument, Instrument.id == BrokerageEvent.instrument_id)
        .where(Wallet.user_id == user_id)
    )
    sum_stmt = _apply_event_filters(
        sum_stmt,
        brokerage_account_ids=brokerage_account_ids,
        kinds=kinds,
        currencies=currencies,
        date_from=date_from,
        date_to=date_to,
        q=q,
    )
    sum_stmt = sum_stmt.group_by(BrokerageEvent.currency)

    sum_rows = (await session.execute(sum_stmt)).all()
    sum_by_ccy: dict[str, Decimal] = {str(ccy.value): Decimal(str(val)) for ccy, val in sum_rows}

    return rows, total, page, size, sum_by_ccy


async def rebuild_holding_from_events(
    session: AsyncSession,
    account_id: uuid.UUID,
    instrument_id: uuid.UUID,
) -> None:
    """
    Rebuild a Holding row by replaying all BrokerageEvents for (account_id, instrument_id)
    in chronological order.

    If resulting quantity == 0, the holding is deleted.

    Args:
        session: SQLAlchemy async session.
        account_id: Brokerage account UUID.
        instrument_id: Instrument UUID.
    """
    res = await session.execute(
        select(BrokerageEvent)
        .where(
            BrokerageEvent.brokerage_account_id == account_id,
            BrokerageEvent.instrument_id == instrument_id,
        )
        .order_by(BrokerageEvent.trade_at.asc(), BrokerageEvent.id.asc())
    )
    events = list(res.scalars().all())

    holding = await get_or_create_holding(session, account_id=account_id, instrument_id=instrument_id)

    holding.quantity = Decimal("0")
    holding.avg_cost = Decimal("0")

    for ev in events:
        apply_event_to_holding(holding, ev)  

    if holding.quantity == 0:
        await session.delete(holding)
    else:
        session.add(holding)
        await session.flush()


async def batch_patch_brokerage_events(
    session: AsyncSession,
    user_id: uuid.UUID,
    items: list[dict],
) -> int:
    """
    Batch patch brokerage events (quantity/price/split_ratio) for a user.
    After patching, rebuild holdings for affected (account_id, instrument_id) pairs.

    Args:
        session: SQLAlchemy async session.
        user_id: Owner user UUID.
        items: List of patch dicts. Each must include "id" and optional fields.

    Returns:
        Number of events updated (count of patched events).
    """

    updated = 0
    affected_pairs: set[tuple[uuid.UUID, uuid.UUID]] = set()

    for patch in items:
        ev_id = patch.get("id")
        if not ev_id:
            continue

        ev = await session.get(BrokerageEvent, uuid.UUID(str(ev_id)))
        if ev is None:
            continue

        acc = await session.get(BrokerageAccount, ev.brokerage_account_id)
        if acc is None:
            continue
        w = await session.get(Wallet, acc.wallet_id)
        if w is None or w.user_id != user_id:
            continue

        if "quantity" in patch and patch["quantity"] is not None:
            ev.quantity = Decimal(str(patch["quantity"]))
        if "price" in patch and patch["price"] is not None:
            ev.price = Decimal(str(patch["price"]))
        if "split_ratio" in patch and patch["split_ratio"] is not None:
            ev.split_ratio = Decimal(str(patch["split_ratio"]))

        updated += 1
        affected_pairs.add((ev.brokerage_account_id, ev.instrument_id))
        
    await session.flush()

    for account_id, instrument_id in affected_pairs:
        await rebuild_holding_from_events(
            session=session,
            account_id=account_id,
            instrument_id=instrument_id,
        )

    return updated


async def delete_brokerage_event_and_rebuild_holding(
    session: AsyncSession,
    user_id: uuid.UUID,
    event_id: uuid.UUID,
) -> bool:
    """
    Delete a brokerage event (if owned by the user) and rebuild the affected holding.

    Args:
        session: SQLAlchemy async session.
        user_id: Owner user UUID.
        event_id: Event UUID to delete.

    Returns:
        True if deleted, False if not found or not owned by the user.
    """
    ev = await session.get(BrokerageEvent, event_id)
    if ev is None:
        return False

    acc = await session.get(BrokerageAccount, ev.brokerage_account_id)
    if acc is None:
        return False
    w = await session.get(Wallet, acc.wallet_id)
    if w is None or w.user_id != user_id:
        return False

    account_id = ev.brokerage_account_id
    instrument_id = ev.instrument_id

    await session.delete(ev)
    await session.flush()

    await rebuild_holding_from_events(
        session=session,
        account_id=account_id,
        instrument_id=instrument_id,
    )
    return True


async def count_brokerage_events_since(
    session: AsyncSession,
    brokerage_ids: list[uuid.UUID],
    since: datetime,
) -> dict[uuid.UUID, int]:
    """
    Count brokerage events per brokerage account since a given timestamp.

    Args:
        session: SQLAlchemy async database session.
        brokerage_ids: List of brokerage account UUIDs to include.
        since: Inclusive lower bound for `BrokerageEvent.trade_at`.

    Returns:
        A mapping: {brokerage_account_id: events_count}.

        - Returns an empty dict if `brokerage_ids` is empty.
        - Brokerage IDs with zero events will not appear in the output.
          (Caller can default missing ids to 0.)

    Raises:
        Exception: Propagates unexpected database errors after logging.
    """
    if not brokerage_ids:
        return {}
    stmt = (
        select(BrokerageEvent.brokerage_account_id, func.count(BrokerageEvent.id))
        .where(BrokerageEvent.brokerage_account_id.in_(brokerage_ids), BrokerageEvent.trade_at >= since)
        .group_by(BrokerageEvent.brokerage_account_id)
    )
    rows = (await session.execute(stmt)).all()
    return {uuid.UUID(str(bid)): int(cnt) for bid, cnt in rows}
