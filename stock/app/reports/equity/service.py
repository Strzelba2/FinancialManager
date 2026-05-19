from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.services.quotes import sync_daily_by_symbol
from app.core.cache.redis import Storage
from app.core.config import settings
from app.crud.candle_daily import get_min_max_date, list_candles_daily
from app.crud.instrument import get_instrument_with_market_by_mic_symbol
from app.crud.quote_latest import get_latest_quote_for_instrument
from app.crud.report_snapshot import (
    get_report_ai_snapshot,
    get_report_snapshot,
    list_report_snapshots,
    mark_report_ai_snapshot_failure,
    upsert_report_ai_snapshot,
    upsert_report_snapshot,
)
from app.models.enums import InstrumentType, ReportAssetClass

from .ai_schema import EquityAiPayload
from .builder import build_equity_report
from .openai_client import OpenAIEquityReportClient, OpenAIReportError
from .prompt import SYSTEM_PROMPT, build_user_prompt, prompt_hash
from .sanitize import sanitize_equity_ai_payload
from .schemas import EquityReport, EquityReportResponse, ReportPeriod
from .web_source import (
    EquityWebSourceClient,
    final_report_payload_needs_enrichment,
    merge_web_source_report_metrics,
    merge_web_source_facts,
    report_payload_needs_enrichment,
)


logger = logging.getLogger(__name__)


TECHNICAL_CANDLE_LOOKBACK_DAYS = 1825


class ReportNotFoundError(LookupError):
    pass


class ReportConflictError(RuntimeError):
    pass


class ReportGenerationError(RuntimeError):
    pass


def last_closed_quarter(today: date) -> str:
    quarter = (today.month - 1) // 3 + 1
    if quarter == 1:
        return f"{today.year - 1}-Q4"
    return f"{today.year}-Q{quarter - 1}"


def normalize_period(requested_period: str | None, today: date) -> str:
    if not requested_period:
        return last_closed_quarter(today)
    raw = requested_period.strip().upper()
    if len(raw) != 7 or raw[4] != "-" or raw[5] != "Q" or raw[6] not in "1234" or not raw[:4].isdigit():
        raise ValueError("Invalid period format. Expected YYYY-QN.")
    return raw


def ai_snapshot_is_fresh(
    ai_snapshot,
    current_period: str,
    requested_period: str,
    today: date,
    current_prompt_hash: str,
) -> bool:
    if ai_snapshot is None:
        return False
    if ai_snapshot.status != "ready":
        return False
    if ai_snapshot.prompt_version != settings.OPENAI_REPORT_PROMPT_VERSION:
        return False
    if ai_snapshot.prompt_hash != current_prompt_hash:
        return False
    if requested_period != current_period:
        return True
    if ai_snapshot.valid_until < today:
        return False
    return True


def needs_candle_refresh(max_candle_date: date | None, latest_trade_date: date) -> bool:
    if max_candle_date is None:
        return True
    return max_candle_date < (latest_trade_date - timedelta(days=5))


def snapshot_is_usable(snapshot, ai_fresh: bool, latest_trade_date: date, candle_latest_date: date | None) -> bool:
    if snapshot is None:
        return False
    if not ai_fresh:
        return False
    return not needs_candle_refresh(candle_latest_date, latest_trade_date)


def should_fetch_web_source_facts(
    ai_payload_sparse: bool,
    final_snapshot_sparse: bool,
    ai_fresh: bool,
) -> bool:
    return ai_payload_sparse or final_snapshot_sparse or not ai_fresh


def should_refresh_ai_for_grounded_narrative(
    ai_fresh: bool,
    ai_payload_sparse: bool,
    web_source_facts,
) -> bool:
    return bool(
        ai_fresh
        and ai_payload_sparse
        and web_source_facts is not None
        and web_source_facts.has_material_data()
    )


def build_ai_cache_prompt_hash(mic: str, symbol: str, period: str) -> str:
    cache_identity = f"equity|{mic.strip().upper()}|{symbol.strip().upper()}|{period}"
    return prompt_hash(
        SYSTEM_PROMPT,
        cache_identity,
        str(settings.REPORT_SCHEMA_VERSION),
        settings.OPENAI_REPORT_PROMPT_VERSION,
    )


def _snapshot_to_report(snapshot) -> EquityReport:
    return EquityReport.model_validate(snapshot.final_payload)


def _available_periods(snapshots: list, current_period: str) -> list[ReportPeriod]:
    periods: list[ReportPeriod] = []
    for snapshot in snapshots:
        periods.append(
            ReportPeriod(
                period=snapshot.period,
                generated_at=snapshot.generated_at.isoformat(timespec="seconds"),
                is_current=snapshot.period == current_period,
            )
        )
    return periods


async def _wait_for_existing_snapshot(
    session: AsyncSession,
    instrument_id,
    asset_class: ReportAssetClass,
    period: str,
    schema_version: int,
    attempts: int = 12,
    delay_s: float = 1.0,
):
    for _ in range(attempts):
        await asyncio.sleep(delay_s)
        snapshot = await get_report_snapshot(
            session=session,
            instrument_id=instrument_id,
            asset_class=asset_class,
            period=period,
            schema_version=schema_version,
        )
        if snapshot is not None:
            return snapshot
    return None


async def _fetch_web_source_facts(
    mic: str,
    symbol: str,
    shortname: str | None,
):
    if not settings.EQUITY_WEB_SOURCE_ENABLED or not settings.EQUITY_WEB_SOURCE_BASE_URL:
        return None

    client = EquityWebSourceClient()
    try:
        return await client.fetch_facts(
            mic=mic,
            symbol=symbol,
            shortname=shortname,
        )
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.warning(
            "Equity web source enrichment failed mic=%s symbol=%s error=%s",
            mic,
            symbol,
            exc,
        )
        return None
    finally:
        await client.aclose()


async def get_equity_report(
    session: AsyncSession,
    storage: Storage,
    mic: str,
    symbol: str,
    period: str | None = None,
    client: Optional[OpenAIEquityReportClient] = None,
) -> EquityReportResponse:
    today = datetime.now(settings.TIME_ZONE).date()
    requested_period = normalize_period(period, today)
    current_period = last_closed_quarter(today)
    schema_version = settings.REPORT_SCHEMA_VERSION
    asset_class = ReportAssetClass.EQUITY

    resolved = await get_instrument_with_market_by_mic_symbol(
        session=session,
        mic=mic.strip().upper(),
        symbol=symbol.strip().upper(),
    )
    if not resolved:
        raise ReportNotFoundError("Instrument not found.")

    instrument, market = resolved
    if instrument.type != InstrumentType.STOCK:
        raise ReportConflictError("Only STOCK instruments are supported by equity reports.")

    if requested_period != current_period:
        snapshot = await get_report_snapshot(
            session=session,
            instrument_id=instrument.id,
            asset_class=asset_class,
            period=requested_period,
            schema_version=schema_version,
        )
        if snapshot is None:
            raise ReportNotFoundError("Archived report snapshot not found.")
        snapshots = await list_report_snapshots(
            session=session,
            instrument_id=instrument.id,
            asset_class=asset_class,
            schema_version=schema_version,
        )
        return EquityReportResponse(
            asset_class="equity",
            report=_snapshot_to_report(snapshot),
            available_periods=_available_periods(snapshots, current_period=current_period),
        )

    quote_latest = await get_latest_quote_for_instrument(session, instrument.id)
    if quote_latest is None:
        raise ReportConflictError("Latest quote is missing for this instrument.")

    latest_trade_date = quote_latest.last_trade_at.date()
    _, candle_latest_date = await get_min_max_date(session, instrument.id)
    instrument_context = {
        "symbol": instrument.symbol,
        "shortname": instrument.shortname,
        "name": instrument.name,
        "isin": instrument.isin,
        "currency": str(market.currency),
        "market": market.mic,
    }
    grounding_context = {
        "market_context": {
            "market_country": market.country,
            "market_timezone": str(market.timezone),
            "market_currency": str(market.currency),
        },
        "quote_context": {
            "last_trade_date": latest_trade_date.isoformat(),
            "current_price": float(quote_latest.last_price),
            "change_1d_pct": float(quote_latest.change_pct),
            "latest_quote_volume": int(quote_latest.volume) if quote_latest.volume is not None else None,
            "candle_latest_date": candle_latest_date.isoformat() if candle_latest_date is not None else None,
        },
        "reporting_guidance": {
            "requested_period": requested_period,
            "current_closed_quarter": current_period,
            "today": today.isoformat(),
            "use_latest_public_period_if_requested_not_published": True,
            "prefer_public_sources": True,
        },
    }
    current_prompt_hash = build_ai_cache_prompt_hash(
        mic=market.mic,
        symbol=instrument.symbol,
        period=requested_period,
    )

    ai_snapshot = await get_report_ai_snapshot(
        session=session,
        instrument_id=instrument.id,
        asset_class=asset_class,
        period=requested_period,
        schema_version=schema_version,
    )
    final_snapshot = await get_report_snapshot(
        session=session,
        instrument_id=instrument.id,
        asset_class=asset_class,
        period=requested_period,
        schema_version=schema_version,
    )

    ai_fresh = ai_snapshot_is_fresh(
        ai_snapshot,
        current_period=current_period,
        requested_period=requested_period,
        today=today,
        current_prompt_hash=current_prompt_hash,
    )
    final_snapshot_sparse = final_report_payload_needs_enrichment(final_snapshot.final_payload) if final_snapshot is not None else True

    if snapshot_is_usable(
        final_snapshot,
        ai_fresh=ai_fresh,
        latest_trade_date=latest_trade_date,
        candle_latest_date=candle_latest_date,
    ) and not final_snapshot_sparse:
        snapshots = await list_report_snapshots(
            session=session,
            instrument_id=instrument.id,
            asset_class=asset_class,
            schema_version=schema_version,
        )
        return EquityReportResponse(
            asset_class="equity",
            report=_snapshot_to_report(final_snapshot),
            available_periods=_available_periods(snapshots, current_period=current_period),
        )

    if needs_candle_refresh(candle_latest_date, latest_trade_date):
        logger.info(
            "Refreshing daily candles before building report mic=%s symbol=%s latest_trade_date=%s max_candle=%s",
            mic,
            symbol,
            latest_trade_date,
            candle_latest_date,
        )
        await sync_daily_by_symbol(session, symbol=instrument.symbol, overlap_days=7)
        await session.commit()
        _, candle_latest_date = await get_min_max_date(session, instrument.id)

    candles = await list_candles_daily(
        session=session,
        instrument_id=instrument.id,
        date_from=latest_trade_date - timedelta(days=TECHNICAL_CANDLE_LOOKBACK_DAYS),
        date_to=latest_trade_date,
    )
    ai_payload_sparse = report_payload_needs_enrichment(ai_snapshot.ai_payload) if ai_snapshot is not None else True
    needs_web_source_facts = should_fetch_web_source_facts(
        ai_payload_sparse=ai_payload_sparse,
        final_snapshot_sparse=final_snapshot_sparse,
        ai_fresh=ai_fresh,
    )
    web_source_facts = None
    if needs_web_source_facts:
        web_source_facts = await _fetch_web_source_facts(
            mic=market.mic,
            symbol=instrument.symbol,
            shortname=instrument.shortname,
        )

    force_grounded_ai_refresh = should_refresh_ai_for_grounded_narrative(
        ai_fresh=ai_fresh,
        ai_payload_sparse=ai_payload_sparse,
        web_source_facts=web_source_facts,
    )

    if ai_fresh and ai_snapshot is not None and not force_grounded_ai_refresh:
        sanitized_cached_payload = sanitize_equity_ai_payload(
            EquityAiPayload.model_validate(ai_snapshot.ai_payload),
            symbol=instrument.symbol,
            mic=market.mic,
            instrument_name=instrument.name,
            instrument_shortname=instrument.shortname,
            instrument_isin=instrument.isin,
        )
        enriched_cached_payload = merge_web_source_facts(
            sanitized_cached_payload,
            web_source_facts,
        )
        report, market_data_as_of = build_equity_report(
            ai_payload=enriched_cached_payload,
            mic=market.mic,
            symbol=instrument.symbol,
            currency=str(market.currency),
            instrument_shortname=instrument.shortname,
            instrument_name=instrument.name,
            instrument_isin=instrument.isin,
            current_price=float(quote_latest.last_price),
            change_1d_pct=float(quote_latest.change_pct),
            last_trade_at=quote_latest.last_trade_at,
            candles=candles,
            period=requested_period,
            model=ai_snapshot.model,
            final_generated_at=datetime.now().astimezone(),
            valid_until=ai_snapshot.valid_until,
        )
        report = merge_web_source_report_metrics(report, web_source_facts)
        snapshot_generated_at = datetime.now().astimezone()
        snapshot = await upsert_report_snapshot(
            session=session,
            instrument_id=instrument.id,
            ai_snapshot_id=ai_snapshot.id,
            asset_class=asset_class,
            period=requested_period,
            schema_version=schema_version,
            final_payload=report.model_dump(mode="json"),
            market_data_as_of=market_data_as_of,
            generated_at=snapshot_generated_at,
            valid_until=ai_snapshot.valid_until,
        )
        await session.commit()
        snapshots = await list_report_snapshots(
            session=session,
            instrument_id=instrument.id,
            asset_class=asset_class,
            schema_version=schema_version,
        )
        return EquityReportResponse(
            asset_class="equity",
            report=_snapshot_to_report(snapshot),
            available_periods=_available_periods(snapshots, current_period=current_period),
        )

    lock_key = f"report:refresh:{instrument.id}:{asset_class.value}:{requested_period}"
    lock_payload = {
        "instrument_id": str(instrument.id),
        "asset_class": asset_class.value,
        "period": requested_period,
    }
    acquired = await storage.stock.set_if_absent(lock_key, lock_payload, timeout=120)
    if not acquired:
        if final_snapshot is not None and not final_snapshot_sparse:
            snapshots = await list_report_snapshots(
                session=session,
                instrument_id=instrument.id,
                asset_class=asset_class,
                schema_version=schema_version,
            )
            return EquityReportResponse(
                asset_class="equity",
                report=_snapshot_to_report(final_snapshot),
                available_periods=_available_periods(snapshots, current_period=current_period),
            )
        waited_snapshot = await _wait_for_existing_snapshot(
            session=session,
            instrument_id=instrument.id,
            asset_class=asset_class,
            period=requested_period,
            schema_version=schema_version,
        )
        if waited_snapshot is not None:
            snapshots = await list_report_snapshots(
                session=session,
                instrument_id=instrument.id,
                asset_class=asset_class,
                schema_version=schema_version,
            )
            return EquityReportResponse(
                asset_class="equity",
                report=_snapshot_to_report(waited_snapshot),
                available_periods=_available_periods(snapshots, current_period=current_period),
            )
        if final_snapshot is not None:
            snapshots = await list_report_snapshots(
                session=session,
                instrument_id=instrument.id,
                asset_class=asset_class,
                schema_version=schema_version,
            )
            return EquityReportResponse(
                asset_class="equity",
                report=_snapshot_to_report(final_snapshot),
                available_periods=_available_periods(snapshots, current_period=current_period),
            )
        raise ReportGenerationError("Report refresh is already in progress.")

    openai_client = client or OpenAIEquityReportClient()
    ai_generated_at = datetime.now().astimezone()
    ai_valid_until = ai_generated_at.date() + timedelta(days=90)

    try:
        prompt_grounding_context = grounding_context
        if web_source_facts is not None and web_source_facts.has_material_data():
            prompt_public_web_facts = web_source_facts.to_prompt_dict()
            valuation_anchors = prompt_public_web_facts.get("valuation_anchors", {})
            valuation_benchmarks = prompt_public_web_facts.get("valuation_benchmarks", {})
            logger.debug(
                "AI valuation context mic=%s symbol=%s anchors=%s benchmarks=%s",
                market.mic,
                instrument.symbol,
                {
                    key: value.get("value")
                    for key, value in valuation_anchors.items()
                    if isinstance(value, dict) and value.get("value") is not None
                },
                {
                    key: value.get("value")
                    for key, value in valuation_benchmarks.items()
                    if isinstance(value, dict) and value.get("value") is not None
                },
            )
            prompt_grounding_context = {
                **grounding_context,
                "public_web_facts": prompt_public_web_facts,
            }
        user_prompt = build_user_prompt(
            mic=market.mic,
            symbol=instrument.symbol,
            period=requested_period,
            today=today,
            instrument_context=instrument_context,
            grounding_context=prompt_grounding_context,
        )
        generated = await openai_client.generate(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )
        sanitized_generated_payload = sanitize_equity_ai_payload(
            generated.payload,
            symbol=instrument.symbol,
            mic=market.mic,
            instrument_name=instrument.name,
            instrument_shortname=instrument.shortname,
            instrument_isin=instrument.isin,
        )
        enriched_generated_payload = merge_web_source_facts(
            sanitized_generated_payload,
            web_source_facts,
        )
        ai_snapshot = await upsert_report_ai_snapshot(
            session=session,
            instrument_id=instrument.id,
            asset_class=asset_class,
            period=requested_period,
            schema_version=schema_version,
            ai_payload=enriched_generated_payload.model_dump(mode="json"),
            model=generated.model,
            prompt_version=settings.OPENAI_REPORT_PROMPT_VERSION,
            prompt_hash=current_prompt_hash,
            generated_at=ai_generated_at,
            valid_until=ai_valid_until,
            usage_prompt_tokens=generated.usage_prompt_tokens,
            usage_output_tokens=generated.usage_output_tokens,
            status="ready",
            last_error=None,
        )

        report_generated_at = datetime.now().astimezone()
        report, market_data_as_of = build_equity_report(
            ai_payload=enriched_generated_payload,
            mic=market.mic,
            symbol=instrument.symbol,
            currency=str(market.currency),
            instrument_shortname=instrument.shortname,
            instrument_name=instrument.name,
            instrument_isin=instrument.isin,
            current_price=float(quote_latest.last_price),
            change_1d_pct=float(quote_latest.change_pct),
            last_trade_at=quote_latest.last_trade_at,
            candles=candles,
            period=requested_period,
            model=generated.model,
            final_generated_at=report_generated_at,
            valid_until=ai_valid_until,
        )
        report = merge_web_source_report_metrics(report, web_source_facts)
        snapshot = await upsert_report_snapshot(
            session=session,
            instrument_id=instrument.id,
            ai_snapshot_id=ai_snapshot.id,
            asset_class=asset_class,
            period=requested_period,
            schema_version=schema_version,
            final_payload=report.model_dump(mode="json"),
            market_data_as_of=market_data_as_of,
            generated_at=report_generated_at,
            valid_until=ai_valid_until,
        )
        await session.commit()
    except OpenAIReportError as exc:
        await mark_report_ai_snapshot_failure(
            session=session,
            instrument_id=instrument.id,
            asset_class=asset_class,
            period=requested_period,
            schema_version=schema_version,
            model=settings.OPENAI_REPORT_MODEL,
            prompt_version=settings.OPENAI_REPORT_PROMPT_VERSION,
            prompt_hash=current_prompt_hash,
            generated_at=ai_generated_at,
            valid_until=ai_valid_until,
            error=str(exc),
        )
        await session.commit()
        if final_snapshot is not None:
            snapshots = await list_report_snapshots(
                session=session,
                instrument_id=instrument.id,
                asset_class=asset_class,
                schema_version=schema_version,
            )
            return EquityReportResponse(
                asset_class="equity",
                report=_snapshot_to_report(final_snapshot),
                available_periods=_available_periods(snapshots, current_period=current_period),
            )
        raise ReportGenerationError(str(exc)) from exc
    finally:
        await storage.stock.clear(lock_key)

    snapshots = await list_report_snapshots(
        session=session,
        instrument_id=instrument.id,
        asset_class=asset_class,
        schema_version=schema_version,
    )
    return EquityReportResponse(
        asset_class="equity",
        report=_snapshot_to_report(snapshot),
        available_periods=_available_periods(snapshots, current_period=current_period),
    )
