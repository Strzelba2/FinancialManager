import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Path
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_internal_user_id, get_stock_client
from app.api.services.instrument_sync import synchronize_instrument_name
from app.clients.stock_client import StockClient
from app.db.session import db
from app.schemas.response import InstrumentNameSyncResponse
from app.schemas.schemas import InstrumentNameSyncRequest


router = APIRouter()


@router.put("/instruments/{symbol}/name", response_model=InstrumentNameSyncResponse)
async def api_synchronize_instrument_name(
    symbol: Annotated[str, Path(min_length=1, max_length=12)],
    payload: InstrumentNameSyncRequest,
    _user_id: uuid.UUID = Depends(get_internal_user_id),
    session: AsyncSession = Depends(db.get_session),
    stock_client: StockClient = Depends(get_stock_client),
) -> InstrumentNameSyncResponse:
    return await synchronize_instrument_name(
        session=session,
        stock_client=stock_client,
        mic=payload.mic,
        symbol=symbol,
        name=payload.name,
    )
