import uuid
from decimal import Decimal
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert

from app.models.models import (
    FxMonthlySnapshot, DepositAccountMonthlySnapshot, BrokerageAccountMonthlySnapshot,
    MetalHoldingMonthlySnapshot, RealEstateMonthlySnapshot
    )
from app.models.enums import Currency
from app.utils.utils import json_safe


async def list_fx_rows_for_months(session: AsyncSession,  month_keys: list[str]) -> list[FxMonthlySnapshot]:
    if not month_keys:
        return []
    res = await session.execute(select(FxMonthlySnapshot).where(FxMonthlySnapshot.month_key.in_(month_keys)))
    return list(res.scalars().all())


async def list_deposit_monthly_snapshots(
    session: AsyncSession,
    wallet_ids: list[uuid.UUID],
    month_keys: list[str],
) -> list[DepositAccountMonthlySnapshot]:
    if not wallet_ids or not month_keys:
        return []
    stmt = select(DepositAccountMonthlySnapshot).where(
        DepositAccountMonthlySnapshot.wallet_id.in_(wallet_ids),
        DepositAccountMonthlySnapshot.month_key.in_(month_keys),
    )
    res = await session.execute(stmt)
    return list(res.scalars().all())


async def list_brokerage_monthly_snapshots(
    session: AsyncSession,
    wallet_ids: list[uuid.UUID],
    month_keys: list[str],
) -> list[BrokerageAccountMonthlySnapshot]:
    if not wallet_ids or not month_keys:
        return []
    stmt = select(BrokerageAccountMonthlySnapshot).where(
        BrokerageAccountMonthlySnapshot.wallet_id.in_(wallet_ids),
        BrokerageAccountMonthlySnapshot.month_key.in_(month_keys),
    )
    res = await session.execute(stmt)
    return list(res.scalars().all())


async def list_metal_monthly_snapshots(
    session: AsyncSession,
    wallet_ids: list[uuid.UUID],
    month_keys: list[str],
) -> list[MetalHoldingMonthlySnapshot]:
    if not wallet_ids or not month_keys:
        return []
    stmt = select(MetalHoldingMonthlySnapshot).where(
        MetalHoldingMonthlySnapshot.wallet_id.in_(wallet_ids),
        MetalHoldingMonthlySnapshot.month_key.in_(month_keys),
    )
    res = await session.execute(stmt)
    return list(res.scalars().all())


async def list_real_estate_monthly_snapshots(
    session: AsyncSession,
    wallet_ids: list[uuid.UUID],
    month_keys: list[str],
) -> list[RealEstateMonthlySnapshot]:
    if not wallet_ids or not month_keys:
        return []
    stmt = select(RealEstateMonthlySnapshot).where(
        RealEstateMonthlySnapshot.wallet_id.in_(wallet_ids),
        RealEstateMonthlySnapshot.month_key.in_(month_keys),
    )
    res = await session.execute(stmt)
    return list(res.scalars().all())


async def upsert_fx_monthly_snapshot_uow(
    session: AsyncSession,
    month_key: str,
    rates_json: dict,
) -> None:
    safe = json_safe(rates_json)
    stmt = (
        insert(FxMonthlySnapshot)
        .values(month_key=month_key, rates_json=safe)
        .on_conflict_do_update(
            constraint="uq_fx_month_key",
            set_={"rates_json": safe, "updated_at": func.now()},
        )
    )
    await session.execute(stmt)
    
    
async def upsert_depacc_monthly_snapshot_uow(
    session: AsyncSession, 
    wallet_id: uuid.UUID,
    account_id, 
    month_key, 
    currency, 
    available
) -> None:
    stmt = (
        insert(DepositAccountMonthlySnapshot)
        .values(account_id=account_id, 
                wallet_id=wallet_id,
                month_key=month_key, 
                currency=currency, 
                available=available
                )
        .on_conflict_do_update(
            constraint="uq_depacc_monthly_snapshot",
            set_={"currency": currency, "available": available, "updated_at": func.now()},
        )
    )
    await session.execute(stmt)


async def upsert_broacc_monthly_snapshot_uow(
    session: AsyncSession, 
    wallet_id: uuid.UUID,
    brokerage_account_id, 
    month_key, 
    currency, 
    cash, 
    stocks
) -> None:
    stmt = (
        insert(BrokerageAccountMonthlySnapshot)
        .values(
            brokerage_account_id=brokerage_account_id, 
            wallet_id=wallet_id,
            month_key=month_key, 
            currency=currency, 
            cash=cash, 
            stocks=stocks
            )
        .on_conflict_do_update(
            constraint="uq_broacc_monthly_snapshot",
            set_={"currency": currency, "cash": cash, "stocks": stocks, "updated_at": func.now()},
        )
    )
    await session.execute(stmt)
    
    
async def upsert_metal_monthly_snapshot(
    session: AsyncSession,
    wallet_id: uuid.UUID,
    metal_holding_id: uuid.UUID,
    month_key: str,
    currency: Currency,
    value: Decimal,
) -> None:
    stmt = (
        insert(MetalHoldingMonthlySnapshot)
        .values(
            wallet_id=wallet_id,
            metal_holding_id=metal_holding_id,
            month_key=month_key,
            currency=currency,
            value=value,
        )
        .on_conflict_do_update(
            constraint="uq_metal_monthly_snapshot",
            set_={"currency": currency, "value": value, "updated_at": func.now()},
        )
    )
    await session.execute(stmt)


async def upsert_real_estate_monthly_snapshot(
    session: AsyncSession,
    wallet_id: uuid.UUID,
    real_estate_id: uuid.UUID,
    month_key: str,
    currency: Currency,
    value: Decimal,
) -> None:
    stmt = (
        insert(RealEstateMonthlySnapshot)
        .values(
            wallet_id=wallet_id,
            real_estate_id=real_estate_id,
            month_key=month_key,
            currency=currency,
            value=value,
        )
        .on_conflict_do_update(
            constraint="uq_re_monthly_snapshot",
            set_={"currency": currency, "value": value, "updated_at": func.now()},
        )
    )
    await session.execute(stmt)
