from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.models.models import CapitalGain
from app.schamas.schemas import CapitalGainCreate


async def create_capital_gain(session: AsyncSession, data: CapitalGainCreate) -> CapitalGain:
    obj = CapitalGain(**data.model_dump()) 
 
    session.add(obj)
    try:
        await session.flush()
    except IntegrityError as e:
        raise ValueError("Transaction already exists for this capital gain, or invalid FK.") from e
    await session.refresh(obj)
    return obj
