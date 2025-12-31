from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
import logging
import uuid

from app.crud.wallet_crud import get_wallet
from app.crud.deposit_account_crud import delete_deposit_account, list_accounts_for_user
from app.api.services.accounts import create_deposit_account_service, create_brokeage_account_service
from app.schamas.response import AccountCreateResponse, AccountOut
from app.schamas.schemas import (
    AccountCreation, DepositAccountRead, AccountType, BrokerageAccountCreate
)
from app.api.deps import get_internal_user_id, get_auth_crypto
from app.db.session import db
from app.crud.user_crud import get_user
from app.clients.auth_client import AuthCryptoClient

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/{wallet_id}/account/create", response_model=AccountCreateResponse, status_code=201)
async def create_account(
    wallet_id: uuid.UUID,
    payload: AccountCreation,
    user_id: uuid.UUID = Depends(get_internal_user_id),
    session: AsyncSession = Depends(db.get_session),
    crypto: AuthCryptoClient = Depends(get_auth_crypto), 
):
    user = await get_user(session, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Unknown user_id')

    wallet = await get_wallet(session, wallet_id)
    if not wallet or wallet.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Wallet not found")
    
    try:
        account: DepositAccountRead = await create_deposit_account_service(session, payload, user.username, wallet.id, crypto)
    except Exception as e:
        logger.error(f" Serwer got error durring account creation : {e}/{type(e)}")
        if "Deposit account already exists" in str(e):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Account already exists')

        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='Failed to create account')

    if payload.account_type == AccountType.BROKERAGE:
        data = BrokerageAccountCreate(
            name=payload.name,
            wallet_id=wallet.id,
            bank_id=account.bank_id
            )
        try:
            await create_brokeage_account_service(session=session, data=data, deposit_account=account)
        except Exception as e:
            logger.error(f" Serwer got error durring borkerage account creation : {e}")
            await delete_deposit_account(session=session, account_id=account.id)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='Failed to create borkerage account')
  
    return AccountCreateResponse(
        id=account.id,
        name=account.name,
        account_type=account.account_type
    )
  
    
@router.get("/accounts", response_model=list[AccountOut])
async def get_accounts(
    user_id: uuid.UUID = Depends(get_internal_user_id),
    session: AsyncSession = Depends(db.get_session),
) -> list[AccountOut]:
    logger.info("get_accounts")
    accounts = await list_accounts_for_user(session=session, user_id=user_id)
    
    return [AccountOut(id=a.id, name=a.name, currency=a.currency) for a in accounts]
