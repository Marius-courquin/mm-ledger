from pydantic import BaseModel

class SnapshotResponse(BaseModel):
    account_id: str
    date: str
    cash: float | None = None
    positions_value: float | None = None
    total_value: float | None = None
    currency: str = "EUR"
    positions: list[dict] | None = None

class TransactionResponse(BaseModel):
    id: int
    account_id: str
    date: str
    type: str | None = None
    label: str | None = None
    amount: float | None = None
    currency: str = "EUR"
    instrument: str | None = None
    quantity: float | None = None
    price: float | None = None

class PerformanceResponse(BaseModel):
    connector_id: str
    period_start: str
    period_end: str
    total_value: float | None = None
    total_invested: float | None = None
    pnl: float | None = None
    pnl_pct: float | None = None
    breakdown: dict | None = None

class TriggerResponse(BaseModel):
    triggered: list[str] | str
    skipped: list[str] | None = None
    reason_skipped: dict | None = None
