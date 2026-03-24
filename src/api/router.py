from fastapi import APIRouter
from src.api.vault_routes import router as vault_router

api_router = APIRouter()
api_router.include_router(vault_router)
