from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
import logging
import uuid

from app.schamas.schemas import (
    UserCreate, WalletCreate, WalletCreateWithoutUser
    )
from app.schamas.response import (
    WalletUserResponse, WalletResponse, WalletListItem, AccountListItem
    )
from app.api.services.user import sync_user
from app.api.services.wallet import create_wallet_service, delete_wallet_service
from app.db.session import db
from app.api.deps import get_internal_user_id
from app.crud.wallet_crud import list_wallets
from app.crud.user_crud import get_user
from app.crud.bank_crud import list_banks
from app.crud.deposit_account_crud import list_deposit_accounts


logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/sync/user", response_model=WalletUserResponse)
async def sync_user_route(data: UserCreate, session: AsyncSession = Depends(db.get_session)):
    
    logger.info("sync_user_route")
    try:
        user = await sync_user(session, data)
    except ValueError as e:
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
            logger.info(f"accounts: {accounts}")
            if accounts:
                for account in accounts:
                    account_list_item = AccountListItem(
                        id=account.id,
                        name=account.name,
                        account_type=account.account_type,
                        currency=account.currency,
                        available=account.balance.available,
                        blocked=account.balance.blocked
                    )
                    wallet_list_item.accounts.append(account_list_item)
            user_wallets.wallets.append(wallet_list_item)
    return user_wallets
   
    
@router.post('/create/wallet', response_model=WalletResponse)
async def create_user_wallet(
    payload: WalletCreateWithoutUser,
    user_id: uuid.UUID = Depends(get_internal_user_id),
    session: AsyncSession = Depends(db.get_session),
):
    user = await get_user(session, user_id)
    if not user:
        raise HTTPException(status_code=400, detail='Unknown user_id')

    data = WalletCreate(**payload.model_dump(), user_id=user.id)
    try:
        wallet = await create_wallet_service(session, data)
        return wallet
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    
@router.delete('/delete/{wallet_id}', status_code=status.HTTP_204_NO_CONTENT)
async def delete_user_wallet(
    wallet_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_internal_user_id),
    session: AsyncSession = Depends(db.get_session),
):
    user = await get_user(session, user_id)
    if not user:
        raise HTTPException(status_code=400, detail='Unknown user_id')

    ok = await delete_wallet_service(session, wallet_id=wallet_id, user_id=user.id)
    if not ok:
        raise HTTPException(status_code=404, detail="Wallet not found")
    
    

