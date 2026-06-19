from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.enums import ReportAssetClass
from app.models.models import ReportAiSnapshot, ReportSnapshot


async def get_report_ai_snapshot(
    session: AsyncSession,
    instrument_id: uuid.UUID,
    asset_class: ReportAssetClass,
    period: str,
    schema_version: int,
) -> Optional[ReportAiSnapshot]:
    stmt = (
        select(ReportAiSnapshot)
        .where(
            ReportAiSnapshot.instrument_id == instrument_id,
            ReportAiSnapshot.asset_class == asset_class,
            ReportAiSnapshot.period == period,
            ReportAiSnapshot.schema_version == schema_version,
        )
        .limit(1)
    )
    res = await session.execute(stmt)
    return res.scalar_one_or_none()


async def get_report_snapshot(
    session: AsyncSession,
    instrument_id: uuid.UUID,
    asset_class: ReportAssetClass,
    period: str,
    schema_version: int,
) -> Optional[ReportSnapshot]:
    stmt = (
        select(ReportSnapshot)
        .where(
            ReportSnapshot.instrument_id == instrument_id,
            ReportSnapshot.asset_class == asset_class,
            ReportSnapshot.period == period,
            ReportSnapshot.schema_version == schema_version,
        )
        .limit(1)
    )
    res = await session.execute(stmt)
    return res.scalar_one_or_none()


async def list_report_snapshots(
    session: AsyncSession,
    instrument_id: uuid.UUID,
    asset_class: ReportAssetClass,
    schema_version: int,
) -> list[ReportSnapshot]:
    stmt = (
        select(ReportSnapshot)
        .where(
            ReportSnapshot.instrument_id == instrument_id,
            ReportSnapshot.asset_class == asset_class,
            ReportSnapshot.schema_version == schema_version,
        )
        .order_by(ReportSnapshot.period.desc(), ReportSnapshot.generated_at.desc())
    )
    res = await session.execute(stmt)
    return list(res.scalars().all())


async def get_latest_ready_report_ai_snapshot(
    session: AsyncSession,
    instrument_id: uuid.UUID,
    asset_class: ReportAssetClass,
    schema_version: int,
) -> Optional[ReportAiSnapshot]:
    stmt = (
        select(ReportAiSnapshot)
        .where(
            ReportAiSnapshot.instrument_id == instrument_id,
            ReportAiSnapshot.asset_class == asset_class,
            ReportAiSnapshot.schema_version == schema_version,
            ReportAiSnapshot.status == "ready",
        )
        .order_by(ReportAiSnapshot.generated_at.desc())
        .limit(1)
    )
    res = await session.execute(stmt)
    return res.scalar_one_or_none()


async def upsert_report_ai_snapshot(
    session: AsyncSession,
    instrument_id: uuid.UUID,
    asset_class: ReportAssetClass,
    period: str,
    schema_version: int,
    ai_payload: dict,
    model: str,
    prompt_version: str,
    prompt_hash: str,
    generated_at: datetime,
    valid_until: date,
    usage_prompt_tokens: int | None,
    usage_output_tokens: int | None,
    status: str = "ready",
    last_error: str | None = None,
) -> ReportAiSnapshot:
    row = await get_report_ai_snapshot(
        session=session,
        instrument_id=instrument_id,
        asset_class=asset_class,
        period=period,
        schema_version=schema_version,
    )
    if row is None:
        row = ReportAiSnapshot(
            instrument_id=instrument_id,
            asset_class=asset_class,
            period=period,
            schema_version=schema_version,
            ai_payload=ai_payload,
            model=model,
            prompt_version=prompt_version,
            prompt_hash=prompt_hash,
            generated_at=generated_at,
            valid_until=valid_until,
            usage_prompt_tokens=usage_prompt_tokens,
            usage_output_tokens=usage_output_tokens,
            status=status,
            last_error=last_error,
        )
        session.add(row)
    else:
        row.ai_payload = ai_payload
        row.model = model
        row.prompt_version = prompt_version
        row.prompt_hash = prompt_hash
        row.generated_at = generated_at
        row.valid_until = valid_until
        row.usage_prompt_tokens = usage_prompt_tokens
        row.usage_output_tokens = usage_output_tokens
        row.status = status
        row.last_error = last_error

    await session.flush()
    await session.refresh(row)
    return row


async def mark_report_ai_snapshot_failure(
    session: AsyncSession,
    instrument_id: uuid.UUID,
    asset_class: ReportAssetClass,
    period: str,
    schema_version: int,
    model: str,
    prompt_version: str,
    prompt_hash: str,
    generated_at: datetime,
    valid_until: date,
    error: str,
) -> ReportAiSnapshot:
    existing = await get_report_ai_snapshot(
        session=session,
        instrument_id=instrument_id,
        asset_class=asset_class,
        period=period,
        schema_version=schema_version,
    )

    if existing is None:
        existing = ReportAiSnapshot(
            instrument_id=instrument_id,
            asset_class=asset_class,
            period=period,
            schema_version=schema_version,
            ai_payload={},
            model=model,
            prompt_version=prompt_version,
            prompt_hash=prompt_hash,
            generated_at=generated_at,
            valid_until=valid_until,
            usage_prompt_tokens=None,
            usage_output_tokens=None,
            status="failed",
            last_error=error,
        )
        session.add(existing)
    else:
        if existing.status != "ready":
            existing.model = model
            existing.prompt_version = prompt_version
            existing.prompt_hash = prompt_hash
            existing.generated_at = generated_at
            existing.valid_until = valid_until
            existing.ai_payload = existing.ai_payload or {}
            existing.status = "failed"
        existing.last_error = error

    await session.flush()
    await session.refresh(existing)
    return existing


async def upsert_report_snapshot(
    session: AsyncSession,
    instrument_id: uuid.UUID,
    ai_snapshot_id: uuid.UUID,
    asset_class: ReportAssetClass,
    period: str,
    schema_version: int,
    final_payload: dict,
    market_data_as_of: date,
    generated_at: datetime,
    valid_until: date,
) -> ReportSnapshot:
    row = await get_report_snapshot(
        session=session,
        instrument_id=instrument_id,
        asset_class=asset_class,
        period=period,
        schema_version=schema_version,
    )
    if row is None:
        row = ReportSnapshot(
            instrument_id=instrument_id,
            ai_snapshot_id=ai_snapshot_id,
            asset_class=asset_class,
            period=period,
            schema_version=schema_version,
            final_payload=final_payload,
            market_data_as_of=market_data_as_of,
            generated_at=generated_at,
            valid_until=valid_until,
        )
        session.add(row)
    else:
        row.ai_snapshot_id = ai_snapshot_id
        row.final_payload = final_payload
        row.market_data_as_of = market_data_as_of
        row.generated_at = generated_at
        row.valid_until = valid_until

    await session.flush()
    await session.refresh(row)
    return row
