from fastapi import APIRouter
from src.api.vault_routes import router as vault_router
from src.api.connectors import router as connectors_router

api_router = APIRouter()
api_router.include_router(vault_router)
api_router.include_router(connectors_router)
