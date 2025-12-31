from fastapi import APIRouter, Depends, HTTPException, Query
import uuid
from datetime import date
from typing import Optional, List
import logging
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import db
from app.schamas.response import (
    BrokerageEventWithHoldingRead, BrokerageEventsImportSummary, BrokerageEventPageOut,
    BrokerageEventRowOut, BatchUpdateBrokerageEventsRequest
    )
from app.schamas.schemas import (
    BrokerageEventCreate, HoldingRead, BrokerageEventsImportRequest, BrokerageAccountRead
    )
from app.api.services.brokerage_event import (
    create_brokerage_event_and_update_holding
    )
from app.crud.broker_event_crud import (
    list_brokerage_events_page, batch_patch_brokerage_events, delete_brokerage_event_and_rebuild_holding
    )
from app.crud.brokerage_account_crud import list_brokerage_accounts_for_user
from app.api.deps import get_internal_user_id
from app.crud.user_crud import get_user


logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/brokerage/accounts", response_model=list[BrokerageAccountRead])
async def get_brokerage_accounts_for_user(
    user_id: uuid.UUID = Depends(get_internal_user_id),
    session: AsyncSession = Depends(db.get_session),
) -> list[BrokerageAccountRead]:
    """
    Return all brokerage accounts belonging to the authenticated internal user.

    Args:
        user_id: Authenticated user id (resolved internally).
        session: SQLAlchemy async session.

    Returns:
        List of brokerage accounts (response_model).
    """
    logger.info("GET /brokerage/accounts:")
    rows = await list_brokerage_accounts_for_user(session=session, user_id=user_id)
    return rows


@router.post(
    "/brokerage/event",
    response_model=BrokerageEventWithHoldingRead,
)
async def create_brokerage_event_endpoint(
    payload: BrokerageEventCreate,
    user_id: uuid.UUID = Depends(get_internal_user_id),
    session: AsyncSession = Depends(db.get_session),
):
    """
    Create a single brokerage event and update the corresponding holding.

    Flow:
        1. Validate that `user_id` points to an existing user.
        2. In a DB transaction, create the brokerage event and update the holding.
        3. Wrap the result into `BrokerageEventWithHoldingRead` for the response.

    Args:
        payload: Data describing the brokerage event to create.
        user_id: Internal user ID obtained from the request context/dependency.
        session: Async SQLAlchemy session (dependency-injected).

    Raises:
        HTTPException(400): If the user does not exist.

    Returns:
        `BrokerageEventWithHoldingRead` with the created event and (optional) updated holding.
    """

    user = await get_user(session, user_id)
    await session.rollback()
    if not user:
        logger.warning(
            "create_brokerage_event_endpoint: unknown user_id"
        )
        raise HTTPException(status_code=400, detail='Unknown user_id')
    
    async with session.begin():
        event, holding = await create_brokerage_event_and_update_holding(session, payload)
    
    if holding:
        holding = HoldingRead.model_validate(holding)

    return BrokerageEventWithHoldingRead(
        id=event.id,
        brokerage_account_id=event.brokerage_account_id,
        instrument_id=event.instrument_id,
        kind=event.kind,
        quantity=event.quantity,
        price=event.price,
        currency=event.currency,
        split_ratio=event.split_ratio,
        trade_at=event.trade_at,
        holding=holding,
    )
    
    
@router.post(
    "/brokerage/events/import",
    response_model=BrokerageEventsImportSummary,
)
async def import_brokerage_events_endpoint(
    payload: BrokerageEventsImportRequest,
    user_id: uuid.UUID = Depends(get_internal_user_id),
    session: AsyncSession = Depends(db.get_session),
) -> BrokerageEventsImportSummary:
    """
    Import a batch of brokerage events and update holdings for each row.

    Flow:
        1. Validate that `user_id` points to an existing user.
        2. For each event row:
           - Build a `BrokerageEventCreate` payload.
           - Execute `create_brokerage_event_and_update_holding` in a transaction.
           - Track `created`, `failed`, and collect per-row errors.
        3. Return a summary including counts and error messages.

    Args:
        payload: Request body containing target `brokerage_account_id` and a list of events.
        user_id: Internal user ID obtained from the request context/dependency.
        session: Async SQLAlchemy session (dependency-injected).

    Raises:
        HTTPException(400): If the user does not exist.

    Returns:
        `BrokerageEventsImportSummary` with:
            - created: number of successfully imported events
            - failed: number of rows that failed
            - errors: list of human-readable error descriptions
    """
    
    user = await get_user(session, user_id)
    await session.rollback()
    if not user:
        logger.warning(
            "import_brokerage_events_endpoint: unknown user_id"
        )
        raise HTTPException(status_code=400, detail='Unknown user_id')

    created = 0
    failed = 0
    errors: list[str] = []

    for idx, row in enumerate(payload.events, start=1):
        be_payload = BrokerageEventCreate(
            brokerage_account_id=payload.brokerage_account_id,
            instrument_symbol=row.instrument_symbol,
            instrument_mic=row.instrument_mic,
            instrument_name=row.instrument_name,
            kind=row.kind,
            quantity=row.quantity,
            price=row.price,
            currency=row.currency,
            split_ratio=row.split_ratio,
            trade_at=row.trade_at,
        )

        try:
            async with session.begin():
                event, holding = await create_brokerage_event_and_update_holding(
                    session, be_payload, creat_transaction=False
                )
            created += 1
        except HTTPException as e:
            failed += 1
            msg = f"Row {idx}: HTTP {e.status_code} - {e.detail}"
            logger.warning(msg)
            errors.append(msg)
        except Exception as e: 
            failed += 1
            msg = f"Row {idx}: unexpected error: {e}"
            logger.exception(
                f"import_brokerage_events_endpoint: unexpected error for row {idx}"
            )
            errors.append(msg)

    return BrokerageEventsImportSummary(
        created=created,
        failed=failed,
        errors=errors,
    )
    

@router.get("/brokerage/events", response_model=BrokerageEventPageOut)
async def get_brokerage_events_page(
    page: int = Query(1, ge=1),
    size: int = Query(40, ge=1, le=200),
    brokerage_account_id: Optional[List[uuid.UUID]] = Query(None),
    kind: Optional[List[str]] = Query(None),
    currency: Optional[List[str]] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    q: Optional[str] = Query(None),
    user_id: uuid.UUID = Depends(get_internal_user_id),
    session: AsyncSession = Depends(db.get_session),
) -> BrokerageEventPageOut:
    """
    Return a paginated list of brokerage events for the user with optional filters.

    Filters:
        - brokerage_account_id: filter by one or more brokerage accounts
        - kind: event kinds (strings, e.g. BUY/SELL/...)
        - currency: currencies (strings, e.g. PLN/USD/...)
        - date_from/date_to: inclusive boundaries (depends on your CRUD implementation)
        - q: free-text search

    Args:
        page: 1-based page index.
        size: page size (1..200).
        brokerage_account_id: list of brokerage account UUIDs.
        kind: list of event kind strings.
        currency: list of currency strings.
        date_from: filter start date.
        date_to: filter end date.
        q: optional search query.
        user_id: authenticated user id.
        session: SQLAlchemy async session.

    Returns:
        BrokerageEventPageOut with enriched row items (account name + instrument info).
    """
    logger.info("GET /brokerage/events: start ")
    
    rows, total, page, size, sum_by_ccy = await list_brokerage_events_page(
        session=session,
        user_id=user_id,
        page=page,
        size=size,
        brokerage_account_ids=brokerage_account_id,
        kinds=kind,
        currencies=currency,
        date_from=date_from,
        date_to=date_to,
        q=q,
    )

    items: list[BrokerageEventRowOut] = []
    for ev, acc, inst, _wallet in rows:
        items.append(
            BrokerageEventRowOut(
                **ev.model_dump(),
                brokerage_account_name=acc.name,
                instrument_symbol=inst.symbol,
                instrument_name=getattr(inst, "name", None),
            )
        )

    return BrokerageEventPageOut(items=items, total=total, page=page, size=size, sum_by_ccy=sum_by_ccy)


@router.patch("/brokerage/events/batch")
async def patch_brokerage_events_batch(
    req: BatchUpdateBrokerageEventsRequest,
    user_id: uuid.UUID = Depends(get_internal_user_id),
    session: AsyncSession = Depends(db.get_session),
) -> dict:
    """
    Batch-update brokerage events for the user.

    The request contains a list of patch items, which are forwarded to the CRUD layer.

    Args:
        req: Batch update request payload.
        user_id: authenticated user id.
        session: SQLAlchemy async session.

    Returns:
        {"updated": <count>} where count is number of updated rows.
    """
    logger.info("PATCH /brokerage/events/batch: start")
    async with session.begin():
        updated = await batch_patch_brokerage_events(session=session, user_id=user_id, items=[i.model_dump() for i in req.items])
    return {"updated": updated}


@router.delete("/brokerage/events/{event_id}")
async def api_delete_brokerage_event(
    event_id: uuid.UUID, 
    user_id: uuid.UUID = Depends(get_internal_user_id),
    session: AsyncSession = Depends(db.get_session),
) -> dict:
    """
    Delete a brokerage event by id and rebuild holdings if needed.

    Args:
        event_id: brokerage event UUID.
        user_id: authenticated user id.
        session: SQLAlchemy async session.

    Returns:
        {"ok": True} if deleted.

    Raises:
        HTTPException(404): if the event is not found for this user.
    """
    logger.info(f"DELETE /brokerage/events/{event_id}: start")
    async with session.begin():
        ok = await delete_brokerage_event_and_rebuild_holding(session=session, user_id=user_id, event_id=event_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Event not found")
    return {"ok": True}