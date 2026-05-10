from typing import Literal

from pydantic import BaseModel


AssetClass = Literal["equity", "etf", "bond", "crypto", "private", "other"]


class PositionResponse(BaseModel):
    connector_id: str
    account_id: str
    instrument: str | None = None  # = isin
    name: str | None = None
    symbol: str | None = None
    asset_class: AssetClass = "other"
    category: str | None = None    # rétrocompat front (= asset_class pour l'instant)
    quantity: float = 0
    avg_price: float | None = None
    current_price: float | None = None
    value: float | None = None
    pnl: float | None = None
    pnl_pct: float | None = None
    currency: str = "EUR"


class PortfolioResponse(BaseModel):
    total_value: float = 0
    total_invested: float = 0
    total_pnl: float = 0
    total_pnl_pct: float = 0
    currency: str = "EUR"
    positions: list[PositionResponse] = []
