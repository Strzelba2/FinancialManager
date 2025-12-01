from fastapi import APIRouter, Depends, HTTPException
import uuid
import logging
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import db
from app.api.deps import get_internal_user_id
from app.crud.user_crud import get_user
from app.core.exceptions import ImportMismatchError
from app.schamas.schemas import CreateTransactionsRequest
from app.api.services.transactions import create_transactions_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post('/transactions/create', status_code=201)
async def create_transactions(
    payload: CreateTransactionsRequest,
    user_id: uuid.UUID = Depends(get_internal_user_id),
    session: AsyncSession = Depends(db.get_session),
):
    """
    Create one or more cash transactions for a given account.

    Flow:
        1. Open a DB transaction (`session.begin()`).
        2. Verify that the `user_id` corresponds to an existing user.
        3. Call `create_transactions_service` to import transactions and
           update the account balance.
        4. Map domain exceptions to HTTP errors:
           - ValueError           → 404 Not Found (e.g. unknown account_id)
           - ImportMismatchError  → 422 Unprocessable Entity
        5. Return a summary dict from the service.

    Args:
        payload: Request body describing account_id and a list of transactions.
        user_id: Internal user ID from dependency (`get_internal_user_id`).
        session: Async SQLAlchemy session (injected via dependency).

    Raises:
        HTTPException(400): If the user does not exist.
        HTTPException(404): If the service raises ValueError (e.g. bad account_id).
        HTTPException(422): If the service raises ImportMismatchError (e.g. balance mismatch).

    Returns:
        A summary dict, typically containing:
            - number of created transactions
            - final balance
            - account ID
        (Exact structure depends on `create_transactions_service`.)
    """
    async with session.begin(): 
        user = await get_user(session, user_id)
        if not user:
            raise HTTPException(status_code=400, detail='Unknown user_id')
        
        try:
            
            summary = await create_transactions_service(session, payload, True)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except ImportMismatchError as e:
            raise HTTPException(
                status_code=422,
                detail=str(e)
            )

    return summary
