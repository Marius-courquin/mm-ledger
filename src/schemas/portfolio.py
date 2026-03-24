from pydantic import BaseModel

class PositionResponse(BaseModel):
    connector_id: str
    account_id: str
    instrument: str | None = None
    name: str | None = None
    symbol: str | None = None
    category: str | None = None
    quantity: float = 0
    avg_price: float = 0
    current_price: float = 0
    value: float = 0
    pnl: float = 0
    pnl_pct: float = 0
    currency: str = "EUR"

class PortfolioResponse(BaseModel):
    total_value: float = 0
    total_invested: float = 0
    total_pnl: float = 0
    total_pnl_pct: float = 0
    currency: str = "EUR"
    positions: list[PositionResponse] = []
