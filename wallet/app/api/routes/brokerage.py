from fastapi import APIRouter, Depends, HTTPException
import uuid
import logging
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import db
from app.schamas.response import BrokerageEventWithHoldingRead, BrokerageEventsImportSummary
from app.schamas.schemas import BrokerageEventCreate, HoldingRead, BrokerageEventsImportRequest
from app.api.services.brokerage_event import create_brokerage_event_and_update_holding
from app.api.deps import get_internal_user_id
from app.crud.user_crud import get_user


logger = logging.getLogger(__name__)

router = APIRouter()


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
                    session, be_payload,
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