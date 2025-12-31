from fastapi import APIRouter, Depends, HTTPException, Query
import uuid
from typing import Optional, List
from datetime import date
import logging
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import db
from app.api.deps import get_internal_user_id
from app.crud.user_crud import get_user
from app.core.exceptions import ImportMismatchError
from app.schamas.schemas import CreateTransactionsRequest
from app.schamas.response import (
    TransactionPageOut, BatchUpdateTransactionsRequest,
    BatchUpdateTransactionsResponse, TransactionRowOut
)
from app.api.services.transactions import create_transactions_service
from app.crud.transaction_crud import (
    list_transactions_page, batch_update_transactions, delete_transaction_for_user_rebalance
    )

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


@router.get("/transactions", response_model=TransactionPageOut)
async def get_transactions_page(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    account_id: Optional[List[uuid.UUID]] = Query(None),
    category: Optional[List[str]] = Query(None),
    status: Optional[List[str]] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    q: Optional[str] = Query(None),
    user_id: uuid.UUID = Depends(get_internal_user_id),
    session: AsyncSession = Depends(db.get_session),
) -> TransactionPageOut:
    """
    Return a paginated list of transactions for the authenticated user with optional filters.

    Filters:
        - account_id: list of account UUIDs
        - category: list of category strings
        - status: list of status strings (e.g. INCOME/EXPENSE/TRANSFER/...)
        - date_from/date_to: date range
        - q: free-text search

    Args:
        page: 1-based page index.
        size: page size (1..200).
        account_id: Optional list of account UUIDs.
        category: Optional list of categories.
        status: Optional list of statuses.
        date_from: Optional start date.
        date_to: Optional end date.
        q: Optional search query.
        user_id: Authenticated user UUID.
        session: SQLAlchemy async session.

    Returns:
        TransactionPageOut with enriched rows (account_name + currency code).
    """
    logger.info("GET /transactions: start ")
    rows, total, size, sum_by_ccy = await list_transactions_page(
                                                session=session,
                                                user_id=user_id,
                                                page=page,
                                                size=size,
                                                account_ids=account_id,
                                                categories=category,
                                                statuses=status,
                                                date_from=date_from,
                                                date_to=date_to,
                                                q=q,
                                            )
    
    items: list[TransactionRowOut] = []
    for tx, acc in rows:
        items.append(
            TransactionRowOut(
                **tx.model_dump(),
                account_name=acc.name,
                ccy=str(acc.currency.value),
            )
        )

    return TransactionPageOut(items=items, total=total, page=page, size=size, sum_by_ccy=sum_by_ccy,)


@router.patch("/transactions/batch", response_model=BatchUpdateTransactionsResponse)
async def patch_transactions_batch(
    req: BatchUpdateTransactionsRequest,
    user_id: uuid.UUID = Depends(get_internal_user_id),
    session: AsyncSession = Depends(db.get_session),
) -> BatchUpdateTransactionsResponse:
    """
    Batch update transactions for the authenticated user.

    Args:
        req: BatchUpdateTransactionsRequest containing update items.
        user_id: Authenticated user UUID.
        session: SQLAlchemy async session.

    Returns:
        BatchUpdateTransactionsResponse (as returned by service/CRUD).
    """
    logger.info("PATCH /transactions/batch: start")
    return await batch_update_transactions(
        session=session,
        user_id=user_id,
        req=req,
    )
   
    
@router.delete("/transactions/{transaction_id}")
async def api_delete_transaction(
    transaction_id: uuid.UUID, 
    user_id: uuid.UUID = Depends(get_internal_user_id),
    session: AsyncSession = Depends(db.get_session),
) -> dict:
    """
    Delete a transaction owned by the authenticated user and rebalance affected account(s).

    Args:
        transaction_id: Transaction UUID.
        user_id: Authenticated user UUID.
        session: SQLAlchemy async session.

    Returns:
        {"ok": True} on success.

    Raises:
        HTTPException(404): if the transaction was not found for this user.
    """
    logger.info(f"DELETE /transactions/{transaction_id}: start")
    async with session.begin():
        ok = await delete_transaction_for_user_rebalance(session=session, user_id=user_id, transaction_id=transaction_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Transaction not found")
    return {"ok": True}
