from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field


LoanType = Literal["immo", "conso", "auto", "other"]


class LoanBase(BaseModel):
    name: str
    loan_type: LoanType
    initial_capital: float = Field(gt=0)
    monthly_payment: float = Field(gt=0)
    total_months: int = Field(gt=0)
    start_date: str  # ISO YYYY-MM-DD


class LoanCreate(LoanBase):
    pass


class LoanUpdate(BaseModel):
    name: str | None = None
    loan_type: LoanType | None = None
    initial_capital: float | None = Field(default=None, gt=0)
    monthly_payment: float | None = Field(default=None, gt=0)
    total_months: int | None = Field(default=None, gt=0)
    start_date: str | None = None
    archived: bool | None = None


class LoanResponse(LoanBase):
    id: int
    archived: bool
    created_at: str
    # Champs calculés :
    end_date: str
    months_paid: int
    months_remaining: int
    amount_remaining: float
    progress_pct: float
    is_active: bool


class LoanSummary(BaseModel):
    total_monthly_payment: float
    total_amount_remaining: float
    last_end_date: str | None
    active_count: int


class LoanCandidate(BaseModel):
    account_id: str
    label: str
    balance: float
    currency: str
    connector_type: str
    as_of: datetime | None = None


class LinkRequest(BaseModel):
    account_id: str
