from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
import logging
import uuid

from app.schamas.schemas import (
    UserCreate, WalletCreate, WalletCreateWithoutUser
    )
from app.schamas.response import (
    WalletUserResponse, WalletResponse, WalletListItem, AccountListItem, BrokerageAccountListItem
    )
from app.api.services.user import sync_user
from app.api.services.wallet import create_wallet_service, delete_wallet_service
from app.db.session import db
from app.api.deps import get_internal_user_id
from app.crud.wallet_crud import list_wallets
from app.crud.user_crud import get_user
from app.crud.bank_crud import list_banks
from app.crud.deposit_account_crud import list_deposit_accounts
from app.crud.transaction_crud import get_last_transactions_for_account
from app.crud.brokerage_account_crud import list_brokerage_accounts


logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/sync/user", response_model=WalletUserResponse)
async def sync_user_route(data: UserCreate, session: AsyncSession = Depends(db.get_session)):
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

            if brokerage_accounts:
                for b in brokerage_accounts:
                    b_item = BrokerageAccountListItem(
                        id=b.id,
                        name=b.name,
                    )
                    wallet_list_item.brokerage_accounts.append(b_item)
            user_wallets.wallets.append(wallet_list_item)
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
    
    

