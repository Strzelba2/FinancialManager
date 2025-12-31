import logging
from typing import Optional
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import RealEstatePrice
from app.schamas.schemas import (
    RealEstatePriceCreate,
)


logger = logging.getLogger(__name__)


async def create_real_estate_price(
    session: AsyncSession,
    payload: RealEstatePriceCreate,
) -> RealEstatePrice:
    """
    Create a RealEstatePrice row (price per m² record).

    Notes:
        This function does NOT commit. Caller should manage transaction boundary.

    Args:
        session: SQLAlchemy async session.
        payload: RealEstatePriceCreate payload.

    Returns:
        Created RealEstatePrice ORM object.

    Raises:
        ValueError: if constraints fail (mapped from IntegrityError).
    """
    obj = RealEstatePrice(**payload.model_dump())
    session.add(obj)
    await session.commit()
    await session.refresh(obj)
    return obj


async def get_latest_real_estate_price(
    session: AsyncSession,
    type,
    country: Optional[str],
    city: Optional[str],
    currency,
) -> Optional[RealEstatePrice]:
    """
    Get the latest RealEstatePrice row for an exact (type, currency, country, city) match.

    Args:
        session: SQLAlchemy async session.
        property_type: Property type to match.
        country: Country to match (exact; can be None).
        city: City to match (exact; can be None).
        currency: Currency to match.

    Returns:
        The latest matching RealEstatePrice or None if not found.
    """
    stmt = (
        select(RealEstatePrice)
        .where(
            RealEstatePrice.type == type,
            RealEstatePrice.currency == currency,
            RealEstatePrice.country == country,
            RealEstatePrice.city == city,
        )
        .order_by(RealEstatePrice.created_at.desc())
        .limit(1)
    )

    res = await session.execute(stmt)
    return res.scalar_one_or_none()
