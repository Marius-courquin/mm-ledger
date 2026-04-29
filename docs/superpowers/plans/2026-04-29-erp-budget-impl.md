# Module Budget — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development.

**Goal:** Implémenter le module Budget (sections custom revenus/charges fixes/charges variables, items mensuels, section virtuelle "Prêts" auto-générée, capacité d'investissement, bouton "Appliquer à la projection") — backend + frontend.

**Architecture:** Tables `budget_sections` + `budget_items`. Section virtuelle "Prêts" injectée à la lecture (pas stockée). Service `compose_budget` pour assembler la vue. Routes `/api/budget`. Page React `/budget` avec 3 colonnes (revenus / fixes / variables) + footer capacité.

**Spec source:** `docs/superpowers/specs/2026-04-27-erp-budget-design.md`

**File map:**
- Modify: `src/db/models.py` (tables `budget_sections`, `budget_items`)
- Create: `src/schemas/budget.py`
- Create: `src/services/budget_compose.py`
- Create: `src/api/budget.py`
- Modify: `src/api/router.py`
- Create: `tests/test_api_budget.py`
- Create: `frontend/src/lib/budget.ts`
- Create: `frontend/src/api/budget.ts`
- Create: `frontend/src/pages/Budget.tsx`
- Create: `frontend/src/components/BudgetCard.tsx`
- Modify: `frontend/src/App.tsx`, `frontend/src/layouts/Sidebar.tsx`, `frontend/src/pages/Dashboard.tsx`
- Modify: `CLAUDE.md`

---

## Task 1 : Tables `budget_sections` + `budget_items`

**Files:** `src/db/models.py`, `tests/test_db.py`

- [ ] **Test smoke** :

```python
def test_budget_tables_created(tmp_path):
    from src.db.engine import create_engine_and_tables
    from src.db.models import budget_sections, budget_items
    from sqlalchemy import inspect

    engine = create_engine_and_tables(tmp_path / "ledger.db")
    insp = inspect(engine)
    assert "budget_sections" in insp.get_table_names()
    assert "budget_items" in insp.get_table_names()
    cols = {c["name"] for c in insp.get_columns("budget_sections")}
    assert {"id", "name", "section_type", "position"} <= cols
    cols = {c["name"] for c in insp.get_columns("budget_items")}
    assert {"id", "section_id", "label", "amount", "position"} <= cols
```

- [ ] **Tables** dans `src/db/models.py` :

```python
budget_sections = Table(
    "budget_sections", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("name", Text, nullable=False),
    Column("section_type", Text, nullable=False),  # 'income' | 'fixed_expense' | 'variable_expense'
    Column("position", Integer, nullable=False, server_default="0"),
)

budget_items = Table(
    "budget_items", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("section_id", Integer, ForeignKey("budget_sections.id", ondelete="CASCADE"), nullable=False),
    Column("label", Text, nullable=False),
    Column("amount", Real, nullable=False),
    Column("position", Integer, nullable=False, server_default="0"),
)

Index("idx_budget_items_section", budget_items.c.section_id)
```

- [ ] Pass + commit : `feat(budget): tables budget_sections + budget_items`.

---

## Task 2 : Schémas Pydantic

**Files:** Create `src/schemas/budget.py`

```python
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
```

- [ ] Smoke import + commit : `feat(budget): schémas Pydantic`.

---

## Task 3 : Service `compose_budget`

**Files:** Create `src/services/budget_compose.py`, `tests/test_budget_compose.py`

- [ ] **Tests** :

```python
from datetime import date
from sqlalchemy import insert
from src.db.engine import create_engine_and_tables
from src.db.models import budget_sections, budget_items, loans
from src.services.budget_compose import compose_budget


def test_empty_budget(tmp_path):
    engine = create_engine_and_tables(tmp_path / "ledger.db")
    view = compose_budget(engine, today=date(2026, 4, 29))
    # Aucun prêt → pas de section virtuelle
    assert view["sections"] == []
    assert view["totals"]["investment_capacity"] == 0


def test_basic_user_sections(tmp_path):
    engine = create_engine_and_tables(tmp_path / "ledger.db")
    with engine.begin() as conn:
        sec = conn.execute(insert(budget_sections).values(
            name="Salaires", section_type="income", position=0
        ))
        sid_income = sec.inserted_primary_key[0]
        conn.execute(insert(budget_items).values(
            section_id=sid_income, label="Salaire", amount=3500, position=0
        ))
        sec = conn.execute(insert(budget_sections).values(
            name="Logement", section_type="fixed_expense", position=0
        ))
        sid_fixed = sec.inserted_primary_key[0]
        conn.execute(insert(budget_items).values(
            section_id=sid_fixed, label="Loyer", amount=1000, position=0
        ))
        sec = conn.execute(insert(budget_sections).values(
            name="Alimentation", section_type="variable_expense", position=0
        ))
        sid_var = sec.inserted_primary_key[0]
        conn.execute(insert(budget_items).values(
            section_id=sid_var, label="Courses", amount=400, position=0
        ))
    view = compose_budget(engine, today=date(2026, 4, 29))
    totals = view["totals"]
    assert totals["income"] == 3500
    assert totals["fixed_expense"] == 1000
    assert totals["variable_expense"] == 400
    assert totals["expense"] == 1400
    assert totals["investment_capacity"] == 2100


def test_virtual_loan_section(tmp_path):
    engine = create_engine_and_tables(tmp_path / "ledger.db")
    with engine.begin() as conn:
        conn.execute(insert(loans).values(
            name="Auto", loan_type="auto", initial_capital=12000,
            monthly_payment=300, total_months=36, start_date="2025-01-01",
        ))
        conn.execute(insert(loans).values(
            name="Old", loan_type="conso", initial_capital=1000,
            monthly_payment=100, total_months=6, start_date="2010-01-01",
        ))  # terminé → ne doit pas apparaître
    view = compose_budget(engine, today=date(2026, 4, 29))
    virtuals = [s for s in view["sections"] if s["is_virtual"]]
    assert len(virtuals) == 1
    assert virtuals[0]["name"] == "Prêts"
    assert virtuals[0]["section_type"] == "fixed_expense"
    assert len(virtuals[0]["items"]) == 1
    assert virtuals[0]["items"][0]["label"] == "Auto"
    assert virtuals[0]["items"][0]["amount"] == 300
    assert virtuals[0]["items"][0]["is_virtual"] is True
    assert view["totals"]["fixed_expense"] == 300
    assert view["totals"]["investment_capacity"] == -300


def test_loans_added_to_user_fixed(tmp_path):
    engine = create_engine_and_tables(tmp_path / "ledger.db")
    with engine.begin() as conn:
        sec = conn.execute(insert(budget_sections).values(
            name="Salaires", section_type="income", position=0
        ))
        conn.execute(insert(budget_items).values(
            section_id=sec.inserted_primary_key[0], label="Salaire", amount=3000, position=0
        ))
        conn.execute(insert(loans).values(
            name="Immo", loan_type="immo", initial_capital=200000,
            monthly_payment=1200, total_months=240, start_date="2024-01-01",
        ))
    view = compose_budget(engine, today=date(2026, 4, 29))
    assert view["totals"]["income"] == 3000
    assert view["totals"]["fixed_expense"] == 1200  # uniquement la mensualité prêt
    assert view["totals"]["investment_capacity"] == 1800
```

- [ ] **Service** :

```python
# src/services/budget_compose.py
from datetime import date
from sqlalchemy import select
from sqlalchemy.engine import Engine

from src.db.models import budget_sections, budget_items, loans
from src.services.loan_calc import compute_loan_state


def compose_budget(engine: Engine, today: date) -> dict:
    """Assemble la vue Budget : sections user + section virtuelle Prêts + totaux."""
    with engine.connect() as conn:
        sec_rows = conn.execute(
            select(budget_sections).order_by(budget_sections.c.position, budget_sections.c.id)
        ).fetchall()
        item_rows = conn.execute(
            select(budget_items).order_by(budget_items.c.position, budget_items.c.id)
        ).fetchall()
        loan_rows = conn.execute(select(loans).where(loans.c.archived == 0)).fetchall()

    items_by_section: dict[int, list[dict]] = {}
    for r in item_rows:
        items_by_section.setdefault(r.section_id, []).append({
            "id": r.id, "label": r.label, "amount": float(r.amount),
            "position": r.position, "is_virtual": False,
        })

    sections: list[dict] = []
    for s in sec_rows:
        sections.append({
            "id": s.id, "name": s.name, "section_type": s.section_type,
            "position": s.position, "is_virtual": False,
            "items": items_by_section.get(s.id, []),
        })

    # Section virtuelle Prêts (un item par prêt actif)
    virtual_items = []
    for l in loan_rows:
        st = compute_loan_state({
            "start_date": l.start_date, "total_months": l.total_months,
            "monthly_payment": l.monthly_payment, "initial_capital": l.initial_capital,
            "archived": l.archived,
        }, today)
        if st["is_active"]:
            virtual_items.append({
                "id": f"virtual:loan:{l.id}",
                "label": l.name,
                "amount": float(l.monthly_payment),
                "position": 0,
                "is_virtual": True,
            })
    if virtual_items:
        sections.insert(0, {
            "id": "virtual:loans", "name": "Prêts",
            "section_type": "fixed_expense", "position": -1,
            "is_virtual": True, "items": virtual_items,
        })

    income = sum(it["amount"] for s in sections if s["section_type"] == "income" for it in s["items"])
    fixed = sum(it["amount"] for s in sections if s["section_type"] == "fixed_expense" for it in s["items"])
    variable = sum(it["amount"] for s in sections if s["section_type"] == "variable_expense" for it in s["items"])
    expense = fixed + variable
    capacity = income - expense

    return {
        "sections": sections,
        "totals": {
            "income": round(income, 2),
            "fixed_expense": round(fixed, 2),
            "variable_expense": round(variable, 2),
            "expense": round(expense, 2),
            "investment_capacity": round(capacity, 2),
        },
    }
```

- [ ] Pass + commit : `feat(budget): service compose_budget (avec section virtuelle Prêts)`.

---

## Task 4 : API CRUD + apply-to-projection

**Files:** Create `src/api/budget.py`, modify `src/api/router.py`, create `tests/test_api_budget.py`

- [ ] **Tests** :

```python
from sqlalchemy import insert
from src.api import deps
from src.auth import decode_jwt
from src.db.models import loans


def _setup(client):
    r = client.post("/api/auth/setup", json={"username": "admin", "password": "testpass123"})
    assert r.status_code == 201
    client.post("/api/vault/setup", json={"password": "test"})
    token = r.cookies.get("mm_session")
    return decode_jwt(token, deps.jwt_secret)["user_id"]


def test_get_empty_budget(client):
    _setup(client)
    r = client.get("/api/budget")
    assert r.status_code == 200
    body = r.json()
    assert body["sections"] == []
    assert body["totals"]["investment_capacity"] == 0


def test_crud_section_and_item(client):
    _setup(client)
    rs = client.post("/api/budget/sections", json={"name": "Salaires", "section_type": "income"})
    assert rs.status_code == 201
    sid = rs.json()["id"]
    ri = client.post(f"/api/budget/sections/{sid}/items", json={"label": "Salaire", "amount": 3500})
    assert ri.status_code == 201
    iid = ri.json()["id"]
    g = client.get("/api/budget").json()
    assert g["totals"]["income"] == 3500
    # Update item
    client.put(f"/api/budget/items/{iid}", json={"amount": 4000})
    g = client.get("/api/budget").json()
    assert g["totals"]["income"] == 4000
    # Delete item
    client.delete(f"/api/budget/items/{iid}")
    g = client.get("/api/budget").json()
    assert g["totals"]["income"] == 0
    # Update section
    client.put(f"/api/budget/sections/{sid}", json={"name": "Salaires renommé"})
    g = client.get("/api/budget").json()
    assert g["sections"][0]["name"] == "Salaires renommé"
    # Delete section (cascade items)
    client.delete(f"/api/budget/sections/{sid}")
    g = client.get("/api/budget").json()
    assert g["sections"] == []


def test_virtual_section_appears(client):
    user_id = _setup(client)
    engine = deps.get_ledger(user_id)
    with engine.begin() as conn:
        conn.execute(insert(loans).values(
            name="Auto", loan_type="auto", initial_capital=12000,
            monthly_payment=300, total_months=36, start_date="2025-01-01",
        ))
    g = client.get("/api/budget").json()
    virtuals = [s for s in g["sections"] if s["is_virtual"]]
    assert len(virtuals) == 1
    assert virtuals[0]["name"] == "Prêts"
    assert g["totals"]["fixed_expense"] == 300


def test_cant_edit_virtual_section(client):
    _setup(client)
    r = client.put("/api/budget/sections/virtual:loans", json={"name": "X"})
    assert r.status_code == 400
    r = client.delete("/api/budget/sections/virtual:loans")
    assert r.status_code == 400
    r = client.post("/api/budget/sections/virtual:loans/items", json={"label": "X", "amount": 1})
    assert r.status_code == 400
    r = client.put("/api/budget/items/virtual:loan:1", json={"amount": 100})
    assert r.status_code == 400
    r = client.delete("/api/budget/items/virtual:loan:1")
    assert r.status_code == 400


def test_apply_to_projection(client):
    _setup(client)
    rs = client.post("/api/budget/sections", json={"name": "Salaires", "section_type": "income"})
    sid = rs.json()["id"]
    client.post(f"/api/budget/sections/{sid}/items", json={"label": "Salaire", "amount": 1000})
    r = client.post("/api/budget/apply-to-projection", json={"cash_share": 0.3, "market_share": 0.7})
    assert r.status_code == 200
    body = r.json()
    assert body["cash_monthly_contribution"] == 300
    assert body["market_monthly_contribution"] == 700
    # Vérifie que projection_settings a bien été MAJ
    s = client.get("/api/projection/settings").json()
    assert s["settings"]["cash_monthly_contribution"] == 300
    assert s["settings"]["market_monthly_contribution"] == 700


def test_apply_to_projection_invalid_shares(client):
    _setup(client)
    r = client.post("/api/budget/apply-to-projection", json={"cash_share": 0.5, "market_share": 0.6})
    assert r.status_code == 400


def test_unauth(client):
    r = client.get("/api/budget")
    assert r.status_code == 401
```

- [ ] **API** :

```python
# src/api/budget.py
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
```

- [ ] Wire router + commit : `feat(budget): API CRUD + apply-to-projection`.

---

## Task 5 : Frontend types + client

**Files:** Create `frontend/src/lib/budget.ts`, `frontend/src/api/budget.ts`

- [ ] **Types** :

```typescript
// frontend/src/lib/budget.ts
export type SectionType = 'income' | 'fixed_expense' | 'variable_expense';

export interface BudgetItem {
  id: number | string;
  label: string;
  amount: number;
  position: number;
  is_virtual: boolean;
}

export interface BudgetSection {
  id: number | string;
  name: string;
  section_type: SectionType;
  position: number;
  is_virtual: boolean;
  items: BudgetItem[];
}

export interface BudgetTotals {
  income: number;
  fixed_expense: number;
  variable_expense: number;
  expense: number;
  investment_capacity: number;
}

export interface BudgetView {
  sections: BudgetSection[];
  totals: BudgetTotals;
}

export const SECTION_TYPE_LABELS: Record<SectionType, string> = {
  income: 'Revenus',
  fixed_expense: 'Charges fixes',
  variable_expense: 'Charges variables',
};
```

- [ ] **Client** :

```typescript
// frontend/src/api/budget.ts
import { api } from './client';
import type { BudgetView, BudgetSection, BudgetItem, SectionType } from '../lib/budget';

export function getBudget(): Promise<BudgetView> {
  return api.get<BudgetView>('/budget');
}

export function createSection(payload: { name: string; section_type: SectionType; position?: number }): Promise<BudgetSection> {
  return api.post<BudgetSection>('/budget/sections', payload);
}

export function updateSection(id: number, patch: Partial<{ name: string; section_type: SectionType; position: number }>): Promise<BudgetSection> {
  return api.put<BudgetSection>(`/budget/sections/${id}`, patch);
}

export function deleteSection(id: number): Promise<void> {
  return api.del(`/budget/sections/${id}`);
}

export function createItem(sectionId: number, payload: { label: string; amount: number; position?: number }): Promise<BudgetItem> {
  return api.post<BudgetItem>(`/budget/sections/${sectionId}/items`, payload);
}

export function updateItem(id: number, patch: Partial<{ label: string; amount: number; position: number }>): Promise<BudgetItem> {
  return api.put<BudgetItem>(`/budget/items/${id}`, patch);
}

export function deleteItem(id: number): Promise<void> {
  return api.del(`/budget/items/${id}`);
}

export function applyToProjection(cashShare: number, marketShare: number): Promise<{
  cash_monthly_contribution: number;
  market_monthly_contribution: number;
  investment_capacity: number;
}> {
  return api.post('/budget/apply-to-projection', { cash_share: cashShare, market_share: marketShare });
}
```

- [ ] Commit : `feat(budget): types + client API frontend`.

---

## Task 6 : Page `/budget`

**Files:** Create `frontend/src/pages/Budget.tsx`, modify `frontend/src/App.tsx`, `frontend/src/layouts/Sidebar.tsx`

**Convention** : HTML+Tailwind, tokens `mm-*`. Icône nav : `Wallet` ou `Calculator` (lucide-react).

- [ ] **Page** :

```tsx
import { useEffect, useState } from 'react';
import { Plus, Trash2, Lock, Link as LinkIcon } from 'lucide-react';
import { Link } from 'react-router-dom';
import {
  getBudget, createSection, updateSection, deleteSection,
  createItem, updateItem, deleteItem, applyToProjection,
} from '@/api/budget';
import type { BudgetView, BudgetSection, SectionType } from '@/lib/budget';
import { formatCurrency } from '@/lib/format';

const COLUMNS: { type: SectionType; label: string }[] = [
  { type: 'income', label: 'Revenus' },
  { type: 'fixed_expense', label: 'Charges fixes' },
  { type: 'variable_expense', label: 'Charges variables' },
];

export function Budget() {
  const [data, setData] = useState<BudgetView | null>(null);
  const [loading, setLoading] = useState(true);
  const [applyOpen, setApplyOpen] = useState(false);

  async function load() {
    setLoading(true);
    try { setData(await getBudget()); }
    finally { setLoading(false); }
  }

  useEffect(() => { load(); }, []);

  async function addSection(type: SectionType) {
    const name = prompt('Nom de la section :');
    if (!name?.trim()) return;
    await createSection({ name: name.trim(), section_type: type });
    load();
  }

  if (loading || !data) {
    return <div className="text-sm text-mm-text-muted">Chargement…</div>;
  }

  return (
    <div className="flex flex-col gap-6 pb-24">
      <div className="flex items-center justify-between">
        <h1 className="text-[28px] font-semibold text-mm-text">Budget</h1>
        <button
          onClick={() => setApplyOpen(true)}
          className="px-4 py-2 bg-mm-gold text-mm-bg text-sm font-semibold rounded-[8px] flex items-center gap-1.5 hover:opacity-90"
          disabled={data.totals.investment_capacity <= 0}
          title={data.totals.investment_capacity <= 0 ? 'Capacité d\'investissement nulle ou négative' : ''}
        >
          <LinkIcon size={14} /> Appliquer à la projection
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {COLUMNS.map(({ type, label }) => (
          <div key={type} className="flex flex-col gap-3">
            <div className="flex items-center justify-between">
              <h2 className="text-base font-semibold text-mm-text">{label}</h2>
              <button onClick={() => addSection(type)} className="text-xs text-mm-gold hover:underline">
                + Section
              </button>
            </div>
            {data.sections
              .filter((s) => s.section_type === type)
              .map((s) => (
                <SectionCard key={String(s.id)} section={s} onChange={load} />
              ))}
            {data.sections.filter((s) => s.section_type === type).length === 0 && (
              <div className="text-xs text-mm-text-muted bg-mm-surface border border-mm-border border-dashed rounded-[8px] px-3 py-4 text-center">
                Aucune section. Clique sur "+ Section" pour démarrer.
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Footer sticky avec totaux */}
      <div className="fixed bottom-0 left-0 right-0 bg-mm-surface border-t border-mm-border px-6 py-3 ml-[--sidebar-width,220px]">
        <div className="max-w-7xl mx-auto flex items-center justify-between text-sm">
          <div className="flex gap-6">
            <Total label="Revenus" value={data.totals.income} positive />
            <Total label="Charges" value={data.totals.expense} />
          </div>
          <div className="flex items-center gap-2">
            <span className="text-mm-text-muted text-xs">Capacité d'investissement</span>
            <span className={`text-2xl font-mono font-semibold ${
              data.totals.investment_capacity >= 0 ? 'text-mm-gain' : 'text-mm-loss'
            }`}>
              {formatCurrency(data.totals.investment_capacity, 'EUR')} / mois
            </span>
          </div>
        </div>
      </div>

      <ApplyModal
        isOpen={applyOpen}
        capacity={data.totals.investment_capacity}
        onClose={() => setApplyOpen(false)}
        onApplied={() => { setApplyOpen(false); load(); }}
      />
    </div>
  );
}

function Total({ label, value, positive }: { label: string; value: number; positive?: boolean }) {
  return (
    <div>
      <div className="text-xs text-mm-text-muted">{label}</div>
      <div className={`font-mono ${positive ? 'text-mm-gain' : 'text-mm-text'}`}>
        {formatCurrency(value, 'EUR')}
      </div>
    </div>
  );
}

function SectionCard({ section, onChange }: { section: BudgetSection; onChange: () => void }) {
  const total = section.items.reduce((s, i) => s + i.amount, 0);

  async function handleDeleteSection() {
    if (section.is_virtual) return;
    if (!confirm(`Supprimer la section "${section.name}" ?`)) return;
    await deleteSection(section.id as number);
    onChange();
  }

  async function handleAddItem() {
    if (section.is_virtual) return;
    const label = prompt('Libellé :');
    if (!label?.trim()) return;
    const amountStr = prompt('Montant (€) :');
    const amount = parseFloat(amountStr ?? '');
    if (!Number.isFinite(amount)) return;
    await createItem(section.id as number, { label: label.trim(), amount });
    onChange();
  }

  return (
    <div className="bg-mm-surface border border-mm-border rounded-[12px] flex flex-col">
      <div className="flex items-center justify-between px-3 py-2 border-b border-mm-border">
        <div className="flex items-center gap-2">
          {section.is_virtual && <Lock size={12} className="text-mm-text-muted" />}
          <span className="text-sm font-medium text-mm-text">{section.name}</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs font-mono text-mm-text-muted">{formatCurrency(total, 'EUR')}</span>
          {!section.is_virtual && (
            <>
              <button onClick={handleAddItem} className="text-mm-gold hover:opacity-80">
                <Plus size={14} />
              </button>
              <button onClick={handleDeleteSection} className="text-mm-text-muted hover:text-mm-loss">
                <Trash2 size={12} />
              </button>
            </>
          )}
        </div>
      </div>
      <div className="flex flex-col">
        {section.items.length === 0 && !section.is_virtual && (
          <div className="px-3 py-3 text-xs text-mm-text-muted text-center">Aucun item.</div>
        )}
        {section.is_virtual && section.items.length === 0 && (
          <div className="px-3 py-3 text-xs text-mm-text-muted text-center">Aucun prêt actif.</div>
        )}
        {section.items.map((it) => (
          <ItemRow key={String(it.id)} sectionId={section.id} item={it} virtual={section.is_virtual} onChange={onChange} />
        ))}
        {section.is_virtual && (
          <div className="px-3 py-2 text-[11px] text-mm-text-muted border-t border-mm-border">
            Auto-généré depuis <Link to="/prets" className="text-mm-gold hover:underline">Prêts</Link>.
          </div>
        )}
      </div>
    </div>
  );
}

function ItemRow({ item, virtual, onChange }: {
  sectionId: number | string;
  item: { id: number | string; label: string; amount: number; is_virtual: boolean };
  virtual: boolean;
  onChange: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [label, setLabel] = useState(item.label);
  const [amount, setAmount] = useState(String(item.amount));

  async function save() {
    const a = parseFloat(amount);
    if (!Number.isFinite(a) || !label.trim()) return;
    await updateItem(item.id as number, { label: label.trim(), amount: a });
    setEditing(false);
    onChange();
  }

  async function handleDelete() {
    if (virtual) return;
    if (!confirm(`Supprimer "${item.label}" ?`)) return;
    await deleteItem(item.id as number);
    onChange();
  }

  if (virtual) {
    return (
      <div className="flex items-center justify-between px-3 py-2 text-sm">
        <span className="text-mm-text-muted">{item.label}</span>
        <span className="font-mono text-mm-text">{formatCurrency(item.amount, 'EUR')}</span>
      </div>
    );
  }

  if (editing) {
    return (
      <div className="flex items-center gap-2 px-3 py-2 bg-mm-surface-elevated">
        <input
          className="flex-1 bg-mm-surface border border-mm-border rounded-[6px] px-2 py-1 text-sm text-mm-text focus:outline-none focus:border-mm-gold"
          value={label}
          onChange={(e) => setLabel(e.target.value)}
        />
        <input
          type="number"
          className="w-24 bg-mm-surface border border-mm-border rounded-[6px] px-2 py-1 text-sm text-mm-text font-mono text-right focus:outline-none focus:border-mm-gold"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
        />
        <button onClick={save} className="text-xs text-mm-gold">OK</button>
        <button onClick={() => { setEditing(false); setLabel(item.label); setAmount(String(item.amount)); }} className="text-xs text-mm-text-muted">×</button>
      </div>
    );
  }

  return (
    <div
      className="flex items-center justify-between px-3 py-2 text-sm hover:bg-mm-surface-elevated/50 cursor-pointer group"
      onClick={() => setEditing(true)}
    >
      <span className="text-mm-text">{item.label}</span>
      <div className="flex items-center gap-2">
        <span className="font-mono text-mm-text">{formatCurrency(item.amount, 'EUR')}</span>
        <button
          onClick={(e) => { e.stopPropagation(); handleDelete(); }}
          className="text-mm-text-muted opacity-0 group-hover:opacity-100 hover:text-mm-loss"
        >
          <Trash2 size={12} />
        </button>
      </div>
    </div>
  );
}

function ApplyModal({ isOpen, capacity, onClose, onApplied }: {
  isOpen: boolean; capacity: number; onClose: () => void; onApplied: () => void;
}) {
  const [marketShare, setMarketShare] = useState(1.0);
  const [submitting, setSubmitting] = useState(false);
  if (!isOpen) return null;
  const cashShare = 1 - marketShare;

  async function submit() {
    setSubmitting(true);
    try {
      await applyToProjection(cashShare, marketShare);
      onApplied();
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={onClose}>
      <div
        className="bg-mm-surface border border-mm-border rounded-[12px] p-6 w-full max-w-md mx-4 flex flex-col gap-4"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-lg font-semibold text-mm-text">Appliquer à la projection</h2>
        <p className="text-sm text-mm-text-muted">
          Capacité d'investissement : <span className="font-mono text-mm-text">{formatCurrency(capacity, 'EUR')} / mois</span>
        </p>
        <div className="flex flex-col gap-2">
          <label className="text-xs text-mm-text-muted">Répartition marché / cash</label>
          <input
            type="range" min={0} max={1} step={0.05}
            value={marketShare}
            onChange={(e) => setMarketShare(parseFloat(e.target.value))}
            className="accent-mm-gold"
          />
          <div className="flex justify-between text-xs text-mm-text-muted">
            <span>Cash : <span className="text-mm-text font-mono">{formatCurrency(capacity * cashShare, 'EUR')}</span> ({(cashShare * 100).toFixed(0)} %)</span>
            <span>Marché : <span className="text-mm-text font-mono">{formatCurrency(capacity * marketShare, 'EUR')}</span> ({(marketShare * 100).toFixed(0)} %)</span>
          </div>
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <button onClick={onClose} className="px-4 py-2 text-sm rounded-[8px] border border-mm-border text-mm-text-muted">
            Annuler
          </button>
          <button
            onClick={submit}
            disabled={submitting}
            className="px-4 py-2 bg-mm-gold text-mm-bg text-sm font-semibold rounded-[8px] disabled:opacity-50"
          >
            Appliquer
          </button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] Wire route + nav (icône `Wallet` lucide-react), build clean, commit : `feat(budget): page /budget (3 colonnes + footer + apply projection)`.

---

## Task 7 : Card Dashboard

**Files:** Create `frontend/src/components/BudgetCard.tsx`, modify `frontend/src/pages/Dashboard.tsx`

```tsx
// frontend/src/components/BudgetCard.tsx
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { getBudget } from '@/api/budget';
import type { BudgetTotals } from '@/lib/budget';
import { formatCurrency } from '@/lib/format';

export function BudgetCard() {
  const [totals, setTotals] = useState<BudgetTotals | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    getBudget()
      .then((b) => { if (!cancelled) setTotals(b.totals); })
      .catch(() => { if (!cancelled) setTotals(null); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  return (
    <div className="bg-mm-surface border border-mm-border rounded-[12px] px-5 py-4 flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <span className="font-medium text-mm-text">Budget</span>
        <Link to="/budget" className="text-sm text-mm-gold hover:underline">Voir →</Link>
      </div>
      {loading && <div className="text-sm text-mm-text-muted">Chargement…</div>}
      {!loading && (!totals || (totals.income === 0 && totals.expense === 0)) && (
        <div className="text-sm text-mm-text-muted">
          Pas encore de budget. <Link to="/budget" className="text-mm-gold hover:underline">En créer un</Link>.
        </div>
      )}
      {!loading && totals && (totals.income > 0 || totals.expense > 0) && (
        <>
          <div>
            <div className={`text-2xl font-mono ${totals.investment_capacity >= 0 ? 'text-mm-gain' : 'text-mm-loss'}`}>
              {formatCurrency(totals.investment_capacity, 'EUR')}
              <span className="text-sm text-mm-text-muted font-sans"> / mois</span>
            </div>
            <div className="text-xs text-mm-text-muted">Capacité d'investissement</div>
          </div>
          <div className="text-xs text-mm-text-muted">
            Revenus : <span className="text-mm-text font-mono">{formatCurrency(totals.income, 'EUR')}</span> ·
            Charges : <span className="text-mm-text font-mono">{formatCurrency(totals.expense, 'EUR')}</span>
          </div>
        </>
      )}
    </div>
  );
}
```

- [ ] Intégrer dans `Dashboard.tsx` à côté de `<ObjectifsCard />` et `<PretsCard />` (étendre la grille à 3 colonnes ou créer une 2e ligne 2x2). Build clean, commit : `feat(budget): card Budget sur le Dashboard`.

---

## Task 8 : CLAUDE.md + vérif finale

- [ ] Note dans CLAUDE.md (Gotchas, après note Module Projection) :

> **Module Budget (ERP)** : 4e et dernier module v1 du chantier ERP. Sections custom (revenus / charges fixes / charges variables), items mensuels, section virtuelle "Prêts" auto-générée à la lecture (un item par prêt actif, lecture seule, FK virtuel `virtual:loans`/`virtual:loan:{id}`). Capacité d'investissement = revenus − charges (incluant prêts). Bouton "Appliquer à la projection" → modale slider cash/marché → met à jour `projection_settings.cash/market_monthly_contribution`. API `/api/budget` (CRUD sections + items + apply-to-projection). Service `compose_budget`. Tables : `budget_sections`, `budget_items`. Spec : `docs/superpowers/specs/2026-04-27-erp-budget-design.md`.

- [ ] pytest + bun build verts.
- [ ] Commit : `docs: note module Budget dans CLAUDE.md`.
