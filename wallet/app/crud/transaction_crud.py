from __future__ import annotations
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional, List

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Transaction
from app.schamas.schemas import (
    TransactionCreate,
    TransactionUpdate,
)
from app.models.enums import TransactionType


async def create_transaction(session: AsyncSession, data: TransactionCreate) -> Transaction:
    tx = Transaction(**data.model_dump())  
    session.add(tx)
    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        raise ValueError("Could not create transaction (invalid account or constraints).") from e
    await session.refresh(tx)
    return tx


async def get_transaction(session: AsyncSession, tx_id: uuid.UUID) -> Optional[Transaction]:
    return await session.get(Transaction, tx_id)


async def get_transaction_with_account(session: AsyncSession, tx_id: uuid.UUID) -> Optional[Transaction]:
    stmt = (
        select(Transaction)
        .options(selectinload(Transaction.account))
        .where(Transaction.id == tx_id)
    )
    result = await session.exec(stmt)
    return result.first()


async def list_transactions(
    session: AsyncSession,
    *,
    account_id: Optional[uuid.UUID] = None,
    types: Optional[List[TransactionType]] = None,
    created_from: Optional[datetime] = None,
    created_to: Optional[datetime] = None,
    min_amount: Optional[Decimal] = None,
    max_amount: Optional[Decimal] = None,
    search: Optional[str] = None,       
    limit: int = 50,
    offset: int = 0,
    newest_first: bool = True,
    with_account: bool = False,
) -> List[Transaction]:
    stmt = select(Transaction)

    if account_id:
        stmt = stmt.where(Transaction.account_id == account_id)
    if types:
        stmt = stmt.where(Transaction.type.in_(types))
    if created_from:
        stmt = stmt.where(Transaction.created_at >= created_from)
    if created_to:
        stmt = stmt.where(Transaction.created_at < created_to)
    if min_amount is not None:
        stmt = stmt.where(Transaction.amount >= min_amount)
    if max_amount is not None:
        stmt = stmt.where(Transaction.amount <= max_amount)
    if search:
        like = f"%{search}%"
        stmt = stmt.where(Transaction.description.ilike(like))

    if with_account:
        stmt = stmt.options(selectinload(Transaction.account))

    stmt = stmt.order_by(
        Transaction.created_at.desc() if newest_first else Transaction.created_at.asc()
    ).offset(offset).limit(limit)

    result = await session.exec(stmt)
    return result.all()


async def update_transaction(
    session: AsyncSession,
    tx_id: uuid.UUID,
    data: TransactionUpdate,
) -> Optional[Transaction]:
    tx = await session.get(Transaction, tx_id)
    if not tx:
        return None

    changes = data.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(tx, field, value) 

    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        raise ValueError("Transaction update violates constraints.") from e

    await session.refresh(tx)
    return tx


async def delete_transaction(session: AsyncSession, tx_id: uuid.UUID) -> bool:
    tx = await session.get(Transaction, tx_id)
    if not tx:
        return False
    session.delete(tx)
    await session.commit()
    return True
