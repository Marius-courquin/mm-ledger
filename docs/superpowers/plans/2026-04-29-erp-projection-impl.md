# Module Projection — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development.

**Goal:** Implémenter le module Projection (simulation patrimoniale 5/10/20/30 ans, taux cash/marché + apports + mensualités prêts auto-déduites) — backend + frontend.

**Architecture:** Tables `projection_settings` (single row) + `account_classification` (overrides). Service pur `compute_projection` (boucle mois par mois). Classification cash/marché auto par `connector_type`. Routes `/api/projection`. Page React `/projection` avec sliders + courbe en aire empilée Recharts.

**Tech Stack:** Python / FastAPI / SQLAlchemy 2 Core / Pydantic v2 / pytest / React 19 / TS / Recharts / Tailwind.

**Spec source:** `docs/superpowers/specs/2026-04-27-erp-projection-design.md`

**File map:**
- Modify: `src/db/models.py` (ajout `projection_settings`, `account_classification`)
- Create: `src/schemas/projection.py`
- Create: `src/services/projection_calc.py`
- Create: `src/services/account_categorization.py`
- Create: `src/api/projection.py`
- Modify: `src/api/router.py`
- Create: `tests/test_api_projection.py`
- Create: `tests/test_projection_calc.py`
- Create: `frontend/src/lib/projection.ts`
- Create: `frontend/src/api/projection.ts`
- Create: `frontend/src/pages/Projection.tsx`
- Modify: `frontend/src/App.tsx` (route)
- Modify: `frontend/src/layouts/Sidebar.tsx` (nav)
- Modify: `CLAUDE.md`

---

## Task 1 : Tables `projection_settings` + `account_classification`

**Files:** Modify `src/db/models.py`, `tests/test_db.py`

- [ ] **Step 1 : Test smoke**

```python
def test_projection_tables_created(tmp_path):
    from src.db.engine import create_engine_and_tables
    from src.db.models import projection_settings, account_classification
    from sqlalchemy import inspect

    engine = create_engine_and_tables(tmp_path / "ledger.db")
    insp = inspect(engine)
    assert "projection_settings" in insp.get_table_names()
    assert "account_classification" in insp.get_table_names()
    cols = {c["name"] for c in insp.get_columns("projection_settings")}
    assert {"id", "cash_annual_rate", "market_annual_rate",
            "cash_monthly_contribution", "market_monthly_contribution",
            "horizon_years"} <= cols
    cols = {c["name"] for c in insp.get_columns("account_classification")}
    assert {"account_id", "category"} <= cols
```

- [ ] **Step 2 : Fail expected**
- [ ] **Step 3 : Ajouter dans `src/db/models.py`** :

```python
projection_settings = Table(
    "projection_settings", metadata,
    Column("id", Integer, primary_key=True),  # toujours = 1
    Column("cash_annual_rate", Real, nullable=False, server_default="0.02"),
    Column("market_annual_rate", Real, nullable=False, server_default="0.05"),
    Column("cash_monthly_contribution", Real, nullable=False, server_default="0"),
    Column("market_monthly_contribution", Real, nullable=False, server_default="0"),
    Column("horizon_years", Integer, nullable=False, server_default="10"),
)

account_classification = Table(
    "account_classification", metadata,
    Column("account_id", Text, primary_key=True),
    Column("category", Text, nullable=False),  # 'cash' | 'market'
)
```

- [ ] **Step 4 : Pass + commit** : `feat(projection): tables projection_settings + account_classification`

---

## Task 2 : Schémas Pydantic

**Files:** Create `src/schemas/projection.py`

- [ ] **Contenu** :

```python
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
```

- [ ] **Smoke import + commit** : `feat(projection): schémas Pydantic`

---

## Task 3 : Service `account_categorization`

**Files:** Create `src/services/account_categorization.py`, `tests/test_account_categorization.py`

- [ ] **Tests** :

```python
from src.db.engine import create_engine_and_tables
from src.db.models import accounts, connectors, account_classification
from sqlalchemy import insert
from src.services.account_categorization import categorize_accounts


def _seed(tmp_path, accs, overrides=None):
    engine = create_engine_and_tables(tmp_path / "ledger.db")
    with engine.begin() as conn:
        seen_connectors = set()
        for acc_id, conn_type in accs:
            if conn_type not in seen_connectors:
                conn.execute(insert(connectors).values(id=f"c_{conn_type}", type=conn_type))
                seen_connectors.add(conn_type)
            conn.execute(insert(accounts).values(id=acc_id, connector_id=f"c_{conn_type}", name=acc_id, type="x"))
        for acc_id, cat in (overrides or []):
            conn.execute(insert(account_classification).values(account_id=acc_id, category=cat))
    return engine


def test_categorize_default(tmp_path):
    engine = _seed(tmp_path, [
        ("livret_a", "woob_bank"),
        ("cto_tr", "trade_republic"),
        ("ibkr_acc", "ibkr"),
        ("nordigen_acc", "banking"),
    ])
    cats = categorize_accounts(engine)
    by_id = {c["account_id"]: c for c in cats}
    assert by_id["livret_a"]["category"] == "cash"
    assert by_id["livret_a"]["auto"] is True
    assert by_id["nordigen_acc"]["category"] == "cash"
    assert by_id["cto_tr"]["category"] == "market"
    assert by_id["ibkr_acc"]["category"] == "market"


def test_categorize_with_override(tmp_path):
    engine = _seed(tmp_path,
        [("cto_tr", "trade_republic")],
        overrides=[("cto_tr", "cash")],
    )
    cats = categorize_accounts(engine)
    by_id = {c["account_id"]: c for c in cats}
    assert by_id["cto_tr"]["category"] == "cash"
    assert by_id["cto_tr"]["auto"] is False


def test_categorize_unknown_connector(tmp_path):
    """Connecteur inconnu → market par défaut, auto=True."""
    engine = _seed(tmp_path, [("acc", "future_broker")])
    cats = categorize_accounts(engine)
    assert cats[0]["category"] == "market"
    assert cats[0]["auto"] is True
```

- [ ] **Service** :

```python
# src/services/account_categorization.py
from sqlalchemy import select
from sqlalchemy.engine import Engine

from src.db.models import accounts, connectors, account_classification

CASH_CONNECTOR_TYPES = {"woob_bank", "banking"}


def categorize_accounts(engine: Engine) -> list[dict]:
    """Renvoie pour chaque compte sa catégorie cash|market et la source (auto|override)."""
    with engine.connect() as conn:
        rows = conn.execute(
            select(accounts.c.id, connectors.c.type)
            .join(connectors, accounts.c.connector_id == connectors.c.id)
        ).fetchall()
        overrides = {
            r.account_id: r.category
            for r in conn.execute(select(account_classification)).fetchall()
        }
    out = []
    for r in rows:
        if r.id in overrides:
            out.append({"account_id": r.id, "category": overrides[r.id], "auto": False})
        else:
            cat = "cash" if r.type in CASH_CONNECTOR_TYPES else "market"
            out.append({"account_id": r.id, "category": cat, "auto": True})
    return out
```

- [ ] **Pass + commit** : `feat(projection): service account_categorization`

---

## Task 4 : Service `compute_projection`

**Files:** Create `src/services/projection_calc.py`, `tests/test_projection_calc.py`

- [ ] **Tests** :

```python
from datetime import date
from src.services.projection_calc import compute_projection


def _settings(**kw):
    base = {
        "cash_annual_rate": 0.02,
        "market_annual_rate": 0.05,
        "cash_monthly_contribution": 0,
        "market_monthly_contribution": 0,
        "horizon_years": 10,
    }
    base.update(kw)
    return base


def test_zero_capital_zero_rate_zero_contrib():
    points = compute_projection(_settings(cash_annual_rate=0, market_annual_rate=0),
                                cash_initial=0, market_initial=0, loans=[],
                                today=date(2026, 4, 29))
    assert len(points) == 120  # 10 ans
    assert points[-1]["total"] == 0


def test_market_growth():
    """1000€ marché à 5%/an pendant 1 an → ~1051€."""
    points = compute_projection(_settings(market_annual_rate=0.05, horizon_years=1),
                                cash_initial=0, market_initial=1000, loans=[],
                                today=date(2026, 4, 29))
    assert len(points) == 12
    assert 1049 < points[-1]["market"] < 1052
    assert points[-1]["cash"] == 0


def test_cash_with_monthly_contribution():
    """0€ cash + 100€/mois pendant 12 mois sans intérêt → 1200€."""
    points = compute_projection(
        _settings(cash_annual_rate=0, market_annual_rate=0,
                  cash_monthly_contribution=100, horizon_years=1),
        cash_initial=0, market_initial=0, loans=[], today=date(2026, 4, 29))
    assert points[-1]["cash"] == 1200


def test_loan_monthly_deducted_from_cash():
    """Mensualité de prêt déduite du cash chaque mois."""
    loan = {"monthly_payment": 500, "end_date": "2030-01-01"}
    points = compute_projection(
        _settings(cash_annual_rate=0, market_annual_rate=0, horizon_years=1),
        cash_initial=10000, market_initial=0, loans=[loan], today=date(2026, 4, 29))
    # 12 mois de 500€ déduits → 10000 - 6000 = 4000
    assert points[-1]["cash"] == 4000
    assert points[-1]["loan_monthly_active"] == 500


def test_loan_ends_during_horizon():
    """Prêt qui se termine dans 6 mois ne se déduit plus après."""
    loan = {"monthly_payment": 500, "end_date": "2026-10-29"}  # ~6 mois après today
    points = compute_projection(
        _settings(cash_annual_rate=0, market_annual_rate=0, horizon_years=1),
        cash_initial=10000, market_initial=0, loans=[loan], today=date(2026, 4, 29))
    # le 12e mois, le prêt n'est plus actif
    last = points[-1]
    assert last["loan_monthly_active"] == 0
    # cash final > 4000 puisque 6 mois sans déduction
    assert last["cash"] > 4000


def test_negative_cash_allowed():
    """Cash peut devenir négatif sans erreur."""
    loan = {"monthly_payment": 5000, "end_date": "2040-01-01"}
    points = compute_projection(
        _settings(cash_annual_rate=0, market_annual_rate=0, horizon_years=1),
        cash_initial=1000, market_initial=0, loans=[loan], today=date(2026, 4, 29))
    assert points[-1]["cash"] < 0  # non bloquant


def test_horizon_30_years_yields_360_points():
    points = compute_projection(_settings(horizon_years=30),
                                cash_initial=0, market_initial=0, loans=[], today=date(2026, 4, 29))
    assert len(points) == 360
```

- [ ] **Service** :

```python
# src/services/projection_calc.py
from datetime import date
from dateutil.relativedelta import relativedelta


def compute_projection(
    settings: dict,
    cash_initial: float,
    market_initial: float,
    loans: list[dict],
    today: date,
) -> list[dict]:
    """Boucle mois par mois sur horizon_years × 12.

    loans: liste de {"monthly_payment": float, "end_date": "YYYY-MM-DD"}.
    À chaque mois t, on calcule la somme des mensualités des prêts encore actifs
    (end_date > today + t mois).
    """
    horizon_months = settings["horizon_years"] * 12
    cash_monthly_rate = (1 + settings["cash_annual_rate"]) ** (1 / 12) - 1
    market_monthly_rate = (1 + settings["market_annual_rate"]) ** (1 / 12) - 1

    cash_t = float(cash_initial)
    market_t = float(market_initial)

    points: list[dict] = []
    for m in range(horizon_months):
        as_of = today + relativedelta(months=m + 1)
        loan_monthly_active = sum(
            float(l["monthly_payment"])
            for l in loans
            if date.fromisoformat(l["end_date"]) > as_of
        )
        cash_t = cash_t * (1 + cash_monthly_rate) + settings["cash_monthly_contribution"] - loan_monthly_active
        market_t = market_t * (1 + market_monthly_rate) + settings["market_monthly_contribution"]
        points.append({
            "month_offset": m + 1,
            "cash": round(cash_t, 2),
            "market": round(market_t, 2),
            "total": round(cash_t + market_t, 2),
            "loan_monthly_active": round(loan_monthly_active, 2),
        })
    return points
```

- [ ] **Pass + commit** : `feat(projection): service compute_projection`

---

## Task 5 : API `/api/projection`

**Files:** Create `src/api/projection.py`, modify `src/api/router.py`, create `tests/test_api_projection.py`

- [ ] **Tests** :

```python
from sqlalchemy import insert
from src.db.models import accounts, connectors, balance_snapshots, loans
from src.api import deps
from src.auth import decode_jwt


def _setup(client):
    r = client.post("/api/auth/setup", json={"username": "admin", "password": "testpass123"})
    assert r.status_code == 201
    client.post("/api/vault/setup", json={"password": "test"})
    token = r.cookies.get("mm_session")
    return decode_jwt(token, deps.jwt_secret)["user_id"]


def _seed_accounts(user_id):
    engine = deps.get_ledger(user_id)
    with engine.begin() as conn:
        conn.execute(insert(connectors).values(id="bp", type="woob_bank"))
        conn.execute(insert(connectors).values(id="tr", type="trade_republic"))
        conn.execute(insert(accounts).values(id="livret", connector_id="bp", name="Livret", type="cash"))
        conn.execute(insert(accounts).values(id="cto", connector_id="tr", name="CTO", type="cto"))
        conn.execute(insert(balance_snapshots).values(
            account_id="livret", date="2026-04-29", cash=5000, positions_value=0, total_value=5000, positions=[],
        ))
        conn.execute(insert(balance_snapshots).values(
            account_id="cto", date="2026-04-29", cash=200, positions_value=10000, total_value=10200, positions=[],
        ))


def test_get_settings_default(client):
    _setup(client)
    r = client.get("/api/projection/settings")
    assert r.status_code == 200
    body = r.json()
    assert body["settings"]["cash_annual_rate"] == 0.02
    assert body["settings"]["market_annual_rate"] == 0.05
    assert body["settings"]["horizon_years"] == 10


def test_update_settings(client):
    _setup(client)
    r = client.put("/api/projection/settings", json={
        "cash_annual_rate": 0.03, "market_annual_rate": 0.07,
        "cash_monthly_contribution": 100, "market_monthly_contribution": 500,
        "horizon_years": 20
    })
    assert r.status_code == 200
    g = client.get("/api/projection/settings").json()
    assert g["settings"]["cash_annual_rate"] == 0.03
    assert g["settings"]["horizon_years"] == 20


def test_compute_projection(client):
    user_id = _setup(client)
    _seed_accounts(user_id)
    r = client.get("/api/projection/compute")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["starting_state"]["cash"] == 5000
    assert body["starting_state"]["market"] == 10200
    assert body["starting_state"]["loan_monthly"] == 0
    assert len(body["points"]) == 120


def test_compute_with_loan(client):
    user_id = _setup(client)
    _seed_accounts(user_id)
    engine = deps.get_ledger(user_id)
    with engine.begin() as conn:
        conn.execute(insert(loans).values(
            name="Auto", loan_type="auto", initial_capital=10000,
            monthly_payment=300, total_months=36, start_date="2024-01-01"
        ))
    r = client.get("/api/projection/compute")
    body = r.json()
    assert body["starting_state"]["loan_monthly"] == 300


def test_account_override(client):
    user_id = _setup(client)
    _seed_accounts(user_id)
    # cto par défaut = market → on l'override en cash
    r = client.post("/api/projection/account-override", json={"account_id": "cto", "category": "cash"})
    assert r.status_code == 204
    s = client.get("/api/projection/settings").json()
    cls = {c["account_id"]: c for c in s["classifications"]}
    assert cls["cto"]["category"] == "cash"
    assert cls["cto"]["auto"] is False
    cmp = client.get("/api/projection/compute").json()
    assert cmp["starting_state"]["cash"] == 5000 + 10200
    assert cmp["starting_state"]["market"] == 0


def test_remove_override(client):
    user_id = _setup(client)
    _seed_accounts(user_id)
    client.post("/api/projection/account-override", json={"account_id": "cto", "category": "cash"})
    r = client.delete("/api/projection/account-override/cto")
    assert r.status_code == 204
    s = client.get("/api/projection/settings").json()
    cls = {c["account_id"]: c for c in s["classifications"]}
    assert cls["cto"]["category"] == "market"
    assert cls["cto"]["auto"] is True


def test_unauth(client):
    r = client.get("/api/projection/settings")
    assert r.status_code == 401
```

- [ ] **Routes** (`src/api/projection.py`) :

```python
from datetime import date as _date
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, insert, update, delete

from src.api import deps
from src.api.middleware import get_current_user, AuthUser
from src.db.models import (
    projection_settings, account_classification,
    accounts, connectors, balance_snapshots, loans,
)
from src.schemas.projection import (
    ProjectionSettings, ProjectionSettingsUpdate, ProjectionResult,
    ProjectionPoint, ProjectionStartingState, AccountOverride, AccountCategorization,
)
from src.services.projection_calc import compute_projection
from src.services.account_categorization import categorize_accounts
from src.services.loan_calc import compute_loan_state

router = APIRouter(prefix="/api/projection", tags=["projection"])


def _ensure_settings_row(conn):
    """Crée la row id=1 si absente, renvoie la row."""
    row = conn.execute(select(projection_settings).where(projection_settings.c.id == 1)).fetchone()
    if not row:
        conn.execute(insert(projection_settings).values(id=1))
        row = conn.execute(select(projection_settings).where(projection_settings.c.id == 1)).fetchone()
    return row


def _settings_to_dict(row) -> dict:
    return {
        "cash_annual_rate": row.cash_annual_rate,
        "market_annual_rate": row.market_annual_rate,
        "cash_monthly_contribution": row.cash_monthly_contribution,
        "market_monthly_contribution": row.market_monthly_contribution,
        "horizon_years": row.horizon_years,
    }


def _starting_state(engine, classifications: list[dict]) -> tuple[float, float, float, list[dict]]:
    """Renvoie (cash_initial, market_initial, loan_monthly_total, active_loans_for_proj)."""
    cls_by_acc = {c["account_id"]: c["category"] for c in classifications}
    cash_total = 0.0
    market_total = 0.0
    with engine.connect() as conn:
        # Solde le plus récent par compte
        for acc_id, cat in cls_by_acc.items():
            stmt = (
                select(balance_snapshots.c.total_value)
                .where(balance_snapshots.c.account_id == acc_id)
                .order_by(balance_snapshots.c.date.desc())
                .limit(1)
            )
            row = conn.execute(stmt).fetchone()
            v = float(row.total_value) if row and row.total_value is not None else 0.0
            if cat == "cash":
                cash_total += v
            else:
                market_total += v
        loan_rows = conn.execute(select(loans).where(loans.c.archived == 0)).fetchall()
    today = _date.today()
    proj_loans = []
    loan_monthly_total = 0.0
    for l in loan_rows:
        st = compute_loan_state({
            "start_date": l.start_date, "total_months": l.total_months,
            "monthly_payment": l.monthly_payment, "initial_capital": l.initial_capital,
            "archived": l.archived,
        }, today)
        if st["is_active"]:
            loan_monthly_total += float(l.monthly_payment)
            proj_loans.append({
                "monthly_payment": float(l.monthly_payment),
                "end_date": st["end_date"],
            })
    return cash_total, market_total, loan_monthly_total, proj_loans


@router.get("/settings")
def get_settings(user: AuthUser = Depends(get_current_user)):
    engine = deps.get_ledger(user.id)
    with engine.begin() as conn:
        row = _ensure_settings_row(conn)
    classifications = categorize_accounts(engine)
    return {
        "settings": _settings_to_dict(row),
        "classifications": classifications,
    }


@router.put("/settings")
def update_settings(payload: ProjectionSettingsUpdate, user: AuthUser = Depends(get_current_user)):
    engine = deps.get_ledger(user.id)
    values = payload.model_dump(exclude_unset=True)
    with engine.begin() as conn:
        _ensure_settings_row(conn)
        if values:
            conn.execute(update(projection_settings).where(projection_settings.c.id == 1).values(**values))
        row = conn.execute(select(projection_settings).where(projection_settings.c.id == 1)).fetchone()
    return {"settings": _settings_to_dict(row)}


@router.get("/compute", response_model=ProjectionResult)
def compute(user: AuthUser = Depends(get_current_user)):
    engine = deps.get_ledger(user.id)
    with engine.begin() as conn:
        row = _ensure_settings_row(conn)
    settings = _settings_to_dict(row)
    classifications = categorize_accounts(engine)
    cash_initial, market_initial, loan_monthly, proj_loans = _starting_state(engine, classifications)
    today = _date.today()
    points = compute_projection(settings, cash_initial, market_initial, proj_loans, today)
    return ProjectionResult(
        settings=ProjectionSettings(**settings),
        starting_state=ProjectionStartingState(
            cash=round(cash_initial, 2), market=round(market_initial, 2),
            loan_monthly=round(loan_monthly, 2),
        ),
        points=[ProjectionPoint(**p) for p in points],
        classifications=[AccountCategorization(**c) for c in classifications],
    )


@router.post("/account-override", status_code=status.HTTP_204_NO_CONTENT)
def set_override(payload: AccountOverride, user: AuthUser = Depends(get_current_user)):
    engine = deps.get_ledger(user.id)
    with engine.begin() as conn:
        existing = conn.execute(
            select(account_classification).where(account_classification.c.account_id == payload.account_id)
        ).fetchone()
        if existing:
            conn.execute(
                update(account_classification)
                .where(account_classification.c.account_id == payload.account_id)
                .values(category=payload.category)
            )
        else:
            conn.execute(insert(account_classification).values(
                account_id=payload.account_id, category=payload.category,
            ))
    return None


@router.delete("/account-override/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
def clear_override(account_id: str, user: AuthUser = Depends(get_current_user)):
    engine = deps.get_ledger(user.id)
    with engine.begin() as conn:
        conn.execute(
            delete(account_classification).where(account_classification.c.account_id == account_id)
        )
    return None
```

- [ ] **Wire router** + pass + commit : `feat(projection): API settings + compute + override`

---

## Task 6 : Frontend types + client

**Files:** Create `frontend/src/lib/projection.ts`, `frontend/src/api/projection.ts`

- [ ] **Types** :

```typescript
// frontend/src/lib/projection.ts
export type ProjectionCategory = 'cash' | 'market';

export interface ProjectionSettings {
  cash_annual_rate: number;
  market_annual_rate: number;
  cash_monthly_contribution: number;
  market_monthly_contribution: number;
  horizon_years: number;
}

export interface AccountCategorization {
  account_id: string;
  category: ProjectionCategory;
  auto: boolean;
}

export interface ProjectionPoint {
  month_offset: number;
  cash: number;
  market: number;
  total: number;
  loan_monthly_active: number;
}

export interface ProjectionStartingState {
  cash: number;
  market: number;
  loan_monthly: number;
}

export interface ProjectionResult {
  settings: ProjectionSettings;
  starting_state: ProjectionStartingState;
  points: ProjectionPoint[];
  classifications: AccountCategorization[];
}

export interface ProjectionSettingsView {
  settings: ProjectionSettings;
  classifications: AccountCategorization[];
}
```

- [ ] **Client** :

```typescript
// frontend/src/api/projection.ts
import { api } from './client';
import type {
  ProjectionResult, ProjectionSettings, ProjectionSettingsView, ProjectionCategory,
} from '../lib/projection';

export function getProjectionSettings(): Promise<ProjectionSettingsView> {
  return api.get<ProjectionSettingsView>('/projection/settings');
}

export function updateProjectionSettings(patch: Partial<ProjectionSettings>): Promise<{ settings: ProjectionSettings }> {
  return api.put<{ settings: ProjectionSettings }>('/projection/settings', patch);
}

export function computeProjection(): Promise<ProjectionResult> {
  return api.get<ProjectionResult>('/projection/compute');
}

export function setAccountOverride(account_id: string, category: ProjectionCategory): Promise<void> {
  return api.post('/projection/account-override', { account_id, category });
}

export function clearAccountOverride(account_id: string): Promise<void> {
  return api.del(`/projection/account-override/${account_id}`);
}
```

- [ ] **Commit** : `feat(projection): types + client API frontend`

---

## Task 7 : Page `/projection` avec courbe Recharts

**Files:** Create `frontend/src/pages/Projection.tsx`, modify `frontend/src/App.tsx`, `frontend/src/layouts/Sidebar.tsx`

**Convention** : HTML+Tailwind avec tokens `mm-*`. Recharts pour la courbe (`AreaChart` empilée cash + market). Icône nav : `LineChart` (lucide-react).

- [ ] **Page** (`frontend/src/pages/Projection.tsx`) :

```tsx
import { useEffect, useMemo, useState } from 'react';
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from 'recharts';
import {
  computeProjection, updateProjectionSettings, setAccountOverride, clearAccountOverride,
} from '@/api/projection';
import type { ProjectionResult, ProjectionCategory } from '@/lib/projection';
import { formatCurrency } from '@/lib/format';

const HORIZON_OPTIONS = [5, 10, 20, 30];

export function Projection() {
  const [data, setData] = useState<ProjectionResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [showOverrides, setShowOverrides] = useState(false);

  async function load() {
    setLoading(true);
    try { setData(await computeProjection()); }
    finally { setLoading(false); }
  }

  useEffect(() => { load(); }, []);

  async function patchSettings(patch: Partial<typeof data['settings']>) {
    if (!data) return;
    await updateProjectionSettings(patch);
    load();
  }

  async function toggleOverride(account_id: string, currentCategory: ProjectionCategory, isAuto: boolean) {
    if (isAuto) {
      const newCat: ProjectionCategory = currentCategory === 'cash' ? 'market' : 'cash';
      await setAccountOverride(account_id, newCat);
    } else {
      await clearAccountOverride(account_id);
    }
    load();
  }

  const milestones = useMemo(() => {
    if (!data) return [];
    return [60, 120, 240, 360].map((m) => {
      const p = data.points.find((pt) => pt.month_offset === m);
      const years = m / 12;
      return { years, point: p };
    }).filter((x) => !!x.point);
  }, [data]);

  if (loading || !data) {
    return <div className="text-sm text-mm-text-muted">Chargement…</div>;
  }

  const { settings, starting_state, points, classifications } = data;
  const chartData = points.map((p) => ({
    label: `M+${p.month_offset}`,
    year: p.month_offset / 12,
    cash: p.cash,
    market: p.market,
    total: p.total,
  }));

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-[28px] font-semibold text-mm-text">Projection</h1>
        <button
          onClick={() => setShowOverrides((v) => !v)}
          className="px-4 py-2 text-sm rounded-[8px] border border-mm-border text-mm-text-muted hover:text-mm-text"
        >
          Classification des comptes
        </button>
      </div>

      {/* Capital de départ */}
      <div className="grid grid-cols-3 gap-4">
        <Stat label="Cash actuel" value={formatCurrency(starting_state.cash, 'EUR')} />
        <Stat label="Marché actuel" value={formatCurrency(starting_state.market, 'EUR')} />
        <Stat
          label="Mensualités prêts"
          value={`${formatCurrency(starting_state.loan_monthly, 'EUR')} / mois`}
          muted
        />
      </div>

      {/* Hypothèses */}
      <div className="bg-mm-surface border border-mm-border rounded-[12px] p-5 flex flex-col gap-4">
        <span className="text-sm font-medium text-mm-text">Hypothèses</span>
        <div className="grid grid-cols-2 gap-x-6 gap-y-4">
          <Slider
            label="Taux annuel cash"
            value={settings.cash_annual_rate * 100}
            min={0} max={10} step={0.1}
            suffix=" %"
            onChange={(v) => patchSettings({ cash_annual_rate: v / 100 })}
          />
          <Slider
            label="Taux annuel marché"
            value={settings.market_annual_rate * 100}
            min={0} max={15} step={0.1}
            suffix=" %"
            onChange={(v) => patchSettings({ market_annual_rate: v / 100 })}
          />
          <NumberInput
            label="Apport mensuel cash (€)"
            value={settings.cash_monthly_contribution}
            onChange={(v) => patchSettings({ cash_monthly_contribution: v })}
          />
          <NumberInput
            label="Apport mensuel marché (€)"
            value={settings.market_monthly_contribution}
            onChange={(v) => patchSettings({ market_monthly_contribution: v })}
          />
          <div className="col-span-2 flex items-center gap-3">
            <span className="text-xs text-mm-text-muted">Horizon</span>
            <div className="flex gap-1">
              {HORIZON_OPTIONS.map((h) => {
                const active = settings.horizon_years === h;
                return (
                  <button
                    key={h}
                    onClick={() => patchSettings({ horizon_years: h })}
                    className={`px-3 py-1.5 text-xs rounded-[6px] border ${
                      active
                        ? 'border-mm-gold text-mm-gold bg-mm-surface-elevated'
                        : 'border-mm-border text-mm-text-muted'
                    }`}
                  >
                    {h} ans
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      </div>

      {/* Courbe empilée */}
      <div className="bg-mm-surface border border-mm-border rounded-[12px] p-5">
        <div className="text-sm font-medium text-mm-text mb-3">Évolution projetée</div>
        <ResponsiveContainer width="100%" height={320}>
          <AreaChart data={chartData} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
            <defs>
              <linearGradient id="projCash" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="var(--mm-gain)" stopOpacity={0.5} />
                <stop offset="100%" stopColor="var(--mm-gain)" stopOpacity={0.05} />
              </linearGradient>
              <linearGradient id="projMarket" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="var(--mm-accent-gold)" stopOpacity={0.5} />
                <stop offset="100%" stopColor="var(--mm-accent-gold)" stopOpacity={0.05} />
              </linearGradient>
            </defs>
            <CartesianGrid stroke="#1a3d4d40" horizontal vertical={false} />
            <XAxis
              dataKey="year"
              tickFormatter={(y) => `${y.toFixed(0)} an${y >= 2 ? 's' : ''}`}
              axisLine={false} tickLine={false}
              tick={{ fill: 'rgba(226,207,234,0.5)', fontSize: 10 }}
            />
            <YAxis
              axisLine={false} tickLine={false}
              tick={{ fill: 'rgba(226,207,234,0.5)', fontSize: 10 }}
              tickFormatter={(v) => `${(v / 1000).toFixed(0)} k€`}
            />
            <Tooltip
              contentStyle={{ backgroundColor: '#143a42', border: '1px solid #1a3d4d', borderRadius: 8, color: '#f0ece4', fontSize: 12 }}
              formatter={(v: number, name: string) => [formatCurrency(v, 'EUR'), name === 'cash' ? 'Cash' : 'Marché']}
              labelFormatter={(y: number) => `Dans ${y.toFixed(1)} ans`}
            />
            <Legend wrapperStyle={{ fontSize: 11, color: '#e2cfea' }} />
            <Area type="monotone" dataKey="cash" stackId="1" name="Cash" stroke="var(--mm-gain)" fill="url(#projCash)" />
            <Area type="monotone" dataKey="market" stackId="1" name="Marché" stroke="var(--mm-accent-gold)" fill="url(#projMarket)" />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      {/* Cards "à X ans" */}
      <div className="grid grid-cols-4 gap-4">
        {milestones.map(({ years, point }) => (
          <div key={years} className="bg-mm-surface border border-mm-border rounded-[12px] p-4">
            <div className="text-xs text-mm-text-muted">À {years} ans</div>
            <div className="text-xl font-mono text-mm-text mt-1">
              {formatCurrency(point!.total, 'EUR')}
            </div>
            <div className="text-[11px] text-mm-text-muted mt-1">
              cash {formatCurrency(point!.cash, 'EUR')} · marché {formatCurrency(point!.market, 'EUR')}
            </div>
          </div>
        ))}
      </div>

      {showOverrides && (
        <div className="bg-mm-surface border border-mm-border rounded-[12px] p-5">
          <div className="text-sm font-medium text-mm-text mb-3">Classification des comptes</div>
          <p className="text-xs text-mm-text-muted mb-3">
            Auto = déduit du type de connecteur (banque → cash, courtier → marché). Clique pour basculer en override manuel.
          </p>
          <div className="grid grid-cols-2 gap-2">
            {classifications.map((c) => (
              <button
                key={c.account_id}
                onClick={() => toggleOverride(c.account_id, c.category, c.auto)}
                className="flex items-center justify-between px-3 py-2 bg-mm-surface-elevated rounded-[8px] hover:bg-mm-surface-elevated/70 text-left"
              >
                <span className="text-sm text-mm-text font-mono">{c.account_id}</span>
                <span className={`text-xs px-2 py-0.5 rounded-full ${
                  c.category === 'cash' ? 'bg-mm-gain/15 text-mm-gain' : 'bg-mm-gold/15 text-mm-gold'
                }`}>
                  {c.category} {c.auto ? '(auto)' : '(override)'}
                </span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function Stat({ label, value, muted }: { label: string; value: string; muted?: boolean }) {
  return (
    <div className="bg-mm-surface border border-mm-border rounded-[12px] px-5 py-4">
      <div className="text-xs text-mm-text-muted">{label}</div>
      <div className={`mt-1 font-mono ${muted ? 'text-lg text-mm-text-muted' : 'text-2xl text-mm-text'}`}>
        {value}
      </div>
    </div>
  );
}

function Slider({ label, value, min, max, step, suffix, onChange }: {
  label: string; value: number; min: number; max: number; step: number; suffix: string;
  onChange: (v: number) => void;
}) {
  const [local, setLocal] = useState(value);
  useEffect(() => { setLocal(value); }, [value]);
  return (
    <label className="flex flex-col gap-1.5">
      <div className="flex justify-between text-xs">
        <span className="text-mm-text-muted">{label}</span>
        <span className="text-mm-text font-mono">{local.toFixed(step < 1 ? 1 : 0)}{suffix}</span>
      </div>
      <input
        type="range"
        min={min} max={max} step={step} value={local}
        onChange={(e) => setLocal(parseFloat(e.target.value))}
        onMouseUp={(e) => onChange(parseFloat((e.target as HTMLInputElement).value))}
        onTouchEnd={(e) => onChange(parseFloat((e.target as HTMLInputElement).value))}
        className="accent-mm-gold"
      />
    </label>
  );
}

function NumberInput({ label, value, onChange }: {
  label: string; value: number; onChange: (v: number) => void;
}) {
  const [local, setLocal] = useState(String(value));
  useEffect(() => { setLocal(String(value)); }, [value]);
  return (
    <label className="flex flex-col gap-1">
      <span className="text-xs text-mm-text-muted">{label}</span>
      <input
        type="number" min={0}
        value={local}
        onChange={(e) => setLocal(e.target.value)}
        onBlur={() => {
          const v = parseFloat(local);
          if (!Number.isNaN(v) && v >= 0 && v !== value) onChange(v);
        }}
        className="px-3 py-2 bg-mm-surface-elevated border border-mm-border rounded-[8px] text-sm text-mm-text focus:outline-none focus:border-mm-gold"
      />
    </label>
  );
}
```

- [ ] **Wire route** dans `App.tsx` (`<Route path="/projection" element={<Projection />} />`) et nav dans `Sidebar.tsx` (entrée "Projection" avec icône `LineChart` de lucide-react, après "Prêts").

- [ ] **Build clean + commit** : `feat(projection): page /projection (sliders + courbe empilée)`

---

## Task 8 : CLAUDE.md + vérif finale

- [ ] Note dans CLAUDE.md (Gotchas) :

> **Module Projection (ERP)** : 3e module v1. Capital projeté à 5/10/20/30 ans. Sliders cash/marché (taux + apports), classification auto par `connector_type` (banking/woob_bank → cash, courtiers → market) avec overrides via `account_classification`. Mensualités prêts auto-déduites du cash, ajustées dynamiquement quand un prêt arrive à échéance dans l'horizon. Courbe AreaChart empilée. API `/api/projection` (settings GET/PUT, compute GET, override POST/DELETE). Service pur `compute_projection`. Tables : `projection_settings` (single row id=1), `account_classification`. Spec : `docs/superpowers/specs/2026-04-27-erp-projection-design.md`.

- [ ] pytest + bun run build verts.
- [ ] Commit : `docs: note module Projection dans CLAUDE.md`.
