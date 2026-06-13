import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status
import logging
import base64

from app.schemas.schemas import (
    AccountCreation, DepositAccountCreate, DepositAccountRead, DepositAccountBalanceCreate,
    BrokerageAccountCreate, BrokerageAccountRead, BrokerageDepositLinkCreate,
    BrokerageCashAccountCreate, AccountType
)
from app.crud.deposit_account_crud import (
    create_deposit_account,
    get_deposit_account,
    get_deposit_account_for_user,
    delete_deposit_account,
)
from app.crud.deposit_account_balance import create_deposit_account_balance
from app.crud.brokerage_account_crud import create_brokerage_account, get_brokerage_account_for_user
from app.crud.brokerage_deposit_link_crud import (
    create_brokerage_deposit_link,
    get_link_by_ba_and_currency,
    list_brokerage_deposit_links,
)
from app.crud.bank_crud import get_bank
from app.clients.auth_client import AuthCryptoClient
from app.utils.utils import b64, b64e, b64d

logger = logging.getLogger(__name__)


async def create_deposit_account_service(
    session: AsyncSession, 
    data: AccountCreation, 
    username: str, 
    wallet_id: uuid.UUID,
    crypto: AuthCryptoClient
) -> DepositAccountRead:
    """
    Creates a new deposit account with encrypted and hashed account number and IBAN.

    Args:
        session (AsyncSession): SQLAlchemy database session.
        data (AccountCreation): Input account creation data.
        username (str): Username used for crypto operations.
        wallet_id (UUID): ID of the wallet to associate the account with.
        crypto (AuthCryptoClient): Crypto client used for encryption and hashing.

    Returns:
        DepositAccountRead: The created deposit account with safe fields.
    """
    logger.info(f"Creating deposit account for user: {username} and wallet: {wallet_id}")

    bank = await get_bank(session, data.bank_id)
    if not bank:
        logger.error("Bank not found")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bank not found")
    
    clean_number = data.account_number.replace(' ', '').upper()
    
    ops = [
        {"id": "acc_h", "kind": "hmac",    "plaintext_b64": b64(clean_number)},
        {"id": "acc_e", "kind": "encrypt", "plaintext_b64": b64(clean_number)},
    ]
    
    if data.iban:
        ops += [
            {"id": "iban_h", "kind": "hmac",    "plaintext_b64": b64(data.iban)},
            {"id": "iban_e", "kind": "encrypt", "plaintext_b64": b64(data.iban)},
        ]
        
    res = await crypto.batch(str(username), ops)
    
    if not res:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Crypto server do not work correctly",
        )
    
    by_id = {r["id"]: r for r in res["results"] if r.get("ok")}

    acc_fp = base64.b64decode(by_id["acc_h"]["digest_b64"])
    acc_nonce = base64.b64decode(by_id["acc_e"]["nonce_b64"])
    acc_ct = base64.b64decode(by_id["acc_e"]["ciphertext_b64"])

    if data.iban:
        iban_fp = base64.b64decode(by_id["iban_h"]["digest_b64"])
        iban_nonce = base64.b64decode(by_id["iban_e"]["nonce_b64"])
        iban_ct = base64.b64decode(by_id["iban_e"]["ciphertext_b64"])
    else:
        iban_fp = iban_nonce = iban_ct = None

    acc = DepositAccountCreate(
        wallet_id=wallet_id,
        bank_id=data.bank_id,
        name=data.name,
        account_type=data.account_type,
        currency=data.currency,
        account_number_nonce=acc_nonce,  
        account_number_fp=acc_fp,
        account_number_ct=acc_ct,
        iban_nonce=iban_nonce,
        iban_ct=iban_ct,
        iban_fp=iban_fp
    )

    account = await create_deposit_account(session, acc)
    
    data = DepositAccountBalanceCreate(account_id=account.id)

    try:
        await create_deposit_account_balance(session, data)
    except Exception as e:
        logger.exception("Failed to create balance, rolling back account creation")
        await delete_deposit_account(session, account.id)
        raise e
    
    return DepositAccountRead.model_validate(account, from_attributes=True)


async def create_brokeage_account_service(
    session: AsyncSession, 
    data: BrokerageAccountCreate,
    deposit_account: DepositAccountRead
) -> BrokerageAccountRead:
    """
    Creates a brokerage account and links it to a deposit account.

    Args:
        session (AsyncSession): SQLAlchemy session.
        data (BrokerageAccountCreate): Data for creating brokerage account.
        deposit_account (DepositAccountRead): Linked deposit account.

    Returns:
        BrokerageAccountRead: Created brokerage account.
    """
    logger.info(f"Creating brokerage account linked to deposit account: {deposit_account.id}")
    brokerage_account = await create_brokerage_account(session=session, data=data)
    
    brokerage_link = BrokerageDepositLinkCreate(
        currency=deposit_account.currency,
        deposit_account_id=deposit_account.id,
        brokerage_account_id=brokerage_account.id 
    )
    
    await create_brokerage_deposit_link(session=session, data=brokerage_link)
    
    return BrokerageAccountRead.model_validate(brokerage_account, from_attributes=True)


async def create_brokerage_cash_account_link_service(
    session: AsyncSession,
    brokerage_account_id: uuid.UUID,
    wallet_id: uuid.UUID,
    bank_id: uuid.UUID,
    brokerage_name: str,
    cash_account: BrokerageCashAccountCreate,
    username: str,
    crypto: AuthCryptoClient,
) -> DepositAccountRead:
    """
    Create a brokerage cash sub-account and link it to a brokerage account for one currency.
    """
    account_number = (cash_account.account_number or "").strip()
    if not account_number:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Brokerage cash account number is required.",
        )

    existing_link = await get_link_by_ba_and_currency(
        session,
        brokerage_account_id=brokerage_account_id,
        currency=cash_account.currency,
    )
    if existing_link is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Brokerage cash account already linked for {cash_account.currency.value}.",
        )

    account_payload = AccountCreation(
        name=cash_account.name or f"{brokerage_name} · Cash {cash_account.currency.value}",
        account_type=AccountType.BROKERAGE,
        currency=cash_account.currency,
        account_number=account_number,
        bank_id=bank_id,
        iban=cash_account.iban,
    )
    account = await create_deposit_account_service(
        session=session,
        data=account_payload,
        username=username,
        wallet_id=wallet_id,
        crypto=crypto,
    )
    link_payload = BrokerageDepositLinkCreate(
        currency=cash_account.currency,
        deposit_account_id=account.id,
        brokerage_account_id=brokerage_account_id,
    )
    await create_brokerage_deposit_link(session=session, data=link_payload)
    return account


async def delete_brokerage_account_with_cash_accounts_service(
    session: AsyncSession,
    user_id: uuid.UUID,
    brokerage_account_id: uuid.UUID,
) -> bool:
    """
    Delete a brokerage account and its dedicated brokerage cash deposit accounts.

    Cash accounts are ordinary deposit accounts linked through brokerage_deposit_links.
    A linked deposit account is deleted only when it belongs to the same user, has
    account_type BROKERAGE, and is not linked to another brokerage account.
    """
    brokerage_account = await get_brokerage_account_for_user(
        session=session,
        user_id=user_id,
        brokerage_account_id=brokerage_account_id,
    )
    if brokerage_account is None:
        return False

    links = await list_brokerage_deposit_links(
        session,
        brokerage_account_id=brokerage_account_id,
        limit=None,
    )

    deposit_accounts_to_delete = []
    for link in links:
        sibling_links = await list_brokerage_deposit_links(
            session,
            deposit_account_id=link.deposit_account_id,
            limit=None,
        )
        linked_elsewhere = any(
            sibling.brokerage_account_id != brokerage_account_id
            for sibling in sibling_links
        )
        if linked_elsewhere:
            continue

        deposit_account = await get_deposit_account_for_user(
            session=session,
            user_id=user_id,
            deposit_account_id=link.deposit_account_id,
        )
        if deposit_account is None:
            continue
        if deposit_account.account_type != AccountType.BROKERAGE:
            continue
        deposit_accounts_to_delete.append(deposit_account)

    try:
        for deposit_account in deposit_accounts_to_delete:
            await session.delete(deposit_account)
        await session.delete(brokerage_account)
        await session.commit()
    except Exception:
        await session.rollback()
        raise

    return True


async def get_plain_account_number_service(
    session: AsyncSession,
    account_id: uuid.UUID,
    username: str, 
    crypto: AuthCryptoClient,
) -> str | None:
    """
    Decrypts and returns the plain text account number for a deposit account.

    Args:
        session (AsyncSession): SQLAlchemy session.
        account_id (UUID): The ID of the deposit account.
        username (str): Username for crypto context.
        crypto (AuthCryptoClient): Crypto client.

    Returns:
        Optional[str]: Decrypted account number or None if not found or error.
    """
    logger.info(f"Fetching and decrypting account number for account: {account_id}")
    acc = await get_deposit_account(session, account_id)
    if not acc:
        logger.warning("Deposit account not found")
        return None

    if not acc.account_number_nonce or not acc.account_number_ct:
        logger.warning("Missing encrypted account number data")
        return None

    ops = [{
        "id": "acc_d",
        "kind": "decrypt",
        "nonce_b64": b64e(acc.account_number_nonce),
        "ciphertext_b64": b64e(acc.account_number_ct),
    }]

    res = await crypto.batch(str(username), ops)
    result = next((r for r in res["results"] if r.get("id") == "acc_d"), None)
    if not result or not result.get("ok"):
        return None

    plaintext = b64d(result["plaintext_b64"])
    return plaintext.decode("utf-8", errors="strict")
