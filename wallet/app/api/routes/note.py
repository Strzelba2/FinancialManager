import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
import logging

from app.db.session import db
from app.api.deps import get_internal_user_id
from app.crud.user_crud import get_user
from app.crud.user_note_crud import get_user_note, upsert_user_note
from app.schamas.schemas import UserNoteUpsert, UserNoteRead


logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/me/note", response_model=Optional[UserNoteRead])
async def get_my_note(
    user_id: uuid.UUID = Depends(get_internal_user_id),
    session: AsyncSession = Depends(db.get_session),
) -> Optional[UserNoteRead]:
    """
    Get the authenticated user's note.

    Args:
        user_id: Authenticated user UUID (resolved internally).
        session: SQLAlchemy async session.

    Returns:
        UserNoteRead if the note exists, otherwise None.

    Raises:
        HTTPException(400): if user_id is unknown.
    """
    logger.info("GET /me/note: start ")
    user = await get_user(session, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown user_id")

    obj = await get_user_note(session, user_id=user_id)
    return UserNoteRead.model_validate(obj) if obj else None


@router.put("/me/note", response_model=UserNoteRead)
async def upsert_my_note(
    payload: UserNoteUpsert,
    user_id: uuid.UUID = Depends(get_internal_user_id),
    session: AsyncSession = Depends(db.get_session),
) -> UserNoteRead:
    """
    Create or update (upsert) the authenticated user's note.

    Args:
        payload: UserNoteUpsert (contains the note text).
        user_id: Authenticated user UUID.
        session: SQLAlchemy async session.

    Returns:
        The upserted note.

    Raises:
        HTTPException(400): if user_id is unknown.
    """
    logger.info("PUT /me/note: start")
    async with session.begin():
        user = await get_user(session, user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown user_id")

        obj = await upsert_user_note(session, user_id=user_id, text=payload.text)
        
        await session.refresh(obj)

        out = UserNoteRead.model_validate(obj)

    return out