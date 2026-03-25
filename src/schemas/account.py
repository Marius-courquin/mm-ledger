from pydantic import BaseModel

class AccountResponse(BaseModel):
    id: str
    connector_id: str
    name: str | None = None
    type: str | None = None
    currency: str = "EUR"

class BalanceResponse(BaseModel):
    account_id: str
    cash: float | None = None
    positions_value: float | None = None
    total_value: float | None = None
    currency: str = "EUR"
    updated_at: str | None = None
