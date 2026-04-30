from datetime import datetime
from typing import Literal

from pydantic import BaseModel


AccountKind = Literal["cash", "securities", "liability"]


class AccountResponse(BaseModel):
    id: str
    connector_id: str
    connector_type: str
    name: str
    kind: AccountKind
    tax_wrapper: str = "none"
    currency: str = "EUR"


class BalanceResponse(BaseModel):
    account_id: str
    cash: float | None = None
    positions_value: float | None = None
    total_value: float = 0.0
    currency: str = "EUR"
    updated_at: datetime | None = None
