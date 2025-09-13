from __future__ import annotations
import uuid
from typing import Optional, List

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import DepositAccount
from app.schamas.schemas import (
    DepositAccountCreate,
    DepositAccountUpdate,
)
from app.models.enums import Currency, AccountType


async def create_deposit_account(session: AsyncSession, data: DepositAccountCreate) -> DepositAccount:
    acc = DepositAccount(**data.model_dump()) 
    session.add(acc)
    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        raise ValueError("Deposit account already exists (name per wallet, IBAN, or fingerprint).") from e
    await session.refresh(acc)
    return acc


async def get_deposit_account(session: AsyncSession, account_id: uuid.UUID) -> Optional[DepositAccount]:
    return await session.get(DepositAccount, account_id)


async def get_deposit_account_with_relations(session: AsyncSession, account_id: uuid.UUID) -> Optional[DepositAccount]:
    stmt = (
        select(DepositAccount)
        .options(
            selectinload(DepositAccount.bank),
            selectinload(DepositAccount.wallet),
            selectinload(DepositAccount.balance),
        )
        .where(DepositAccount.id == account_id)
    )
    result = await session.exec(stmt)
    return result.first()


async def get_deposit_by_fingerprint(session: AsyncSession, fp: bytes) -> Optional[DepositAccount]:
    stmt = select(DepositAccount).where(DepositAccount.account_number_fp == fp)
    return (await session.exec(stmt)).first()


async def get_deposit_by_iban(session: AsyncSession, iban: str) -> Optional[DepositAccount]:
    stmt = select(DepositAccount).where(DepositAccount.iban == iban.upper())
    return (await session.exec(stmt)).first()


async def get_deposit_by_wallet_and_name(
    session: AsyncSession, wallet_id: uuid.UUID, name: str
) -> Optional[DepositAccount]:
    stmt = select(DepositAccount).where(
        (DepositAccount.wallet_id == wallet_id) & (DepositAccount.name == name)
    )
    return (await session.exec(stmt)).first()


async def list_deposit_accounts(
    session: AsyncSession,
    *,
    wallet_id: Optional[uuid.UUID] = None,
    bank_id: Optional[uuid.UUID] = None,
    currency: Optional["Currency"] = None,
    account_type: Optional["AccountType"] = None,
    search: Optional[str] = None,  
    limit: int = 50,
    offset: int = 0,
    with_relations: bool = False,
) -> List[DepositAccount]:
    stmt = select(DepositAccount)
    if wallet_id:
        stmt = stmt.where(DepositAccount.wallet_id == wallet_id)
    if bank_id:
        stmt = stmt.where(DepositAccount.bank_id == bank_id)
    if currency:
        stmt = stmt.where(DepositAccount.currency == currency)
    if account_type:
        stmt = stmt.where(DepositAccount.account_type == account_type)
    if search:
        like = f"%{search}%"
        stmt = stmt.where((DepositAccount.name.ilike(like)) | (DepositAccount.iban.ilike(like)))

    if with_relations:
        stmt = stmt.options(
            selectinload(DepositAccount.bank),
            selectinload(DepositAccount.wallet),
            selectinload(DepositAccount.balance),
        )

    stmt = stmt.order_by(DepositAccount.created_at.desc()).offset(offset).limit(limit)
    result = await session.exec(stmt)
    return result.all()


async def update_deposit_account(
    session: AsyncSession,
    account_id: uuid.UUID,
    data: DepositAccountUpdate,
) -> Optional[DepositAccount]:
    acc = await session.get(DepositAccount, account_id)
    if not acc:
        return None

    changes = data.model_dump(exclude_unset=True)

    for field, value in changes.items():
        setattr(acc, field, value) 

    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        raise ValueError("Deposit account update violates uniqueness (name per wallet, IBAN, or fingerprint).") from e

    await session.refresh(acc)
    return acc


async def delete_deposit_account(session: AsyncSession, account_id: uuid.UUID) -> bool:
    acc = await session.get(DepositAccount, account_id)
    if not acc:
        return False
    session.delete(acc)  
    await session.commit()
    return True
