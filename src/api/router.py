from fastapi import APIRouter
from src.api.vault_routes import router as vault_router
from src.api.connectors import router as connectors_router
from src.api.accounts import router as accounts_router
from src.api.portfolio import router as portfolio_router
from src.api.snapshots import router as snapshots_router
from src.api.transactions import router as transactions_router
from src.api.performance import router as performance_router
from src.api.events import router as events_router
from src.api.health import router as health_router
from src.api.auth_routes import router as auth_router
from src.api.admin_routes import router as admin_router
from src.api.networth import router as networth_router
from src.api.cashflow import router as cashflow_router
from src.api.banking import router as banking_router
from src.api.targets import router as targets_router
from src.api.loans import router as loans_router
from src.api.projection import router as projection_router
from src.api.budget import router as budget_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(admin_router)
api_router.include_router(vault_router)
api_router.include_router(connectors_router)
api_router.include_router(accounts_router)
api_router.include_router(portfolio_router)
api_router.include_router(snapshots_router)
api_router.include_router(transactions_router)
api_router.include_router(performance_router)
api_router.include_router(events_router)
api_router.include_router(health_router)
api_router.include_router(networth_router)
api_router.include_router(cashflow_router)
api_router.include_router(banking_router)
api_router.include_router(targets_router)
api_router.include_router(loans_router)
api_router.include_router(projection_router)
api_router.include_router(budget_router)
