from typing import Literal
from pydantic import BaseModel, Field


SectionType = Literal["income", "fixed_expense", "variable_expense"]


class ItemBase(BaseModel):
    label: str
    amount: float
    position: int = 0


class ItemCreate(ItemBase):
    pass


class ItemUpdate(BaseModel):
    label: str | None = None
    amount: float | None = None
    position: int | None = None


class ItemResponse(ItemBase):
    id: int | str  # int réel, ou "virtual:loan:{id}"
    is_virtual: bool = False


class SectionBase(BaseModel):
    name: str
    section_type: SectionType
    position: int = 0


class SectionCreate(SectionBase):
    pass


class SectionUpdate(BaseModel):
    name: str | None = None
    section_type: SectionType | None = None
    position: int | None = None


class SectionResponse(SectionBase):
    id: int | str  # int réel, ou "virtual:loans"
    is_virtual: bool = False
    items: list[ItemResponse] = []


class BudgetTotals(BaseModel):
    income: float
    fixed_expense: float
    variable_expense: float
    expense: float
    investment_capacity: float


class BudgetView(BaseModel):
    sections: list[SectionResponse]
    totals: BudgetTotals


class ApplyToProjectionPayload(BaseModel):
    cash_share: float = Field(ge=0, le=1)
    market_share: float = Field(ge=0, le=1)
