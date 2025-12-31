from __future__ import annotations
import uuid
from typing import Optional, List

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Bank
from app.schamas.schemas import BankCreate, BankUpdate


async def create_bank(session: AsyncSession, data: BankCreate) -> Bank:
    bank = Bank(**data.model_dump()) 
    session.add(bank)
    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        raise ValueError("Bank with this name or shortname already exists.") from e
    await session.refresh(bank)
    return bank


async def get_bank(session: AsyncSession, bank_id: uuid.UUID) -> Optional[Bank]:
    return await session.get(Bank, bank_id)


async def get_bank_with_accounts(session: AsyncSession, bank_id: uuid.UUID) -> Optional[Bank]:
    stmt = (
        select(Bank)
        .options(
            selectinload(Bank.accounts),
            selectinload(Bank.brokerage_accounts),
        )
        .where(Bank.id == bank_id)
    )
    result = await session.execute(stmt)
    return result.first()


async def get_bank_by_name(session: AsyncSession, name: str) -> Optional[Bank]:
    result = await session.execute(select(Bank).where(Bank.name == name))
    return result.first()


async def get_bank_by_shortname(session: AsyncSession, shortname: str) -> Optional[Bank]:
    result = await session.execute(select(Bank).where(Bank.shortname == shortname.upper()))
    return result.first()


async def list_banks(
    session: AsyncSession,
    limit: int = 50,
    offset: int = 0,
    search: Optional[str] = None,
    with_accounts: bool = False,
) -> List[Bank]:
    stmt = select(Bank).order_by(Bank.name.asc())
    if search:
        like = f"%{search}%"
        stmt = stmt.where(Bank.name.ilike(like) | Bank.shortname.ilike(like))
    if with_accounts:
        stmt = stmt.options(
            selectinload(Bank.accounts),
            selectinload(Bank.brokerage_accounts),
        )
    stmt = stmt.offset(offset).limit(limit)
    result = await session.execute(stmt)
    return result.scalars().all() 


async def update_bank(session: AsyncSession, bank_id: uuid.UUID, data: BankUpdate) -> Optional[Bank]:
    bank = await session.get(Bank, bank_id)
    if not bank:
        return None

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(bank, field, value)  

    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        raise ValueError("Bank with this name or shortname already exists.") from e

    await session.refresh(bank)
    return bank


async def delete_bank(session: AsyncSession, bank_id: uuid.UUID) -> bool:
    bank = await session.get(Bank, bank_id)
    if not bank:
        return False
    session.delete(bank) 
    await session.commit()
    return True
