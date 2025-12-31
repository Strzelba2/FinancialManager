import uuid
from decimal import Decimal
from datetime import datetime, timezone
from fastapi import HTTPException
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import CapitalGain
from app.models.enums import CapitalGainKind, Currency
from app.schamas.response import SellMetalIn, SellRealEstateIn
from app.schamas.schemas import TransactionCreate, MetalHoldingUpdate

from app.crud.metal_holding_crud import get_metal_holding, delete_metal_holding, update_metal_holding
from app.crud.real_estate_crud import get_real_estate, delete_real_estate
from app.crud.wallet_crud import get_wallet
from app.crud.deposit_account_crud import get_deposit_account
from app.crud.deposit_account_balance import get_deposit_account_balance
from app.crud.transaction_crud import create_transaction_uow, get_last_balance_after
from app.utils.utils import ccy_str

logger = logging.getLogger(__name__)


async def sell_metal_holding_service(
    session: AsyncSession,
    user_id: uuid.UUID,
    metal_holding_id: uuid.UUID,
    req: SellMetalIn,
) -> int:
    """
    Sell (part of) a metal holding and optionally create an INCOME transaction + capital gain record.

    Flow:
      1) Load metal holding and verify wallet ownership.
      2) Validate deposit account belongs to the same wallet and currency matches proceeds/cost currency.
      3) Validate grams_sold and compute allocated cost + PnL.
      4) Create CapitalGain entry.
      5) Optionally create a Transaction and update deposit account balance.
      6) Update or delete the metal holding depending on remaining grams.

    Args:
        session: SQLAlchemy async session.
        user_id: Authenticated user UUID.
        metal_holding_id: Metal holding UUID to sell from.
        req: SellMetalIn request (grams_sold, proceeds_amount, proceeds_currency, deposit_account_id, etc.).

    Returns:
        int: 1 on success, 0 when deposit account is missing/mismatched wallet (keeps your original semantics).

    Raises:
        HTTPException: for not found / forbidden / validation errors.
    """
    async with session.begin():  
        mh = await get_metal_holding(session, metal_holding_id)
        if mh is None:
            raise HTTPException(status_code=404, detail='Metal not found.')

        w = await get_wallet(session, mh.wallet_id)
        if w is None or w.user_id != user_id:
            raise HTTPException(status_code=404, detail='Wallet not found.')

        acc = await get_deposit_account(session, req.deposit_account_id)
        if acc is None or acc.wallet_id != mh.wallet_id:
            return 0

        if ccy_str(acc.currency) != str(req.proceeds_currency):
            raise HTTPException(status_code=400, detail='Deposit account belongs to a different wallet than the asset')
        if ccy_str(mh.cost_currency) != str(req.proceeds_currency):
            raise HTTPException(
                status_code=400, 
                detail=f"Deposit account currency is {ccy_str(acc.currency)}, but proceeds currency is {req.proceeds_currency}."
                )

        total_grams = Decimal(str(mh.grams or "0"))
        if req.grams_sold <= 0 or req.grams_sold > total_grams:
            raise HTTPException(status_code=400, detail='The quantity for sale cannot exceed the quantity held')

        cost_basis = Decimal(str(mh.cost_basis or "0"))
        ratio = req.grams_sold / total_grams if total_grams > 0 else Decimal("0")
        allocated_cost = cost_basis * ratio if cost_basis > 0 else Decimal("0")
        pnl = req.proceeds_amount - allocated_cost

        occurred = req.occurred_at or datetime.now(timezone.utc)

        cg = CapitalGain(
            kind=CapitalGainKind.METAL_REALIZED_PNL,
            amount=pnl,
            currency=Currency(str(req.proceeds_currency)),
            occurred_at=occurred,
            deposit_account_id=req.deposit_account_id,
            transaction_id=None,
        )
        session.add(cg)

        if req.create_transaction:
            before = await get_last_balance_after(session, req.deposit_account_id)
            after = before + req.proceeds_amount

            tx = await create_transaction_uow(
                session,
                TransactionCreate(
                    account_id=req.deposit_account_id,
                    amount=req.proceeds_amount,
                    description=f"Metal sale: {ccy_str(mh.metal) if hasattr(mh, 'metal') else 'Metal'}",
                    category="INVESTMENTS",
                    status="INCOME",
                    balance_before=before,
                    balance_after=after,
                    date_transaction=occurred,
                ),
            )
            cg.transaction_id = tx.id
            
            bal = await get_deposit_account_balance(session, req.deposit_account_id)
            
            bal.available = after
            session.add(bal)
            await session.flush()
            
        new_grams = total_grams - req.grams_sold
        new_cost = cost_basis - allocated_cost

        if new_grams <= 0:
            await delete_metal_holding(session, mh)
        else:
            payload = MetalHoldingUpdate(grams=new_grams, cost_basis=new_cost)
            await update_metal_holding(
                session=session,
                metal_holding_id=mh.id,
                payload=payload,
            )

        return 1


async def sell_real_estate_service(
    session: AsyncSession,
    user_id: uuid.UUID,
    real_estate_id: uuid.UUID,
    req: SellRealEstateIn,
) -> int:
    """
    Sell a real estate asset, create a capital gain record, optionally create an INCOME transaction,
    update deposit account balance, and delete the real estate record.

    Args:
        session: SQLAlchemy async session.
        user_id: Authenticated user UUID.
        real_estate_id: Real estate UUID being sold.
        req: SellRealEstateIn request (deposit_account_id, proceeds_amount, proceeds_currency, occurred_at, ...).

    Returns:
        int: 1 on success.

    Raises:
        HTTPException: for not found / forbidden / validation errors.
    """
    async with session.begin():
        re = await get_real_estate(session, real_estate_id)
        if re is None:
            raise HTTPException(status_code=404, detail='Real estate not found.')

        w = await get_wallet(session, re.wallet_id)
        if w is None or w.user_id != user_id:
            raise HTTPException(status_code=404, detail='Wallet not found.')

        acc = await get_deposit_account(session, req.deposit_account_id)
        if acc is None or acc.wallet_id != re.wallet_id:
            raise HTTPException(status_code=404, detail='Deposit account not found.')

        if ccy_str(acc.currency) != str(req.proceeds_currency):
            raise HTTPException(status_code=400, detail='Deposit account belongs to a different wallet than the asset')
        if ccy_str(re.purchase_currency) != str(req.proceeds_currency):
            raise HTTPException(
                status_code=400, 
                detail=f"Deposit account currency is {ccy_str(acc.currency)}, but proceeds currency is {req.proceeds_currency}."
                )

        purchase_price = Decimal(str(re.purchase_price or "0"))
        pnl = req.proceeds_amount - purchase_price
        occurred = req.occurred_at or datetime.now(timezone.utc)

        cg = CapitalGain(
            kind=CapitalGainKind.REAL_ESTATE_REALIZED_PNL,
            amount=pnl,
            currency=Currency(str(req.proceeds_currency)),
            occurred_at=occurred,
            deposit_account_id=req.deposit_account_id,
            transaction_id=None,
        )
        session.add(cg)

        if req.create_transaction:
            before = await get_last_balance_after(session, req.deposit_account_id)
            after = before + req.proceeds_amount

            tx = await create_transaction_uow(
                session,
                TransactionCreate(
                    account_id=req.deposit_account_id,
                    amount=req.proceeds_amount,
                    description=f"Property sale: {getattr(re, 'name', '')}".strip() or "Property sale",
                    category="INVESTMENTS",
                    status="INCOME",
                    balance_before=before,
                    balance_after=after,
                    date_transaction=occurred,
                ),
            )
            cg.transaction_id = tx.id
            
            bal = await get_deposit_account_balance(session, req.deposit_account_id)
            
            bal.available = after
            session.add(bal)
            await session.flush()

        await delete_real_estate(session, re.id) 
        return 1
