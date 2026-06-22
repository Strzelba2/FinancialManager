from __future__ import annotations

import logging

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.clients.stock_client import StockClient, StockInstrumentUpdateError
from app.models.enums import InstrumentCurrency, InstrumentType
from app.models.models import Instrument
from app.schemas.response import InstrumentNameSyncResponse, StockInstrumentRead


logger = logging.getLogger(__name__)


def _wallet_currency(value: str) -> InstrumentCurrency:
    try:
        return InstrumentCurrency(value.strip().upper())
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Unsupported instrument currency returned by stock.",
        ) from exc


def _wallet_instrument_type(value: str) -> InstrumentType:
    try:
        return InstrumentType(value.strip().upper())
    except ValueError:
        logger.warning(
            "Stock instrument type %r has no wallet equivalent; using STOCK for the local mirror",
            value,
        )
        return InstrumentType.STOCK


async def _resolve_stock_instrument(
    stock_client: StockClient,
    mic: str,
    symbol: str,
) -> StockInstrumentRead:
    try:
        return await stock_client.resolve_instrument(mic=mic, symbol=symbol)
    except ValueError as exc:
        detail = str(exc)
        code = status.HTTP_404_NOT_FOUND if "not found" in detail.lower() else status.HTTP_502_BAD_GATEWAY
        raise HTTPException(status_code=code, detail=detail) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Stock service unavailable.",
        ) from exc


def _stock_error(exc: StockInstrumentUpdateError) -> HTTPException:
    allowed = {
        status.HTTP_404_NOT_FOUND,
        status.HTTP_409_CONFLICT,
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        status.HTTP_503_SERVICE_UNAVAILABLE,
    }
    code = exc.status_code if exc.status_code in allowed else status.HTTP_502_BAD_GATEWAY
    return HTTPException(status_code=code, detail=exc.detail)


async def synchronize_instrument_name(
    session: AsyncSession,
    stock_client: StockClient,
    mic: str,
    symbol: str,
    name: str,
) -> InstrumentNameSyncResponse:
    """Synchronize stock.shortname and wallet.instrument.name with compensation."""
    canonical = await _resolve_stock_instrument(stock_client, mic, symbol)
    mic_u = canonical.mic.strip().upper()
    symbol_u = canonical.symbol.strip().upper()
    previous_shortname = canonical.shortname
    stock_result: StockInstrumentRead | None = None
    created = False

    try:
        async with session.begin():
            result = await session.execute(
                select(Instrument)
                .where(Instrument.symbol == symbol_u)
                .with_for_update()
            )
            instrument = result.scalar_one_or_none()
            if instrument is not None and instrument.mic != mic_u:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Instrument symbol already exists in wallet for another MIC.",
                )

            if instrument is None:
                created = True
                instrument = Instrument(
                    mic=mic_u,
                    symbol=symbol_u,
                    name=previous_shortname,
                    currency=_wallet_currency(canonical.currency),
                    type=_wallet_instrument_type(canonical.type),
                )
                session.add(instrument)
                await session.flush()

            try:
                stock_result = await stock_client.update_instrument_shortname(
                    mic=mic_u,
                    symbol=symbol_u,
                    shortname=name,
                    expected_shortname=previous_shortname,
                )
            except StockInstrumentUpdateError as exc:
                if exc.status_code < 500:
                    raise _stock_error(exc) from exc

                reconciled = await _resolve_stock_instrument(stock_client, mic_u, symbol_u)
                if reconciled.shortname != name.strip().upper():
                    raise _stock_error(exc) from exc
                stock_result = reconciled

            instrument.name = stock_result.shortname
            await session.flush()
    except HTTPException:
        if stock_result is not None:
            compensation_ok = await _compensate_stock_name(
                stock_client=stock_client,
                mic=mic_u,
                symbol=symbol_u,
                current_shortname=stock_result.shortname,
                previous_shortname=previous_shortname,
            )
            if not compensation_ok:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Instrument name synchronization failed and stock compensation was unsuccessful.",
                )
        raise
    except Exception as exc:
        compensation_ok = True
        if stock_result is not None:
            compensation_ok = await _compensate_stock_name(
                stock_client=stock_client,
                mic=mic_u,
                symbol=symbol_u,
                current_shortname=stock_result.shortname,
                previous_shortname=previous_shortname,
            )
        logger.exception("Wallet instrument name synchronization failed for %s/%s", mic_u, symbol_u)
        detail = (
            "Instrument name synchronization failed and stock compensation was unsuccessful."
            if not compensation_ok
            else "Instrument name synchronization failed."
        )
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=detail) from exc

    assert stock_result is not None
    return InstrumentNameSyncResponse(
        symbol=symbol_u,
        mic=mic_u,
        name=stock_result.shortname,
        created=created,
    )


async def _compensate_stock_name(
    stock_client: StockClient,
    mic: str,
    symbol: str,
    current_shortname: str,
    previous_shortname: str,
) -> bool:
    try:
        await stock_client.update_instrument_shortname(
            mic=mic,
            symbol=symbol,
            shortname=previous_shortname,
            expected_shortname=current_shortname,
        )
        return True
    except StockInstrumentUpdateError:
        logger.critical(
            "Stock compensation failed after wallet instrument name error for %s/%s",
            mic,
            symbol,
            exc_info=True,
        )
        return False
