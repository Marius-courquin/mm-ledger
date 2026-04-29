from typing import Literal
from pydantic import BaseModel, Field


Category = Literal["cash", "market"]


class ProjectionSettings(BaseModel):
    cash_annual_rate: float = Field(ge=0, le=0.5)
    market_annual_rate: float = Field(ge=0, le=0.5)
    cash_monthly_contribution: float = Field(ge=0)
    market_monthly_contribution: float = Field(ge=0)
    horizon_years: int = Field(ge=1, le=50)


class ProjectionSettingsUpdate(BaseModel):
    cash_annual_rate: float | None = Field(default=None, ge=0, le=0.5)
    market_annual_rate: float | None = Field(default=None, ge=0, le=0.5)
    cash_monthly_contribution: float | None = Field(default=None, ge=0)
    market_monthly_contribution: float | None = Field(default=None, ge=0)
    horizon_years: int | None = Field(default=None, ge=1, le=50)


class AccountCategorization(BaseModel):
    account_id: str
    category: Category
    auto: bool  # True si classification auto, False si override manuel


class AccountOverride(BaseModel):
    account_id: str
    category: Category


class ProjectionPoint(BaseModel):
    month_offset: int
    cash: float
    market: float
    total: float
    loan_monthly_active: float


class ProjectionStartingState(BaseModel):
    cash: float
    market: float
    loan_monthly: float


class ProjectionResult(BaseModel):
    settings: ProjectionSettings
    starting_state: ProjectionStartingState
    points: list[ProjectionPoint]
    classifications: list[AccountCategorization]
