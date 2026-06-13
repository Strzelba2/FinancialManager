from fastapi import APIRouter, Depends, HTTPException, Query, status
import uuid
from datetime import date
from typing import Optional, List
import logging
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import db
from app.schemas.response import (
    BrokerageEventWithHoldingRead, BrokerageEventsImportSummary, BrokerageEventPageOut,
    BrokerageEventRowOut, BatchUpdateBrokerageEventsRequest, BrokerageCashLinkResult
    )
from app.schemas.schemas import (
    BrokerageEventCreate, HoldingRead, BrokerageEventsImportRequest, BrokerageAccountRead,
    BrokerageCashLinksEnsureRequest, BrokerageHistoryImportRequest
    )
from app.models.enums import BrokerageEventKind
from app.api.services.brokerage_event import (
    create_brokerage_event_and_update_holding
    )
from app.api.services.brokerage_history_import import import_brokerage_history_service
from app.api.services.accounts import (
    create_brokerage_cash_account_link_service,
    delete_brokerage_account_with_cash_accounts_service,
)
from app.api.deps import get_auth_crypto, get_internal_user_id, get_stock_client
from app.clients.auth_client import AuthCryptoClient
from app.clients.stock_client import StockClient
from app.crud.brokerage_deposit_link_crud import get_link_by_ba_and_currency
from app.crud.broker_event_crud import (
    list_brokerage_events_page, batch_patch_brokerage_events, delete_brokerage_event_and_rebuild_holding
    )
from app.crud.holding_crud import HoldingQuantityExceeded
from app.crud.brokerage_account_crud import (
    list_brokerage_accounts_for_user, get_brokerage_account_for_user
)
from app.crud.user_crud import get_user


logger = logging.getLogger(__name__)

router = APIRouter()


def _brokerage_row_context(row) -> dict:
    return {
        "instrument_symbol": row.instrument_symbol,
        "instrument_name": row.instrument_name,
        "kind": row.kind,
        "trade_at": row.trade_at,
        "quantity": row.quantity,
    }


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
    "/brokerage/{brokerage_account_id}/cash-links/ensure",
    response_model=list[BrokerageCashLinkResult],
)
async def ensure_brokerage_cash_links(
    brokerage_account_id: uuid.UUID,
    payload: BrokerageCashLinksEnsureRequest,
    user_id: uuid.UUID = Depends(get_internal_user_id),
    session: AsyncSession = Depends(db.get_session),
    crypto: AuthCryptoClient = Depends(get_auth_crypto),
) -> list[BrokerageCashLinkResult]:
    user = await get_user(session, user_id)
    if not user:
        raise HTTPException(status_code=400, detail='Unknown user_id')
    username = user.username
    await session.rollback()

    brokerage_account = await get_brokerage_account_for_user(
        session=session,
        user_id=user_id,
        brokerage_account_id=brokerage_account_id,
    )
    if brokerage_account is None:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Brokerage account not found.",
        )
    brokerage_id = brokerage_account.id
    brokerage_wallet_id = brokerage_account.wallet_id
    brokerage_bank_id = brokerage_account.bank_id
    brokerage_name = brokerage_account.name
    await session.rollback()

    seen = set()
    results: list[BrokerageCashLinkResult] = []
    for cash_account in payload.cash_accounts:
        if cash_account.currency in seen:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Duplicate brokerage cash currency: {cash_account.currency.value}",
            )
        seen.add(cash_account.currency)

        existing = await get_link_by_ba_and_currency(
            session,
            brokerage_account_id=brokerage_id,
            currency=cash_account.currency,
        )
        if existing is not None:
            results.append(
                BrokerageCashLinkResult(
                    currency=cash_account.currency,
                    deposit_account_id=existing.deposit_account_id,
                    created=False,
                )
            )
            continue

        account = await create_brokerage_cash_account_link_service(
            session=session,
            brokerage_account_id=brokerage_id,
            wallet_id=brokerage_wallet_id,
            bank_id=brokerage_bank_id,
            brokerage_name=brokerage_name,
            cash_account=cash_account,
            username=username,
            crypto=crypto,
        )
        results.append(
            BrokerageCashLinkResult(
                currency=cash_account.currency,
                deposit_account_id=account.id,
                created=True,
                name=account.name,
            )
        )

    return results


@router.post(
    "/brokerage/event",
    response_model=BrokerageEventWithHoldingRead,
)
async def create_brokerage_event_endpoint(
    payload: BrokerageEventCreate,
    user_id: uuid.UUID = Depends(get_internal_user_id),
    session: AsyncSession = Depends(db.get_session),
    stock_client: StockClient = Depends(get_stock_client),
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

    brokerage_account = await get_brokerage_account_for_user(
        session=session,
        user_id=user_id,
        brokerage_account_id=payload.brokerage_account_id,
    )
    await session.rollback()
    if brokerage_account is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Brokerage account not found.",
        )
    
    async with session.begin():
        event, holding = await create_brokerage_event_and_update_holding(
            session,
            payload,
            stock_client=stock_client,
        )
    
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
        note=event.note,
        target_instrument_id=event.target_instrument_id,
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
    stock_client: StockClient = Depends(get_stock_client),
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

    brokerage_account = await get_brokerage_account_for_user(
        session=session,
        user_id=user_id,
        brokerage_account_id=payload.brokerage_account_id,
    )
    await session.rollback()
    if brokerage_account is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Brokerage account not found.",
        )

    total = len(payload.events)
    created = 0
    skipped_duplicates = 0
    failed = 0
    errors: list[str] = []
    rows: list[dict] = []

    # Apply events oldest-first so that holdings build up before they are reduced
    # (broker exports such as Saxo list newest-first, which would otherwise process
    # a SELL before its BUY). The original 1-based index is kept for row labels.
    ordered_events = sorted(enumerate(payload.events, start=1), key=lambda pair: pair[1].trade_at)

    for idx, row in ordered_events:
        if row.kind == BrokerageEventKind.CONVERSION:
            failed += 1
            msg = "CONVERSION events must be created manually through holding actions."
            errors.append(f"Row {idx}: {msg}")
            rows.append(
                {
                    "row": idx,
                    "status": "failed",
                    "message": msg,
                    "reason_code": "conversion_import_not_supported",
                    **_brokerage_row_context(row),
                }
            )
            continue

        be_payload = BrokerageEventCreate(
            brokerage_account_id=payload.brokerage_account_id,
            instrument_symbol=row.instrument_symbol,
            instrument_mic=row.instrument_mic,
            instrument_name=row.instrument_name or row.instrument_symbol,
            kind=row.kind,
                quantity=row.quantity,
                price=row.price,
                currency=row.currency,
                split_ratio=row.split_ratio,
                note=row.note,
                target_instrument_id=row.target_instrument_id,
                trade_at=row.trade_at,
                settlement_currency=row.settlement_currency,
                fx_rate=row.fx_rate,
            )

        try:
            async with session.begin():
                event, holding = await create_brokerage_event_and_update_holding(
                    session,
                    be_payload,
                    creat_transaction=False,
                    stock_client=stock_client,
                )
            created += 1
            rows.append(
                {
                    "row": idx,
                    "status": "created",
                    "brokerage_event_id": event.id,
                    **_brokerage_row_context(row),
                }
            )
        except HoldingQuantityExceeded as e:
            failed += 1
            msg = f"Row {idx}: HTTP {e.status_code} - {e.detail}"
            logger.warning(msg)
            errors.append(msg)
            rows.append(
                {
                    "row": idx,
                    "status": "failed",
                    "message": msg,
                    **_brokerage_row_context(row),
                    **e.context,
                }
            )
        except HTTPException as e:
            if e.status_code == status.HTTP_409_CONFLICT:
                skipped_duplicates += 1
                msg = f"Row {idx}: skipped duplicate - {e.detail}"
                logger.info(msg)
                rows.append(
                    {
                        "row": idx,
                        "status": "skipped_duplicate",
                        "message": str(e.detail),
                        **_brokerage_row_context(row),
                    }
                )
                continue

            failed += 1
            msg = f"Row {idx}: HTTP {e.status_code} - {e.detail}"
            logger.warning(msg)
            errors.append(msg)
            rows.append(
                {
                    "row": idx,
                    "status": "failed",
                    "message": msg,
                    **_brokerage_row_context(row),
                }
            )
        except Exception as e: 
            failed += 1
            msg = f"Row {idx}: unexpected error: {e}"
            logger.exception(
                f"import_brokerage_events_endpoint: unexpected error for row {idx}"
            )
            errors.append(msg)
            rows.append(
                {
                    "row": idx,
                    "status": "failed",
                    "message": msg,
                    **_brokerage_row_context(row),
                }
            )

    return BrokerageEventsImportSummary(
        total=total,
        created=created,
        skipped_duplicates=skipped_duplicates,
        failed=failed,
        errors=errors,
        rows=rows,
    )


@router.post(
    "/brokerage/history/import",
    response_model=BrokerageEventsImportSummary,
)
async def import_brokerage_history_endpoint(
    payload: BrokerageHistoryImportRequest,
    user_id: uuid.UUID = Depends(get_internal_user_id),
    session: AsyncSession = Depends(db.get_session),
    stock_client: StockClient = Depends(get_stock_client),
) -> BrokerageEventsImportSummary:
    user = await get_user(session, user_id)
    await session.rollback()
    if not user:
        logger.warning("import_brokerage_history_endpoint: unknown user_id")
        raise HTTPException(status_code=400, detail='Unknown user_id')

    brokerage_account = await get_brokerage_account_for_user(
        session=session,
        user_id=user_id,
        brokerage_account_id=payload.brokerage_account_id,
    )
    await session.rollback()
    if brokerage_account is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Brokerage account not found.",
        )

    async with session.begin():
        return await import_brokerage_history_service(
            session=session,
            user_id=user_id,
            payload=payload,
            stock_client=stock_client,
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


@router.delete("/brokerage/{brokerage_account_id}")
async def api_delete_brokerage_account(
    brokerage_account_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_internal_user_id),
    session: AsyncSession = Depends(db.get_session),
):
    """
    Delete a brokerage account for the authenticated user.

    Args:
        brokerage_account_id: Brokerage account UUID to delete.
        user_id: Internal user UUID resolved from request (dependency).
        session: SQLAlchemy async database session (dependency).

    Returns:
        A dict with `{"ok": True}` when the account was deleted.

    Raises:
        HTTPException:
            - 400 if the user_id is unknown.
            - 404 if the brokerage account does not exist for this user.
            - 404 if deletion fails because the account does not exist (race/consistency case).
    """
    user = await get_user(session, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Unknown user_id')
    
    account = await get_brokerage_account_for_user(
            session,
            user_id=user_id,
            brokerage_account_id=brokerage_account_id,
        )
    
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Account not found')
    
    ok = await delete_brokerage_account_with_cash_accounts_service(
        session=session,
        user_id=user_id,
        brokerage_account_id=brokerage_account_id,
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Brokerage account not found")
    return {"ok": True}
