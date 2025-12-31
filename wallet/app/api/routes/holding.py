from fastapi import APIRouter, Depends, Query
import uuid
import logging
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession


from app.schamas.response import HoldingRowOut
from app.db.session import db
from app.api.deps import get_internal_user_id
from app.crud.holding_crud import list_holdings_rows_for_user

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/{user_id}/holdings", response_model=List[HoldingRowOut])
async def api_list_holdings_for_user(
    brokerage_account_id: list[uuid.UUID] = Query(default_factory=list),
    q: Optional[str] = None,
    user_id: uuid.UUID = Depends(get_internal_user_id),
    session: AsyncSession = Depends(db.get_session),
) -> List[HoldingRowOut]:
    """
    List holdings rows for the authenticated user.

    Optional filters:
    - brokerage_account_id: restrict holdings to one or more brokerage accounts
    - q: free-text search (symbol/name)

    Args:
        brokerage_account_id: List of brokerage account UUIDs. Empty -> all accounts.
        q: Optional search query.
        user_id: Authenticated user UUID.
        session: SQLAlchemy async session.

    Returns:
        List of HoldingRowOut rows.
    """
    logger.info("GET /holdings: start ")
    rows = await list_holdings_rows_for_user(
        session,
        user_id=user_id,
        brokerage_account_ids=brokerage_account_id or None,
        q=q,
    )
    return rows