from fastapi import APIRouter, Depends, HTTPException, status
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
    async with session.begin(): 
        user = await get_user(session, user_id)
        if not user:
            raise HTTPException(status_code=400, detail='Unknown user_id')
        
        try:
            
            summary = await create_transactions_service(session, payload)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except ImportMismatchError as e:
            raise HTTPException(
                status_code=422,
                detail=f"Saldo po operacji w wierszu {e.index} nie zgadza się: {e.provided} != {e.computed}"
            )

    return summary
