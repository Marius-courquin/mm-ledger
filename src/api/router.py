from fastapi import APIRouter
from src.api.vault_routes import router as vault_router
from src.api.connectors import router as connectors_router
from src.api.accounts import router as accounts_router
from src.api.portfolio import router as portfolio_router
from src.api.snapshots import router as snapshots_router
from src.api.transactions import router as transactions_router
from src.api.performance import router as performance_router

api_router = APIRouter()
api_router.include_router(vault_router)
api_router.include_router(connectors_router)
api_router.include_router(accounts_router)
api_router.include_router(portfolio_router)
api_router.include_router(snapshots_router)
api_router.include_router(transactions_router)
api_router.include_router(performance_router)
