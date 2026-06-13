from fastapi import APIRouter, Depends, HTTPException, Query
import uuid
from typing import Optional, List
from datetime import date
import logging
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import db
from app.api.deps import get_internal_user_id
from app.core.exceptions import (
    ImportMismatchError, UnknownAccountError, UnknownUserError, DuplicateTransactionError
)
from app.schemas.schemas import CreateTransactionsRequest
from app.schemas.response import (
    TransactionPageOut, BatchUpdateTransactionsRequest,
    BatchUpdateTransactionsResponse, TransactionRowOut
)
from app.api.services.transactions import create_transactions_rebalance_service
from app.crud.transaction_crud import (
    list_transactions_page, batch_update_transactions, delete_transaction_for_user_rebalance
    )

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/transactions/create/rebalance", status_code=201)
async def create_transactions_rebalance(
    payload: CreateTransactionsRequest,
    user_id: uuid.UUID = Depends(get_internal_user_id),
    session: AsyncSession = Depends(db.get_session),
):
    """
    Create a set of rebalance transactions for the given user.

    The service performs validations (user/account existence, duplicates, import mismatch),
    and can optionally verify the resulting account balance after applying transactions.

    Args:
        payload: Request body containing the rebalance transaction specification.
        user_id: Internal user UUID resolved from request (dependency).
        session: SQLAlchemy async database session (dependency).

    Returns:
        The service result returned by `create_transactions_rebalance_service`.

    Raises:
        HTTPException:
            - 400 for unknown user.
            - 404 for unknown account.
            - 409 for duplicate transaction.
            - 422 for import mismatch / validation mismatch.
    """
    async with session.begin():
        try:
            return await create_transactions_rebalance_service(
                session=session,
                user_id=user_id,
                payload=payload,
                verify_amount_after=True,
                skip_duplicates=payload.skip_duplicates,
            )
        except UnknownUserError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except UnknownAccountError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except DuplicateTransactionError as e:
            raise HTTPException(status_code=409, detail=str(e))
        except ImportMismatchError as e:
            raise HTTPException(status_code=422, detail=str(e))


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
    sort_by: str = Query("date", pattern="^(date|account|category|status)$"),
    sort_dir: str = Query("desc", pattern="^(asc|desc)$"),
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
                                                sort_by=sort_by,
                                                sort_dir=sort_dir,
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
        try:
            ok = await delete_transaction_for_user_rebalance(session=session, user_id=user_id, transaction_id=transaction_id)
        except ImportMismatchError as e:
            raise HTTPException(status_code=400, detail=str(e))
        if not ok:
            raise HTTPException(status_code=404, detail="Transaction not found")
    return {"ok": True}
