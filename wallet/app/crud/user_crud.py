import uuid
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import User
from app.schamas.schemas import UserCreate, UserUpdate


def _utcnow():
    return datetime.now(timezone.utc)


async def create_user(session: AsyncSession, data: UserCreate) -> User:
    user = User(**data.model_dump())
    session.add(user)
    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        raise ValueError("Username or email already exists.") from e
    await session.refresh(user)
    return user


async def get_user(session: AsyncSession, user_id: uuid.UUID) -> Optional[User]:
    return await session.get(User, user_id)


async def get_user_by_username(session: AsyncSession, username: str) -> Optional[User]:
    result = await session.exec(select(User).where(User.username == username))
    return result.first()


async def get_user_by_email(session: AsyncSession, email: str) -> Optional[User]:
    result = await session.exec(select(User).where(User.email == email))
    return result.first()


async def list_users(
    session: AsyncSession,
    *,
    limit: int = 50,
    offset: int = 0,
    search: Optional[str] = None,
) -> List[User]:
    stmt = select(User).order_by(User.created_at.desc())
    if search:
        like = f"%{search}%"
        stmt = stmt.where((User.username.ilike(like)) | (User.email.ilike(like)))
    stmt = stmt.offset(offset).limit(limit)
    result = await session.exec(stmt)
    return result.all()


async def update_user(session: AsyncSession, user_id: uuid.UUID, data: UserUpdate) -> Optional[User]:
    user = await session.get(User, user_id)
    if not user:
        return None

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    user.updated_at = _utcnow()

    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        raise ValueError("Username or email already exists.") from e

    await session.refresh(user)
    return user


async def delete_user(session: AsyncSession, user_id: uuid.UUID) -> bool:
    user = await session.get(User, user_id)
    if not user:
        return False
    session.delete(user) 
    await session.commit()
    return True
