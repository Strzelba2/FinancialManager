from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
import logging
import uuid

from app.crud.wallet_crud import get_wallet
from app.crud.deposit_account_crud import delete_deposit_account, list_accounts_for_user, get_deposit_account_for_user
from app.crud.brokerage_account_crud import delete_brokerage_account
from app.api.services.accounts import (
    create_deposit_account_service,
    create_brokeage_account_service,
    create_brokerage_cash_account_link_service,
)
from app.schemas.response import AccountCreateResponse, AccountOut
from app.schemas.schemas import (
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

    if payload.account_type == AccountType.BROKERAGE:
        seen_currencies = {payload.currency}
        for cash_account in payload.brokerage_cash_accounts or []:
            if cash_account.currency in seen_currencies:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Duplicate brokerage cash currency: {cash_account.currency.value}",
                )
            seen_currencies.add(cash_account.currency)
    
    try:
        account: DepositAccountRead = await create_deposit_account_service(session, payload, user.username, wallet.id, crypto)
    except Exception as e:
        logger.error(f" Serwer got error durring account creation : {e}/{type(e)}")
        if "Deposit account already exists" in str(e):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Account already exists')

        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='Failed to create account')

    if payload.account_type == AccountType.BROKERAGE:
        brokerage_account = None
        extra_account_ids: list[uuid.UUID] = []
        data = BrokerageAccountCreate(
            name=payload.name,
            wallet_id=wallet.id,
            bank_id=account.bank_id
            )
        try:
            brokerage_account = await create_brokeage_account_service(session=session, data=data, deposit_account=account)
            for cash_account in payload.brokerage_cash_accounts or []:
                extra_account = await create_brokerage_cash_account_link_service(
                    session=session,
                    brokerage_account_id=brokerage_account.id,
                    wallet_id=wallet.id,
                    bank_id=account.bank_id,
                    brokerage_name=payload.name,
                    cash_account=cash_account,
                    username=user.username,
                    crypto=crypto,
                )
                extra_account_ids.append(extra_account.id)
        except Exception as e:
            logger.error(f" Serwer got error durring borkerage account creation : {e}")
            for extra_account_id in extra_account_ids:
                await delete_deposit_account(session=session, account_id=extra_account_id)
            if brokerage_account is not None:
                await delete_brokerage_account(session=session, account_id=brokerage_account.id)
            await delete_deposit_account(session=session, account_id=account.id)
            if isinstance(e, HTTPException):
                raise e
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


@router.delete("/account/{deposit_account_id}")
async def api_delete_deposit_account(
    deposit_account_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_internal_user_id),
    session: AsyncSession = Depends(db.get_session),
):
    user = await get_user(session, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Unknown user_id')
    
    account = get_deposit_account_for_user(session=session, user_id=user_id, deposit_account_id=deposit_account_id)
    
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Account not found')
    
    ok = await delete_deposit_account(session=session, account_id=deposit_account_id)
 
    if not ok:
        raise HTTPException(status_code=404, detail="Deposit account not found")
    return {"ok": True}
