from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
import logging

from app.db.session import db
from app.crud.real_estates_price_crud import create_real_estate_price
from app.api.services.real_estate import get_latest_price_with_fallback
from app.models.enums import PropertyType, Currency
from app.schamas.schemas import RealEstatePriceCreate, RealEstatePriceRead


logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/real-estate-prices/create", response_model=RealEstatePriceRead)
async def create_price(
    payload: RealEstatePriceCreate,
    session: AsyncSession = Depends(db.get_session),
) -> RealEstatePriceRead:
    """
    Create a new real-estate price (price per m²) record.

    Args:
        payload: RealEstatePriceCreate payload.
        session: SQLAlchemy async session.

    Returns:
        The created RealEstatePriceRead.
    """
    logger.info("POST /real-estate-prices/create: start ")
    obj = await create_real_estate_price(session, payload)
    return RealEstatePriceRead.model_validate(obj)


@router.get("/real-estate-prices/latest", response_model=Optional[RealEstatePriceRead])
async def get_latest_price(
    type: PropertyType = Query(..., alias="type"),
    currency: Currency = Query(...),
    country: Optional[str] = None,
    city: Optional[str] = None,
    session: AsyncSession = Depends(db.get_session),
) -> Optional[RealEstatePriceRead]:
    """
    Get the latest real-estate price (price per m²) with fallback logic.

    Typical fallback strategy (depends on your CRUD implementation):
    - (type, country, city, currency)
    - then maybe (type, country, currency)
    - then maybe (type, currency)
    - etc.

    Args:
        property_type: PropertyType, provided as query parameter "type".
        currency: Target currency.
        country: Optional country filter.
        city: Optional city filter.
        session: SQLAlchemy async session.

    Returns:
        RealEstatePriceRead if found, otherwise None.
    """
    logger.info("GET /real-estate-prices/latest: start ")
    obj = await get_latest_price_with_fallback(
        session,
        type=type,
        country=country,
        city=city,
        currency=currency,
    )
    return RealEstatePriceRead.model_validate(obj) if obj else None
