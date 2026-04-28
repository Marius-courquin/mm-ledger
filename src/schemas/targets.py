from typing import Literal
from pydantic import BaseModel, Field


class SliceBase(BaseModel):
    account_id: str
    allocation_kind: Literal["amount", "percent"]
    allocation_value: float = Field(ge=0)


class SliceCreate(SliceBase):
    pass


class SliceUpdate(BaseModel):
    account_id: str | None = None
    allocation_kind: Literal["amount", "percent"] | None = None
    allocation_value: float | None = Field(default=None, ge=0)


class SliceResponse(SliceBase):
    id: int


class TargetBase(BaseModel):
    name: str
    target_amount: float = Field(gt=0)
    rate_override: float | None = None  # €/mois


class TargetCreate(TargetBase):
    type: Literal["asset", "bucket"]
    asset_account_id: str | None = None
    asset_symbol: str | None = None
    slices: list[SliceCreate] = []


class TargetUpdate(BaseModel):
    name: str | None = None
    target_amount: float | None = Field(default=None, gt=0)
    rate_override: float | None = None
    archived: bool | None = None


class TargetResponse(TargetBase):
    id: int
    type: Literal["asset", "bucket"]
    asset_account_id: str | None = None
    asset_symbol: str | None = None
    archived: bool
    created_at: str
    slices: list[SliceResponse] = []


class HistoryPoint(BaseModel):
    date: str  # ISO YYYY-MM-DD
    value: float


class ProgressionResponse(BaseModel):
    target_id: int
    target_amount: float
    current_value: float
    progress_pct: float
    rate: float                # €/mois
    rate_source: Literal["auto", "override"]
    eta_months: float | None   # NULL si rythme insuffisant ou atteint
    eta_status: Literal["reached", "ok", "insufficient"]
    history: list[HistoryPoint]
