from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status
from typing import Tuple, Optional
from decimal import Decimal
import logging

from app.models.models import Holding, BrokerageEvent
from app.models.enums import BrokerageEventKind, CapitalGainKind
from app.schamas.schemas import BrokerageEventCreate, TransactionIn, CreateTransactionsRequest, CapitalGainCreate
from app.crud.holding_crud import get_or_create_holding, apply_event_to_holding
from app.crud.broker_event_crud import create_brokerage_event, find_duplicate_brokerage_event
from app.crud.deposit_account_crud import resolve_deposit_for_event
from app.crud.instrument_crud import get_or_create_instrument
from app.crud.brokerage_account_crud import get_brokerage_account
from app.utils.money import compute_cash_effect
from app.api.services.transactions import create_transactions_service
from app.crud.capital_gain_crud import create_capital_gain

logger = logging.getLogger(__name__)


async def create_brokerage_event_and_update_holding(
    session: AsyncSession,
    payload: BrokerageEventCreate,
    creat_transaction: bool = True
) -> Tuple[BrokerageEvent, Optional[Holding]]:
    """
    Create a brokerage event, update (or delete) the related holding, and
    optionally create a cash transaction & capital gain record.

    Flow:
        1. Validate the brokerage account exists.
        2. Resolve or create the underlying instrument.
        3. Detect duplicate events for the same account + instrument + params.
        4. Resolve or create the holding for (brokerage_account, instrument).
        5. If it's a SELL trade, compute realized P&L based on avg_cost.
        6. Apply the event to the holding (quantity/avg_cost update).
           - If holding quantity becomes zero, delete the holding.
        7. Create the brokerage event row.
        8. Compute the cash effect and:
           - Resolve the deposit account mapping.
           - Create a linked cash transaction.
           - If realized P&L is non-zero, create a capital gain entry.
        9. Refresh and return (event, holding or None).

    Args:
        session: Active async SQLAlchemy session.
        payload: Brokerage event data (account, instrument, quantity, price, etc.).

    Raises:
        HTTPException(404): If the brokerage account is not found.
        HTTPException(409): If a duplicate brokerage event is detected.

    Returns:
        Tuple of:
            - BrokerageEvent: The created brokerage event model.
            - Optional[Holding]: The updated holding or None if it was deleted
              (when quantity drops to zero).
    """

    account = await get_brokerage_account(session, payload.brokerage_account_id)
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Brokerage account not found.",
        )

    instrument = await get_or_create_instrument(
        session,
        mic=payload.instrument_mic,
        symbol=payload.instrument_symbol,
        name=payload.instrument_name,
        currency=payload.currency,  
    )
    
    dup_event = await find_duplicate_brokerage_event(session, payload, instrument.id)
    if dup_event is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Brokerage event already exists for this account, instrument and parameters.",
        )

    holding = await get_or_create_holding(
        session,
        account_id=payload.brokerage_account_id,
        instrument_id=instrument.id,
    )
    
    realized_pnl = Decimal("0")

    if payload.kind == BrokerageEventKind.TRADE_SELL:
        q = Decimal(payload.quantity)
        p = Decimal(payload.price)
        old_avg = Decimal(holding.avg_cost or 0)
        realized_pnl = (p - old_avg) * q
        
    apply_event_to_holding(holding, payload)
    
    delete_holding = False
    if holding.quantity == 0:
        logger.info("holding is equal 0")
        delete_holding = True
        await session.delete(holding)
        
    event = await create_brokerage_event(session, payload, instrument.id)
    
    cash_amount = compute_cash_effect(
        payload.kind,
        payload.quantity,
        payload.price,
    )
    
    if cash_amount != 0:
        deposit = await resolve_deposit_for_event(
            session,
            brokerage_account_id=payload.brokerage_account_id,
            currency=payload.currency,
        )
        if not deposit:
            logger.warning(
                f"No deposit account mapping for brokerage_account_id={payload.brokerage_account_id} "
                f"and currency={payload.currency}"
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="can not found deposit account for this brokerage account",
            )
        transaction_id = None
        
        if creat_transaction:
            tx_in = TransactionIn(
                date=payload.trade_at,
                amount=cash_amount,
                description=(
                    f"{payload.kind.value} {payload.instrument_symbol} "
                    f"{payload.quantity} @ {payload.price}"
                ),
                amount_after=None,
            )
            tx_request = CreateTransactionsRequest(
                account_id=deposit.id,
                transactions=[tx_in],
            )
            tx_summary = await create_transactions_service(
                session=session,
                payload=tx_request,
                verify_amount_after=False,
                return_tr=True
            )
            
            transaction_id = tx_summary['transaction_ids'][-1]

        if realized_pnl != 0:
            data = CapitalGainCreate(
                kind=CapitalGainKind.BROKER_REALIZED_PNL,
                amount=realized_pnl,
                currency=payload.currency,
                occurred_at=payload.trade_at,
                deposit_account_id=deposit.id,
                transaction_id=transaction_id
            )

            await create_capital_gain(session, data)
            
    if not delete_holding:
        await session.refresh(holding)
        return event, holding 
    else:
        return event, None