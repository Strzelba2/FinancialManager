from app.schamas.schemas import UserCreate
from app.models.models import User
from sqlalchemy.ext.asyncio import AsyncSession
from app.crud.user_crud import get_user_by_username, create_user

import logging

logger = logging.getLogger(__name__)


async def sync_user(session: AsyncSession, data: UserCreate) -> User:
    existing_user = await get_user_by_username(session, data.username)
    if existing_user:
        logger.info(f"user_exist: {existing_user}")
        return existing_user
    logger.info("user do not exist")
    return await create_user(session, data)
