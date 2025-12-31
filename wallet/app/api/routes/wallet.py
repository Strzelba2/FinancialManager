from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Dict
from datetime import datetime, timezone
from decimal import Decimal
import logging
import uuid

from app.models.models import Holding
from app.models.enums import Currency, CapitalGainKind
from app.schamas.schemas import (
    UserCreate, WalletCreate, WalletCreateWithoutUser
    )
from app.schamas.response import (
    WalletUserResponse, WalletResponse, WalletListItem, AccountListItem, BrokerageAccountListItem,
    QuoteBySymbolItem, BrokerageEventListItem, RealEstateItem, MetalHoldingItem, DebtItem,
    RecurringExpenseItem, YearGoalRead
    )
from app.api.services.user import sync_user
from app.api.services.wallet import create_wallet_service, delete_wallet_service, dash_flow_8m
from app.api.services.holding import (
    compute_top_n_performance_from_quotes, 
    compute_brokerage_account_value_by_currency_from_quotes
    )
from app.api.services.real_estate import get_latest_price_with_fallback
from app.api.services.transactions import compute_wallet_ytd_income_expense_maps
from app.db.session import db
from app.clients.stock_client import StockClient
from app.api.deps import get_internal_user_id, get_stock_client
from app.crud.wallet_crud import list_wallets
from app.crud.user_crud import get_user
from app.crud.bank_crud import list_banks
from app.crud.deposit_account_crud import list_deposit_accounts
from app.crud.transaction_crud import get_last_transactions_for_account
from app.crud.brokerage_account_crud import list_brokerage_accounts
from app.crud.broker_event_crud import list_last_brokerage_events_for_accounts
from app.crud.holding_crud import list_holdings
from app.crud.capital_gain_crud import sum_capital_gains_for_wallet_year
from app.crud.real_estate_crud import list_real_estates
from app.crud.metal_holding_crud import list_metal_holdings_by_wallet
from app.crud.debt_crud import list_debts
from app.crud.recurring_expenses_crud import list_top_recurring_expenses
from app.crud.year_goal_crud import get_year_goal
from app.utils.utils import TROY_OUNCE_G
from app.core.config import settings


logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/sync/user", response_model=WalletUserResponse)
async def sync_user_route(
    data: UserCreate, 
    session: AsyncSession = Depends(db.get_session),
    stock_client: StockClient = Depends(get_stock_client),
):
    """
    Create or update a wallet user and return their wallets, accounts and banks.

    Flow:
        1. Call `sync_user` to create or update the user based on provided data.
        2. Fetch the user's wallets, banks, and per-wallet accounts & brokerage accounts.
        3. Build and return a `WalletUserResponse` containing:
           - user_id / first_name
           - list of banks
           - list of wallets with their accounts and last transactions.

    Args:
        data: User creation/sync payload (typically contains external identifiers and basic profile data).
        session: Async SQLAlchemy session injected via dependency.

    Raises:
        HTTPException(400): If `sync_user` raises a ValueError (e.g. invalid input).

    Returns:
        WalletUserResponse: Aggregated user, wallets, accounts and banks data.
    """
    try:
        user = await sync_user(session, data)
    except ValueError as e:
        logger.warning(f"sync_user_route: sync_user failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    
    wallets = await list_wallets(session, user_id=user.id)
    banks = await list_banks(session)
    
    user_wallets = WalletUserResponse(
        user_id=str(user.id), 
        first_name=user.first_name,
        banks=banks)
    
    current_year = datetime.now(timezone.utc).year
    
    if wallets:  
        for wallet in wallets:
            wallet_list_item = WalletListItem(id=wallet.id, name=wallet.name)
            accounts = await list_deposit_accounts(session=session, wallet_id=wallet.id, with_relations=True)
            if accounts:
                for account in accounts:
                    account_list_item = AccountListItem(
                        id=account.id,
                        name=account.name,
                        bank_id=account.bank_id,
                        account_type=account.account_type,
                        currency=account.currency,
                        available=account.balance.available,
                        blocked=account.balance.blocked
                    )
                    account_list_item.last_transactions = await get_last_transactions_for_account(
                        session=session,
                        account_id=account.id,
                        limit=5,
                    )
                 
                    wallet_list_item.accounts.append(account_list_item)
                    
            brokerage_accounts = await list_brokerage_accounts(
                session=session,
                wallet_id=wallet.id,
            )
            
            wallet_brokerage_account_ids: List[uuid.UUID] = []
            wallet_holdings: List[Holding] = []
            wallet_quotes_map: Dict[str, "QuoteBySymbolItem"] = {}

            if brokerage_accounts:
                for b in brokerage_accounts:
                    wallet_brokerage_account_ids.append(b.id)

                    holdings = await list_holdings(
                        session=session,
                        account_id=b.id,
                        min_quantity=0.0,
                        limit=10_000,
                        offset=0,
                        with_relations=True,
                    )
                    wallet_holdings.extend(holdings)

                    if not holdings:
                        
                        b_item = BrokerageAccountListItem(
                            id=b.id,
                            name=b.name,
                            totals_by_currency={},
                        )
                        wallet_list_item.brokerage_accounts.append(b_item)
                        continue

                    symbols_for_account = list(
                        {
                            h.instrument.symbol
                            for h in holdings
                            if h.instrument is not None
                        }
                    )

                    quotes_map_for_account = await stock_client.get_latest_quotes_for_symbols(
                        symbols_for_account
                    )

                    for sym, q in quotes_map_for_account.items():
                        wallet_quotes_map[sym] = q

                    totals_by_currency = await compute_brokerage_account_value_by_currency_from_quotes(
                        session=session,
                        holdings=holdings,
                        quotes_map=quotes_map_for_account,
                        auto_fix_currency=True,
                        commit_changes=True,
                    )
                    
                    b_item = BrokerageAccountListItem(
                        id=b.id,
                        name=b.name,
                        totals_by_currency=totals_by_currency,
                    )

                    wallet_list_item.brokerage_accounts.append(b_item)
                    
            current_year = datetime.now(timezone.utc).year
            rows = await sum_capital_gains_for_wallet_year(
                session=session,
                wallet_id=wallet.id,
                year=current_year,
            )

            deposit_map: Dict[Currency, Decimal] = {}
            broker_map: Dict[Currency, Decimal] = {}
            real_estate_map: Dict[Currency, Decimal] = {}
            metal_map: Dict[Currency, Decimal] = {}
            
            for kind, currency, total in rows:
                total_dec = total or Decimal("0")

                if kind == CapitalGainKind.DEPOSIT_INTEREST:
                    deposit_map[currency] = deposit_map.get(currency, Decimal("0")) + total_dec
                elif kind == CapitalGainKind.BROKER_DIVIDEND or kind == CapitalGainKind.BROKER_REALIZED_PNL:
                    broker_map[currency] = broker_map.get(currency, Decimal("0")) + total_dec
                elif kind == CapitalGainKind.REAL_ESTATE_REALIZED_PNL:
                    real_estate_map[currency] = broker_map.get(currency, Decimal("0")) + total_dec
                elif kind == CapitalGainKind.METAL_REALIZED_PNL:
                    metal_map[currency] = broker_map.get(currency, Decimal("0")) + total_dec
                else:
                    continue

            wallet_list_item.capital_gains_deposit_ytd = deposit_map
            wallet_list_item.capital_gains_broker_ytd = broker_map
            wallet_list_item.capital_gains_real_estate_ytd = real_estate_map
            wallet_list_item.capital_gains_metal_ytd = metal_map
                    
            if wallet_brokerage_account_ids:
                events = await list_last_brokerage_events_for_accounts(
                    session=session,
                    account_ids=wallet_brokerage_account_ids,
                    limit=5,
                )

                for ev, inst, acc in events:
                    value = None
                    try:
                        value = ev.quantity * ev.price
                    except Exception:
                        value = None

                    wallet_list_item.last_brokerage_events.append(
                        BrokerageEventListItem(
                            date=ev.trade_at,
                            sym=inst.symbol,
                            type=ev.kind,
                            qty=ev.quantity,
                            price=ev.price,
                            value=value,
                            ccy=ev.currency,
                            account=acc.name,
                        )
                    )

            if wallet_holdings and wallet_quotes_map:
                top_losers, top_gainers = compute_top_n_performance_from_quotes(
                    holdings=wallet_holdings,
                    quotes_map=wallet_quotes_map,
                    n=settings.TOP_N_PERFORMANCE,
                )
                wallet_list_item.top_losers = top_losers
                wallet_list_item.top_gainers = top_gainers
                
            re_rows = await list_real_estates(session, wallet.id)
            mh_rows = await list_metal_holdings_by_wallet(session, wallet.id)
            
            real_estate_items: list[RealEstateItem] = []
            
            for re in re_rows:
                latest = await get_latest_price_with_fallback(
                    session=session,
                    type=re.type,
                    country=re.country,
                    city=re.city,
                    currency=re.purchase_currency,
                )

                real_estate_items.append(
                    RealEstateItem(
                        id=re.id,
                        name=re.name,
                        country=re.country,
                        city=re.city,
                        type=re.type,
                        area_m2=re.area_m2,
                        purchase_price=re.purchase_price,
                        purchase_currency=re.purchase_currency,
                        price=latest.avg_price_per_m2 if latest else None
                        )
                )
            
            wallet_list_item.real_estates = real_estate_items
            
            symbols = [mh.quote_symbol for mh in mh_rows if mh.quote_symbol]
            quotes = await stock_client.get_latest_quotes_for_symbols(list(dict.fromkeys(symbols)))
            
            metal_items: list[MetalHoldingItem] = []
            for mh in mh_rows:
                q = quotes.get(mh.quote_symbol) if mh.quote_symbol else None
                
                price_per_gram: Decimal | None = None
                price_ccy: Currency | None = None

                if q and q.price is not None:
                    last_price = Decimal(str(q.price))
                    price_per_gram = (last_price / TROY_OUNCE_G)
                    price_ccy = getattr(q, "currency", None) or Currency.USD

                metal_items.append(
                    MetalHoldingItem(
                        id=mh.id,
                        metal=mh.metal,
                        grams=mh.grams,
                        cost_basis=mh.cost_basis,
                        cost_currency=mh.cost_currency,
                        price=price_per_gram,
                        price_currency=price_ccy,
                    )
                )
                
                wallet_list_item.metal_holdings = metal_items
                
            d_rows = await list_debts(session, wallet_id=wallet.id)  
            wallet_list_item.debts = [
                DebtItem(
                    id=d.id,
                    wallet_id=d.wallet_id,
                    name=d.name,
                    lander=d.lander,
                    amount=d.amount,
                    currency=d.currency,
                    interest_rate_pct=d.interest_rate_pct,
                    monthly_payment=d.monthly_payment,
                    end_date=d.end_date,
                )
                for d in d_rows
            ]
            
            top_exp = await list_top_recurring_expenses(session=session, wallet_id=wallet.id, limit=5)

            wallet_list_item.recurring_expenses_top = [
                RecurringExpenseItem(
                    id=e.id,
                    name=e.name,
                    category=e.category,
                    amount=e.amount,
                    currency=e.currency,
                    due_day=e.due_day,
                    account=e.account,
                    note=e.note,
                )
                for e in top_exp
            ]
            
            income_map, expense_map = await compute_wallet_ytd_income_expense_maps(
                session=session,
                wallet_id=wallet.id,
                year=current_year,
            )

            wallet_list_item.income_ytd_by_currency = income_map
            wallet_list_item.expense_ytd_by_currency = expense_map
            
            obj = await get_year_goal(session, wallet_id=wallet.id, year=current_year)
            wallet_list_item.year_goal = YearGoalRead.model_validate(obj) if obj else None
                
            user_wallets.wallets.append(wallet_list_item)
            
            flows = await dash_flow_8m(session, wallet)
            
            wallet_list_item.dash_flow_8m = flows
            
    logger.info(f"user_wallets finnal: {user_wallets}")
            
    return user_wallets
   
    
@router.post('/create/wallet', response_model=WalletResponse)
async def create_user_wallet(
    payload: WalletCreateWithoutUser,
    user_id: uuid.UUID = Depends(get_internal_user_id),
    session: AsyncSession = Depends(db.get_session),
) -> WalletResponse:
    """
    Create a new wallet for the authenticated user.

    Flow:
        1. Resolve the internal `user_id` and verify the user exists.
        2. Merge `payload` with `user_id` into a full `WalletCreate`.
        3. Call `create_wallet_service` to persist and return the wallet.

    Args:
        payload: Wallet data without the `user_id` field.
        user_id: Internal user ID resolved from the request (dependency).
        session: Async SQLAlchemy session (dependency).

    Raises:
        HTTPException(400): If user does not exist or wallet service raises ValueError.

    Returns:
        WalletResponse: The created wallet.
    """
    user = await get_user(session, user_id)
    if not user:
        logger.warning(
            "create_user_wallet: unknown user_id, rejecting request"
        )
        raise HTTPException(status_code=400, detail='Unknown user_id')

    data = WalletCreate(**payload.model_dump(), user_id=user.id)
    try:
        wallet = await create_wallet_service(session, data)
        return wallet
    except ValueError as e:
        logger.warning(
            f"create_user_wallet: failed to create wallet for user_id: {e}"
        )
        raise HTTPException(status_code=400, detail=str(e))
    
    
@router.delete('/delete/{wallet_id}', status_code=status.HTTP_204_NO_CONTENT)
async def delete_user_wallet(
    wallet_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_internal_user_id),
    session: AsyncSession = Depends(db.get_session),
):
    """
    Delete a user's wallet by ID.

    Flow:
        1. Validate that `user_id` exists.
        2. Call `delete_wallet_service` with the wallet_id and user_id.
        3. If the wallet is not found / not deletable, return 404.

    Args:
        wallet_id: ID of the wallet to delete.
        user_id: Internal user ID resolved from the request (dependency).
        session: Async SQLAlchemy session (dependency).

    Raises:
        HTTPException(400): If the user does not exist.
        HTTPException(404): If the wallet is not found or cannot be deleted.

    Returns:
        None. (HTTP 204 No Content on success.)
    """
    user = await get_user(session, user_id)
    if not user:
        raise HTTPException(status_code=400, detail='Unknown user_id')

    ok = await delete_wallet_service(session, wallet_id=wallet_id, user_id=user.id)
    if not ok:
        raise HTTPException(status_code=404, detail="Wallet not found")
    
    

