from __future__ import annotations
import uuid
from typing import Optional, List

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import BrokerageDepositLink
from app.schamas.schemas import (
    BrokerageDepositLinkCreate,
    BrokerageDepositLinkUpdate,
)
from app.models.enums import Currency  


async def create_brokerage_deposit_link(
    session: AsyncSession, data: BrokerageDepositLinkCreate
) -> BrokerageDepositLink:
    link = BrokerageDepositLink(**data.model_dump())
    session.add(link)
    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        raise ValueError("Link already exists or currency already mapped for this brokerage account.") from e
    await session.refresh(link)
    return link


async def get_brokerage_deposit_link(
    session: AsyncSession,
    brokerage_account_id: uuid.UUID,
    deposit_account_id: uuid.UUID,
) -> Optional[BrokerageDepositLink]:
    stmt = select(BrokerageDepositLink).where(
        (BrokerageDepositLink.brokerage_account_id == brokerage_account_id)
        & (BrokerageDepositLink.deposit_account_id == deposit_account_id)
    )
    return (await session.execute(stmt)).first()


async def get_link_by_ba_and_currency(
    session: AsyncSession,
    brokerage_account_id: uuid.UUID,
    currency: Currency,
) -> Optional[BrokerageDepositLink]:
    stmt = select(BrokerageDepositLink).where(
        (BrokerageDepositLink.brokerage_account_id == brokerage_account_id)
        & (BrokerageDepositLink.currency == currency)
    )
    return (await session.execute(stmt)).first()


async def get_link_with_relations(
    session: AsyncSession,
    brokerage_account_id: uuid.UUID,
    deposit_account_id: uuid.UUID,
) -> Optional[BrokerageDepositLink]:
    stmt = (
        select(BrokerageDepositLink)
        .options(
            selectinload(BrokerageDepositLink.brokerage_account),
            selectinload(BrokerageDepositLink.deposit_account),
        )
        .where(
            (BrokerageDepositLink.brokerage_account_id == brokerage_account_id)
            & (BrokerageDepositLink.deposit_account_id == deposit_account_id)
        )
    )
    return (await session.execute(stmt)).first()


async def list_brokerage_deposit_links(
    session: AsyncSession,
    brokerage_account_id: Optional[uuid.UUID] = None,
    deposit_account_id: Optional[uuid.UUID] = None,
    currency: Optional[Currency] = None,
    limit: int = 50,
    offset: int = 0,
    with_relations: bool = False,
) -> List[BrokerageDepositLink]:
    stmt = select(BrokerageDepositLink)
    if brokerage_account_id:
        stmt = stmt.where(BrokerageDepositLink.brokerage_account_id == brokerage_account_id)
    if deposit_account_id:
        stmt = stmt.where(BrokerageDepositLink.deposit_account_id == deposit_account_id)
    if currency:
        stmt = stmt.where(BrokerageDepositLink.currency == currency)

    if with_relations:
        stmt = stmt.options(
            selectinload(BrokerageDepositLink.brokerage_account),
            selectinload(BrokerageDepositLink.deposit_account),
        )

    stmt = stmt.offset(offset).limit(limit)
    result = await session.execute(stmt)
    return result.all()


async def update_brokerage_deposit_link(
    session: AsyncSession,
    brokerage_account_id: uuid.UUID,
    deposit_account_id: uuid.UUID,
    data: BrokerageDepositLinkUpdate,
) -> Optional[BrokerageDepositLink]:
    link = await get_brokerage_deposit_link(session, brokerage_account_id, deposit_account_id)
    if not link:
        return None

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(link, field, value)

    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        raise ValueError("Update violates uniqueness (currency per brokerage or link already exists).") from e

    await session.refresh(link)
    return link


async def delete_brokerage_deposit_link(
    session: AsyncSession,
    brokerage_account_id: uuid.UUID,
    deposit_account_id: uuid.UUID,
) -> bool:
    link = await get_brokerage_deposit_link(session, brokerage_account_id, deposit_account_id)
    if not link:
        return False
    session.delete(link)
    await session.commit()
    return True
