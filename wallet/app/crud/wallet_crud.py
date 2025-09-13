from __future__ import annotations
import uuid
from typing import Optional, List

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Wallet
from app.schamas.schemas import WalletCreate, WalletUpdate


async def create_wallet(session: AsyncSession, data: WalletCreate) -> Wallet:
    """
    Creates a wallet for a given user. Enforces DB uniqueness (user_id, name).
    """
    obj = Wallet(**data.model_dump())
    session.add(obj)
    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        raise ValueError("Wallet with this name already exists for this user, or user_id is invalid.") from e
    await session.refresh(obj)
    return obj


async def get_wallet(session: AsyncSession, wallet_id: uuid.UUID) -> Optional[Wallet]:
    return await session.get(Wallet, wallet_id)


async def get_wallet_with_relations(session: AsyncSession, wallet_id: uuid.UUID) -> Optional[Wallet]:
    stmt = (
        select(Wallet)
        .options(
            selectinload(Wallet.deposit_accounts),
            selectinload(Wallet.brokerage_accounts),
            selectinload(Wallet.real_estates),
            selectinload(Wallet.metal_holdings),
        )
        .where(Wallet.id == wallet_id)
    )
    result = await session.exec(stmt)
    return result.first()


async def get_wallet_by_user_and_name(
    session: AsyncSession, user_id: uuid.UUID, name: str
) -> Optional[Wallet]:
    stmt = select(Wallet).where((Wallet.user_id == user_id) & (Wallet.name == name))
    return (await session.exec(stmt)).first()


async def list_wallets(
    session: AsyncSession,
    *,
    user_id: Optional[uuid.UUID] = None,
    search: Optional[str] = None,  
    limit: int = 50,
    offset: int = 0,
    with_relations: bool = False,
    newest_first: bool = True,
) -> List[Wallet]:
    stmt = select(Wallet)

    if user_id:
        stmt = stmt.where(Wallet.user_id == user_id)
    if search:
        like = f"%{search}%"
        stmt = stmt.where(Wallet.name.ilike(like))

    if with_relations:
        stmt = stmt.options(
            selectinload(Wallet.deposit_accounts),
            selectinload(Wallet.brokerage_accounts),
            selectinload(Wallet.real_estates),
            selectinload(Wallet.metal_holdings),
        )

    stmt = stmt.order_by(
        Wallet.created_at.desc() if newest_first else Wallet.created_at.asc()
    ).offset(offset).limit(limit)

    result = await session.exec(stmt)
    return result.all()


async def update_wallet(
    session: AsyncSession,
    wallet_id: uuid.UUID,
    data: WalletUpdate,
) -> Optional[Wallet]:
    obj = await session.get(Wallet, wallet_id)
    if not obj:
        return None

    changes = data.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(obj, field, value)  

    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        raise ValueError("Wallet update violates uniqueness (name already used by this user).") from e

    await session.refresh(obj)
    return obj


async def delete_wallet(session: AsyncSession, wallet_id: uuid.UUID) -> bool:
    obj = await session.get(Wallet, wallet_id)
    if not obj:
        return False
    session.delete(obj) 
    await session.commit()
    return True
