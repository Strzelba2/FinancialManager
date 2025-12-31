from typing import Optional
import logging
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import RealEstatePrice
from app.crud.real_estates_price_crud import get_latest_real_estate_price


logger = logging.getLogger(__name__)


async def get_latest_price_with_fallback(
    session: AsyncSession,
    type,
    country: Optional[str],
    city: Optional[str],
    currency,
) -> Optional[RealEstatePrice]:
    """
    Get the latest real estate price (per m²) with a simple fallback strategy.

    Lookup order:
        1) (type, country, city, currency)     if both country and city provided
        2) (type, country, None, currency)     if country provided
        3) (type, None, None, currency)        global fallback

    Args:
        session: SQLAlchemy async session.
        property_type: Property type (e.g., APARTMENT, HOUSE).
        country: Optional country filter.
        city: Optional city filter.
        currency: Currency to match.

    Returns:
        RealEstatePrice if found, otherwise None.
    """

    if country and city:
        p = await get_latest_real_estate_price(
            session, type=type, country=country, city=city, currency=currency
        )
        if p:
            return p

    if country:
        p = await get_latest_real_estate_price(
            session, type=type, country=country, city=None, currency=currency
        )
        if p:
            return p

    return await get_latest_real_estate_price(
        session, type=type, country=None, city=None, currency=currency
    )