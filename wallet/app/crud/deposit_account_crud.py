from __future__ import annotations
import uuid
from typing import Optional, List

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from sqlmodel import select, or_, cast, String
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import DepositAccount, BrokerageDepositLink
from app.models.enums import Currency
from app.schamas.schemas import (
    DepositAccountCreate,
    DepositAccountUpdate,
)


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
    result = await session.execute(stmt)
    return result.first()


async def get_deposit_by_fingerprint(session: AsyncSession, fp: bytes) -> Optional[DepositAccount]:
    stmt = select(DepositAccount).where(DepositAccount.account_number_fp == fp)
    return (await session.execute(stmt)).first()


async def get_deposit_by_wallet_and_name(
    session: AsyncSession, wallet_id: uuid.UUID, name: str
) -> Optional[DepositAccount]:
    stmt = select(DepositAccount).where(
        (DepositAccount.wallet_id == wallet_id) & (DepositAccount.name == name)
    )
    return (await session.execute(stmt)).first()


async def list_deposit_accounts(
    session: AsyncSession,
    *,
    wallet_id: Optional[uuid.UUID] = None,
    search: Optional[str] = None,  
    limit: int = 50,
    offset: int = 0,
    with_relations: bool = False,
) -> List[DepositAccount]:
    stmt = select(DepositAccount)
    if wallet_id:
        stmt = stmt.where(DepositAccount.wallet_id == wallet_id)
        
    if search:
        q = (search or "").strip()
        like = f"%{q}%"
        conditions = [
            DepositAccount.name.ilike(like),
            cast(DepositAccount.account_type, String).ilike(like),
        ]
        try:
            as_uuid = uuid.UUID(q)
            conditions.append(DepositAccount.bank_id == as_uuid)
        except (ValueError, AttributeError):
            join_bank = True

        if join_bank:
            from app.models.models import Bank
            stmt = stmt.join(Bank, Bank.id == DepositAccount.bank_id)
            conditions.extend([
                cast(Bank.name, String).ilike(like),
                cast(Bank.shortname, String).ilike(like),
            ])

        stmt = stmt.where(or_(*conditions))
    if with_relations:
        stmt = stmt.options(
            selectinload(DepositAccount.bank),
            selectinload(DepositAccount.wallet),
            selectinload(DepositAccount.balance),
        )

    stmt = stmt.order_by(DepositAccount.created_at.desc()).offset(offset).limit(limit)
    result = await session.execute(stmt)
    return result.scalars().all() 


async def list_deposit_accounts_for_wallets(
    session: AsyncSession,
    wallet_ids: list[uuid.UUID],
) -> list[DepositAccount]:
    stmt = (
        select(DepositAccount)
        .where(DepositAccount.wallet_id.in_(wallet_ids))
        .options(
            selectinload(DepositAccount.balance),
            selectinload(DepositAccount.bank),
        )
        .order_by(DepositAccount.created_at.desc())
    )
    res = await session.execute(stmt)
    return res.scalars().all()


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


async def resolve_deposit_for_event(
    session: AsyncSession,
    brokerage_account_id: uuid.UUID,
    currency: Currency,
) -> DepositAccount | None:

    stmt = (
        select(DepositAccount)
        .join(
            BrokerageDepositLink,
            BrokerageDepositLink.deposit_account_id == DepositAccount.id,
        )
        .where(
            BrokerageDepositLink.brokerage_account_id == brokerage_account_id,
            BrokerageDepositLink.currency == currency,
        )
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()
