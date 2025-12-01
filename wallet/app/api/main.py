from fastapi import APIRouter
from app.api.routes import wallet, account, transaction, brokerage

api_router = APIRouter()

api_router.include_router(wallet.router, prefix="/wallet", tags=["wallet"])
api_router.include_router(account.router, prefix="/wallet", tags=["wallet"])
api_router.include_router(transaction.router, prefix="/wallet", tags=["wallet"])
api_router.include_router(brokerage.router, prefix="/wallet", tags=["wallet"])
