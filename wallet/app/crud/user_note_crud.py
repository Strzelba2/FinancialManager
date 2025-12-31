import uuid
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.models import UserNote


async def get_user_note(session: AsyncSession, user_id: uuid.UUID) -> Optional[UserNote]:
    """
    Fetch the user's note (if any).

    Args:
        session: SQLAlchemy async session.
        user_id: User UUID.

    Returns:
        UserNote ORM object if found, otherwise None.
    """
    stmt = select(UserNote).where(UserNote.user_id == user_id)
    res = await session.execute(stmt)
    return res.scalars().first()


async def upsert_user_note(session: AsyncSession, user_id: uuid.UUID, text: str) -> UserNote:
    """
    Create or update a user's note.

    If no note exists for the user, a new one is inserted.
    Otherwise the existing note is updated.

    Notes:
        This function uses flush() but does not commit. Caller controls the transaction.

    Args:
        session: SQLAlchemy async session.
        user_id: User UUID.
        text: Note text (None/empty becomes "").

    Returns:
        The created/updated UserNote ORM object.
    """
    obj = await get_user_note(session, user_id=user_id)
    if obj is None:
        obj = UserNote(user_id=user_id, text=text or "")
        session.add(obj)
        await session.flush()
        return obj

    obj.text = text or ""
    session.add(obj)
    await session.flush()
    return obj
