from datetime import date as _date
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, insert, update, delete

from src.api import deps
from src.api.middleware import get_current_user, AuthUser
from src.db.models import budget_sections, budget_items, projection_settings
from src.schemas.budget import (
    SectionCreate, SectionUpdate, SectionResponse,
    ItemCreate, ItemUpdate, ItemResponse,
    BudgetView, BudgetTotals, ApplyToProjectionPayload,
)
from src.services.budget_compose import compose_budget

router = APIRouter(prefix="/api/budget", tags=["budget"])


def _reject_virtual(section_id_or_item_id):
    if isinstance(section_id_or_item_id, str) and section_id_or_item_id.startswith("virtual:"):
        raise HTTPException(400, "Les sections/items virtuels (prêts) ne sont pas éditables")


@router.get("", response_model=BudgetView)
def get_budget(user: AuthUser = Depends(get_current_user)):
    engine = deps.get_ledger(user.id)
    view = compose_budget(engine, today=_date.today())
    return BudgetView(
        sections=[
            SectionResponse(
                id=s["id"], name=s["name"], section_type=s["section_type"],
                position=s["position"], is_virtual=s["is_virtual"],
                items=[ItemResponse(**it) for it in s["items"]],
            ) for s in view["sections"]
        ],
        totals=BudgetTotals(**view["totals"]),
    )


@router.post("/sections", response_model=SectionResponse, status_code=status.HTTP_201_CREATED)
def create_section(payload: SectionCreate, user: AuthUser = Depends(get_current_user)):
    engine = deps.get_ledger(user.id)
    with engine.begin() as conn:
        result = conn.execute(insert(budget_sections).values(
            name=payload.name, section_type=payload.section_type, position=payload.position,
        ))
        sid = result.inserted_primary_key[0]
    return SectionResponse(
        id=sid, name=payload.name, section_type=payload.section_type,
        position=payload.position, is_virtual=False, items=[],
    )


@router.put("/sections/{section_id}", response_model=SectionResponse)
def update_section(section_id: str, payload: SectionUpdate, user: AuthUser = Depends(get_current_user)):
    _reject_virtual(section_id)
    try:
        sid = int(section_id)
    except ValueError:
        raise HTTPException(400, "section_id invalide")
    engine = deps.get_ledger(user.id)
    values = payload.model_dump(exclude_unset=True)
    with engine.begin() as conn:
        existing = conn.execute(select(budget_sections).where(budget_sections.c.id == sid)).fetchone()
        if not existing:
            raise HTTPException(404, "Section introuvable")
        if values:
            conn.execute(update(budget_sections).where(budget_sections.c.id == sid).values(**values))
        row = conn.execute(select(budget_sections).where(budget_sections.c.id == sid)).fetchone()
    return SectionResponse(
        id=row.id, name=row.name, section_type=row.section_type,
        position=row.position, is_virtual=False, items=[],
    )


@router.delete("/sections/{section_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_section(section_id: str, user: AuthUser = Depends(get_current_user)):
    _reject_virtual(section_id)
    try:
        sid = int(section_id)
    except ValueError:
        raise HTTPException(400, "section_id invalide")
    engine = deps.get_ledger(user.id)
    with engine.begin() as conn:
        existing = conn.execute(select(budget_sections).where(budget_sections.c.id == sid)).fetchone()
        if not existing:
            raise HTTPException(404, "Section introuvable")
        conn.execute(delete(budget_items).where(budget_items.c.section_id == sid))
        conn.execute(delete(budget_sections).where(budget_sections.c.id == sid))
    return None


@router.post("/sections/{section_id}/items", response_model=ItemResponse, status_code=status.HTTP_201_CREATED)
def create_item(section_id: str, payload: ItemCreate, user: AuthUser = Depends(get_current_user)):
    _reject_virtual(section_id)
    try:
        sid = int(section_id)
    except ValueError:
        raise HTTPException(400, "section_id invalide")
    engine = deps.get_ledger(user.id)
    with engine.begin() as conn:
        existing = conn.execute(select(budget_sections).where(budget_sections.c.id == sid)).fetchone()
        if not existing:
            raise HTTPException(404, "Section introuvable")
        result = conn.execute(insert(budget_items).values(
            section_id=sid, label=payload.label, amount=payload.amount, position=payload.position,
        ))
        iid = result.inserted_primary_key[0]
    return ItemResponse(id=iid, label=payload.label, amount=payload.amount,
                        position=payload.position, is_virtual=False)


@router.put("/items/{item_id}", response_model=ItemResponse)
def update_item(item_id: str, payload: ItemUpdate, user: AuthUser = Depends(get_current_user)):
    _reject_virtual(item_id)
    try:
        iid = int(item_id)
    except ValueError:
        raise HTTPException(400, "item_id invalide")
    engine = deps.get_ledger(user.id)
    values = payload.model_dump(exclude_unset=True)
    with engine.begin() as conn:
        existing = conn.execute(select(budget_items).where(budget_items.c.id == iid)).fetchone()
        if not existing:
            raise HTTPException(404, "Item introuvable")
        if values:
            conn.execute(update(budget_items).where(budget_items.c.id == iid).values(**values))
        row = conn.execute(select(budget_items).where(budget_items.c.id == iid)).fetchone()
    return ItemResponse(id=row.id, label=row.label, amount=row.amount,
                        position=row.position, is_virtual=False)


@router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_item(item_id: str, user: AuthUser = Depends(get_current_user)):
    _reject_virtual(item_id)
    try:
        iid = int(item_id)
    except ValueError:
        raise HTTPException(400, "item_id invalide")
    engine = deps.get_ledger(user.id)
    with engine.begin() as conn:
        existing = conn.execute(select(budget_items).where(budget_items.c.id == iid)).fetchone()
        if not existing:
            raise HTTPException(404, "Item introuvable")
        conn.execute(delete(budget_items).where(budget_items.c.id == iid))
    return None


@router.post("/apply-to-projection")
def apply_to_projection(payload: ApplyToProjectionPayload, user: AuthUser = Depends(get_current_user)):
    if abs(payload.cash_share + payload.market_share - 1.0) > 0.001:
        raise HTTPException(400, "cash_share + market_share doivent sommer à 1.0")
    engine = deps.get_ledger(user.id)
    view = compose_budget(engine, today=_date.today())
    capacity = max(0.0, view["totals"]["investment_capacity"])
    cash_contrib = round(capacity * payload.cash_share, 2)
    market_contrib = round(capacity * payload.market_share, 2)
    with engine.begin() as conn:
        existing = conn.execute(select(projection_settings).where(projection_settings.c.id == 1)).fetchone()
        if not existing:
            conn.execute(insert(projection_settings).values(
                id=1, cash_monthly_contribution=cash_contrib,
                market_monthly_contribution=market_contrib,
            ))
        else:
            conn.execute(update(projection_settings).where(projection_settings.c.id == 1).values(
                cash_monthly_contribution=cash_contrib,
                market_monthly_contribution=market_contrib,
            ))
    return {
        "cash_monthly_contribution": cash_contrib,
        "market_monthly_contribution": market_contrib,
        "investment_capacity": capacity,
    }
