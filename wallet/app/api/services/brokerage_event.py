from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status
from typing import Tuple, Optional
from decimal import Decimal
import logging

from app.models.models import Holding, BrokerageEvent
from app.models.enums import BrokerageEventKind, CapitalGainKind, Currency, InstrumentCurrency, InstrumentType
from app.schemas.schemas import BrokerageEventCreate, TransactionIn, CreateTransactionsRequest, CapitalGainCreate
from app.schemas.response import StockInstrumentRead
from app.crud.holding_crud import (
    apply_conversion_to_holding_pair,
    apply_event_to_holding,
    get_holding_by_keys,
    get_or_create_holding,
)
from app.crud.broker_event_crud import create_brokerage_event, find_duplicate_brokerage_event
from app.crud.deposit_account_crud import resolve_deposit_for_event
from app.crud.instrument_crud import get_or_create_instrument
from app.crud.brokerage_account_crud import get_brokerage_account
from app.utils.money import compute_cash_effect
from app.api.services.transactions import create_transactions_service
from app.crud.capital_gain_crud import create_capital_gain
from app.clients.stock_client import StockClient

logger = logging.getLogger(__name__)


def _wallet_currency(value: str | InstrumentCurrency) -> InstrumentCurrency:
    try:
        return value if isinstance(value, InstrumentCurrency) else InstrumentCurrency(str(value).upper())
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported instrument currency from stock-service: {value}",
        ) from exc


def _base_currency_or_none(value: str | Currency | InstrumentCurrency | None) -> Optional[Currency]:
    """Return the matching base (reporting) Currency or None if unsupported (e.g. CHF/GBP)."""
    if value is None:
        return None
    if isinstance(value, Currency):
        return value
    raw = getattr(value, "value", value)
    try:
        return Currency(str(raw).upper())
    except ValueError:
        return None


def _validate_cash_settlement_payload(payload: BrokerageEventCreate) -> None:
    cash_amount = compute_cash_effect(
        payload.kind,
        payload.quantity,
        payload.price,
    )
    if cash_amount == 0:
        return

    event_base_ccy = _base_currency_or_none(payload.currency)
    if event_base_ccy is None:
        if payload.settlement_currency is None or payload.fx_rate is None:
            currency_label = getattr(payload.currency, "value", str(payload.currency))
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Brokerage event currency {currency_label} requires "
                    "settlement_currency and fx_rate for cash settlement."
                ),
            )
        return

    if payload.settlement_currency is not None and payload.settlement_currency != event_base_ccy:
        if payload.fx_rate is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Brokerage event settlement conversion requires fx_rate.",
            )


def _wallet_instrument_type(value: str) -> InstrumentType:
    try:
        return InstrumentType(str(value).upper())
    except ValueError:
        return InstrumentType.STOCK


async def resolve_stock_instrument(
    mic: str,
    symbol: str,
    stock_client: StockClient | None = None,
) -> StockInstrumentRead:
    owns_client = stock_client is None
    client = stock_client or StockClient()
    try:
        return await client.resolve_instrument(mic, symbol)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Instrument must be created in stock first.",
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Stock service unavailable.",
        ) from exc
    finally:
        if owns_client:
            await client.aclose()


async def get_or_create_stock_backed_instrument(
    session: AsyncSession,
    mic: str,
    symbol: str,
    stock_client: StockClient | None = None,
):
    stock_instrument = await resolve_stock_instrument(mic, symbol, stock_client=stock_client)
    return await get_or_create_instrument(
        session,
        mic=stock_instrument.mic,
        symbol=stock_instrument.symbol,
        name=stock_instrument.shortname or stock_instrument.name or stock_instrument.symbol,
        currency=_wallet_currency(stock_instrument.currency),
        instrument_type=_wallet_instrument_type(stock_instrument.type),
    )


def _require_conversion_target(payload: BrokerageEventCreate) -> tuple[str, str, str]:
    symbol = (payload.target_instrument_symbol or "").strip()
    mic = (payload.target_instrument_mic or "").strip()
    name = (payload.target_instrument_name or symbol).strip()

    if not symbol or not mic or not name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CONVERSION target instrument is required.",
        )

    if symbol == payload.instrument_symbol and mic == payload.instrument_mic:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CONVERSION target instrument must differ from source instrument.",
        )

    return symbol, mic, name


async def create_brokerage_event_and_update_holding(
    session: AsyncSession,
    payload: BrokerageEventCreate,
    creat_transaction: bool = True,
    stock_client: StockClient | None = None,
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

    instrument = await get_or_create_stock_backed_instrument(
        session,
        mic=payload.instrument_mic,
        symbol=payload.instrument_symbol,
        stock_client=stock_client,
    )
    target_instrument = None
    if payload.kind == BrokerageEventKind.CONVERSION:
        target_symbol, target_mic, _target_name = _require_conversion_target(payload)
        target_instrument = await get_or_create_stock_backed_instrument(
            session,
            mic=target_mic,
            symbol=target_symbol,
            stock_client=stock_client,
        )
    
    dup_event = await find_duplicate_brokerage_event(
        session,
        payload,
        instrument.id,
        target_instrument_id=getattr(target_instrument, "id", None),
    )
    if dup_event is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Brokerage event already exists for this account, instrument and parameters.",
        )

    _validate_cash_settlement_payload(payload)

    if payload.kind == BrokerageEventKind.CONVERSION:
        source_holding = await get_holding_by_keys(
            session,
            account_id=payload.brokerage_account_id,
            instrument_id=instrument.id,
        )
        if source_holding is None:
            source_holding = await get_or_create_holding(
                session,
                account_id=payload.brokerage_account_id,
                instrument_id=instrument.id,
            )
        target_holding = await get_or_create_holding(
            session,
            account_id=payload.brokerage_account_id,
            instrument_id=target_instrument.id,
        )

        apply_conversion_to_holding_pair(source_holding, target_holding, payload)

        delete_source_holding = source_holding.quantity == 0
        if delete_source_holding:
            await session.delete(source_holding)

        event = await create_brokerage_event(
            session,
            payload,
            instrument.id,
            target_instrument_id=target_instrument.id,
        )

        await session.refresh(target_holding)
        return event, target_holding

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

    # Cash settles in the account (base) currency, not necessarily the instrument
    # currency. settlement_currency (PLN/USD/EUR) + fx_rate (instrument->settlement)
    # come from the import row; when absent we fall back to the event currency
    # only for same-currency base settlement.
    settlement_ccy = payload.settlement_currency or _base_currency_or_none(payload.currency)
    needs_conversion = (
        payload.settlement_currency is not None
        and _base_currency_or_none(payload.currency) != payload.settlement_currency
    )

    if cash_amount != 0:
        rate = payload.fx_rate if needs_conversion else None
        cash_settle = cash_amount * rate if rate is not None else cash_amount
        pnl_settle = realized_pnl * rate if rate is not None else realized_pnl

        deposit = await resolve_deposit_for_event(
            session,
            brokerage_account_id=payload.brokerage_account_id,
            currency=settlement_ccy,
        )
        if not deposit:
            logger.warning(
                f"No deposit account mapping for brokerage_account_id={payload.brokerage_account_id} "
                f"and currency={settlement_ccy}"
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="can not found deposit account for this brokerage account",
            )
        transaction_id = None

        if creat_transaction:
            tx_in = TransactionIn(
                date=payload.trade_at,
                amount=cash_settle,
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

        if pnl_settle != 0:
            data = CapitalGainCreate(
                kind=CapitalGainKind.BROKER_REALIZED_PNL,
                amount=pnl_settle,
                currency=settlement_ccy,
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
