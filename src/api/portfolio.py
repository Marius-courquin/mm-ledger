from fastapi import APIRouter
from src.schemas.portfolio import PortfolioResponse

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


@router.get("", response_model=PortfolioResponse)
def get_portfolio(connector_id: str | None = None):
    return PortfolioResponse()


@router.get("/{connector_id}", response_model=PortfolioResponse)
def get_portfolio_by_connector(connector_id: str):
    return PortfolioResponse()
