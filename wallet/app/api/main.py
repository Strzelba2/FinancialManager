from fastapi import APIRouter
from app.api.routes import (
    wallet, account, transaction, brokerage, real_estate,
    real_estates_price, metal_holding, debt, recurring_expenses,
    note, goals, holding)

api_router = APIRouter()

api_router.include_router(wallet.router, prefix="/wallet", tags=["wallet"])
api_router.include_router(account.router, prefix="/wallet", tags=["wallet"])
api_router.include_router(transaction.router, prefix="/wallet", tags=["wallet"])
api_router.include_router(brokerage.router, prefix="/wallet", tags=["wallet"])
api_router.include_router(real_estate.router, prefix="/wallet", tags=["wallet"])
api_router.include_router(real_estates_price.router, prefix="/wallet", tags=["wallet"])
api_router.include_router(metal_holding.router, prefix="/wallet", tags=["wallet"])
api_router.include_router(debt.router, prefix="/wallet", tags=["wallet"])
api_router.include_router(recurring_expenses.router, prefix="/wallet", tags=["wallet"])
api_router.include_router(goals.router, prefix="/wallet", tags=["wallet"])
api_router.include_router(note.router, prefix="/users", tags=["users"])
api_router.include_router(holding.router, prefix="/users", tags=["users"])
