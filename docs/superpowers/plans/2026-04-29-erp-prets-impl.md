# Module Prêts — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans.

**Goal:** Implémenter le module Prêts (suivi déclaratif simple, calculs calendaires, pas d'amortissement) — backend + frontend.

**Architecture:** Une table `loans` dans le ledger user, un service pur `compute_loan_state` pour les calculs calendaires (avec `dateutil.relativedelta`), 6 routes FastAPI dans `src/api/loans.py`, page React `/prets` + modale CRUD + card Dashboard.

**Tech Stack:** Python 3.12 / FastAPI / SQLAlchemy 2 Core / pytest / `python-dateutil` / React 19 / TS / Tailwind / Lucide icons.

**Spec source:** `docs/superpowers/specs/2026-04-27-erp-prets-design.md`

**File map:**
- Modify: `src/db/models.py` (ajout table `loans`)
- Create: `src/schemas/loans.py`
- Create: `src/services/loan_calc.py`
- Create: `src/api/loans.py`
- Modify: `src/api/router.py`
- Create: `tests/test_api_loans.py`
- Create: `tests/test_loan_calc.py`
- Create: `frontend/src/lib/loans.ts`
- Create: `frontend/src/api/loans.ts`
- Create: `frontend/src/pages/Prets.tsx`
- Create: `frontend/src/components/LoanFormModal.tsx`
- Create: `frontend/src/components/PretsCard.tsx`
- Modify: `frontend/src/App.tsx` (route)
- Modify: `frontend/src/layouts/Sidebar.tsx` (nav entry)
- Modify: `frontend/src/pages/Dashboard.tsx` (intégrer card)
- Modify: `CLAUDE.md` (note module)

---

## Task 1 : Table `loans`

**Files:** Modify `src/db/models.py`, `tests/test_db.py`

- [ ] **Step 1 : Test smoke**

```python
def test_loans_table_created(tmp_path):
    from src.db.engine import create_engine_and_tables
    from src.db.models import loans
    from sqlalchemy import inspect

    engine = create_engine_and_tables(tmp_path / "ledger.db")
    insp = inspect(engine)
    assert "loans" in insp.get_table_names()
    cols = {c["name"] for c in insp.get_columns("loans")}
    assert {"id", "name", "loan_type", "initial_capital", "monthly_payment",
            "total_months", "start_date", "archived", "created_at"} <= cols
```

- [ ] **Step 2 : Run, fail expected**

```bash
cd /Users/charles/Desktop/mm-ledger && source .venv/bin/activate && pytest tests/test_db.py::test_loans_table_created -v
```

- [ ] **Step 3 : Ajouter dans `src/db/models.py`** (à la suite des autres `Table(...)`, avant la fin du fichier) :

```python
loans = Table(
    "loans", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("name", Text, nullable=False),
    Column("loan_type", Text, nullable=False),  # 'immo' | 'conso' | 'auto' | 'other'
    Column("initial_capital", Real, nullable=False),
    Column("monthly_payment", Real, nullable=False),
    Column("total_months", Integer, nullable=False),
    Column("start_date", Text, nullable=False),  # ISO YYYY-MM-DD
    Column("archived", Integer, nullable=False, server_default="0"),
    Column("created_at", Text, server_default="(datetime('now'))"),
)
```

- [ ] **Step 4 : Pass + commit**

```bash
pytest tests/test_db.py::test_loans_table_created -v
git add src/db/models.py tests/test_db.py
git commit -m "feat(loans): table loans"
```

---

## Task 2 : Schémas Pydantic

**Files:** Create `src/schemas/loans.py`

- [ ] **Step 1 : Créer `src/schemas/loans.py`**

```python
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
```

- [ ] **Step 2 : Smoke import**

```bash
python -c "from src.schemas.loans import LoanCreate, LoanResponse, LoanSummary; print('OK')"
```

- [ ] **Step 3 : Commit**

```bash
git add src/schemas/loans.py
git commit -m "feat(loans): schémas Pydantic"
```

---

## Task 3 : Service `compute_loan_state`

**Files:** Create `src/services/loan_calc.py`, `tests/test_loan_calc.py`

- [ ] **Step 1 : Tests**

```python
# tests/test_loan_calc.py
from datetime import date
from src.services.loan_calc import compute_loan_state


def _loan(start="2020-01-01", total_months=240, monthly=1200, capital=250000, archived=False):
    return {
        "start_date": start,
        "total_months": total_months,
        "monthly_payment": monthly,
        "initial_capital": capital,
        "archived": int(archived),
    }


def test_state_in_progress():
    """Prêt 20 ans démarré il y a 6 ans, mensualité 1200."""
    state = compute_loan_state(_loan(start="2020-01-01"), today=date(2026, 1, 1))
    assert state["months_paid"] == 72
    assert state["months_remaining"] == 168
    assert state["amount_remaining"] == 168 * 1200
    assert state["end_date"] == "2040-01-01"
    assert 29.5 < state["progress_pct"] < 30.5
    assert state["is_active"] is True


def test_state_future_start():
    """Prêt qui commence demain → 0 payé."""
    state = compute_loan_state(_loan(start="2030-01-01"), today=date(2026, 1, 1))
    assert state["months_paid"] == 0
    assert state["months_remaining"] == 240
    assert state["progress_pct"] == 0.0
    assert state["is_active"] is True


def test_state_finished():
    """Prêt arrivé à terme."""
    state = compute_loan_state(_loan(start="2000-01-01", total_months=12), today=date(2026, 1, 1))
    assert state["months_paid"] == 12
    assert state["months_remaining"] == 0
    assert state["amount_remaining"] == 0
    assert state["progress_pct"] == 100.0
    assert state["is_active"] is False


def test_state_today_is_start():
    state = compute_loan_state(_loan(start="2026-01-01", total_months=12), today=date(2026, 1, 1))
    assert state["months_paid"] == 0
    assert state["months_remaining"] == 12


def test_state_archived_not_active():
    state = compute_loan_state(_loan(archived=True), today=date(2026, 1, 1))
    assert state["is_active"] is False


def test_state_total_months_one():
    state = compute_loan_state(_loan(start="2025-12-01", total_months=1, monthly=500), today=date(2026, 1, 1))
    assert state["months_paid"] == 1
    assert state["months_remaining"] == 0
    assert state["progress_pct"] == 100.0
```

- [ ] **Step 2 : Fail expected**

```bash
pytest tests/test_loan_calc.py -v
```

- [ ] **Step 3 : Implémenter `src/services/loan_calc.py`**

```python
from datetime import date
from dateutil.relativedelta import relativedelta


def compute_loan_state(loan: dict, today: date) -> dict:
    """Calcule l'état courant d'un prêt depuis sa déclaration et la date du jour.

    Toutes les valeurs sont déterministes (pas de tracking de paiements individuels).
    """
    start = date.fromisoformat(loan["start_date"])
    total_months = int(loan["total_months"])
    monthly = float(loan["monthly_payment"])

    end_date = start + relativedelta(months=total_months)

    if today < start:
        months_paid = 0
    else:
        delta = relativedelta(today, start)
        months_paid = delta.years * 12 + delta.months
    months_paid = max(0, min(months_paid, total_months))
    months_remaining = total_months - months_paid
    amount_remaining = monthly * months_remaining
    progress_pct = (months_paid / total_months * 100.0) if total_months > 0 else 0.0
    archived = bool(loan.get("archived"))
    is_active = (months_remaining > 0) and not archived

    return {
        "end_date": end_date.isoformat(),
        "months_paid": months_paid,
        "months_remaining": months_remaining,
        "amount_remaining": round(amount_remaining, 2),
        "progress_pct": round(progress_pct, 2),
        "is_active": is_active,
    }
```

- [ ] **Step 4 : Pass + commit**

```bash
pytest tests/test_loan_calc.py -v
git add src/services/loan_calc.py tests/test_loan_calc.py
git commit -m "feat(loans): service compute_loan_state (calendrier)"
```

---

## Task 4 : API CRUD `loans` + summary + wire router

**Files:** Create `src/api/loans.py`, modify `src/api/router.py`, create `tests/test_api_loans.py`

- [ ] **Step 1 : Tests** (`tests/test_api_loans.py`)

```python
from src.api import deps
from src.auth import decode_jwt


def _setup(client):
    r = client.post("/api/auth/setup", json={"username": "admin", "password": "testpass123"})
    assert r.status_code == 201
    client.post("/api/vault/setup", json={"password": "test"})
    token = r.cookies.get("mm_session")
    return decode_jwt(token, deps.jwt_secret)["user_id"]


def test_create_loan(client):
    _setup(client)
    r = client.post("/api/loans", json={
        "name": "Crédit immo Paris", "loan_type": "immo",
        "initial_capital": 250000, "monthly_payment": 1200,
        "total_months": 240, "start_date": "2020-01-01"
    })
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["name"] == "Crédit immo Paris"
    assert body["months_remaining"] >= 0
    assert body["end_date"] == "2040-01-01"


def test_list_loans(client):
    _setup(client)
    for n in ("A", "B"):
        client.post("/api/loans", json={
            "name": n, "loan_type": "conso", "initial_capital": 5000,
            "monthly_payment": 150, "total_months": 36, "start_date": "2024-06-01"
        })
    r = client.get("/api/loans")
    assert r.status_code == 200
    assert len(r.json()) == 2


def test_get_loan_404(client):
    _setup(client)
    r = client.get("/api/loans/999")
    assert r.status_code == 404


def test_update_loan(client):
    _setup(client)
    cr = client.post("/api/loans", json={
        "name": "L1", "loan_type": "auto", "initial_capital": 12000,
        "monthly_payment": 200, "total_months": 60, "start_date": "2024-01-01"
    })
    lid = cr.json()["id"]
    r = client.put(f"/api/loans/{lid}", json={"monthly_payment": 250, "name": "L1 renamed"})
    assert r.status_code == 200
    assert r.json()["monthly_payment"] == 250
    assert r.json()["name"] == "L1 renamed"


def test_delete_loan(client):
    _setup(client)
    cr = client.post("/api/loans", json={
        "name": "L1", "loan_type": "other", "initial_capital": 1000,
        "monthly_payment": 100, "total_months": 12, "start_date": "2024-01-01"
    })
    lid = cr.json()["id"]
    r = client.delete(f"/api/loans/{lid}")
    assert r.status_code == 204
    r = client.get(f"/api/loans/{lid}")
    assert r.status_code == 404


def test_summary(client):
    _setup(client)
    client.post("/api/loans", json={
        "name": "Immo", "loan_type": "immo", "initial_capital": 200000,
        "monthly_payment": 1000, "total_months": 240, "start_date": "2024-01-01"
    })
    client.post("/api/loans", json={
        "name": "Auto", "loan_type": "auto", "initial_capital": 12000,
        "monthly_payment": 200, "total_months": 60, "start_date": "2024-01-01"
    })
    # Prêt terminé : ne doit pas compter dans summary
    client.post("/api/loans", json={
        "name": "Old", "loan_type": "conso", "initial_capital": 1000,
        "monthly_payment": 100, "total_months": 6, "start_date": "2010-01-01"
    })
    r = client.get("/api/loans/summary")
    assert r.status_code == 200
    body = r.json()
    assert body["active_count"] == 2
    assert body["total_monthly_payment"] == 1200.0
    assert body["last_end_date"] is not None


def test_unauth(client):
    r = client.get("/api/loans")
    assert r.status_code == 401
```

- [ ] **Step 2 : Fail expected**

- [ ] **Step 3 : Implémenter `src/api/loans.py`**

```python
from datetime import date as _date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, insert, update, delete

from src.api import deps
from src.api.middleware import get_current_user, AuthUser
from src.db.models import loans
from src.schemas.loans import LoanCreate, LoanUpdate, LoanResponse, LoanSummary
from src.services.loan_calc import compute_loan_state

router = APIRouter(prefix="/api/loans", tags=["loans"])


def _row_to_response(row, today: _date) -> LoanResponse:
    state = compute_loan_state({
        "start_date": row.start_date,
        "total_months": row.total_months,
        "monthly_payment": row.monthly_payment,
        "initial_capital": row.initial_capital,
        "archived": row.archived,
    }, today)
    return LoanResponse(
        id=row.id, name=row.name, loan_type=row.loan_type,
        initial_capital=row.initial_capital, monthly_payment=row.monthly_payment,
        total_months=row.total_months, start_date=row.start_date,
        archived=bool(row.archived), created_at=row.created_at,
        end_date=state["end_date"], months_paid=state["months_paid"],
        months_remaining=state["months_remaining"],
        amount_remaining=state["amount_remaining"],
        progress_pct=state["progress_pct"], is_active=state["is_active"],
    )


@router.post("", response_model=LoanResponse, status_code=status.HTTP_201_CREATED)
def create_loan(payload: LoanCreate, user: AuthUser = Depends(get_current_user)):
    engine = deps.get_ledger(user.id)
    with engine.begin() as conn:
        result = conn.execute(insert(loans).values(
            name=payload.name, loan_type=payload.loan_type,
            initial_capital=payload.initial_capital, monthly_payment=payload.monthly_payment,
            total_months=payload.total_months, start_date=payload.start_date,
        ))
        lid = result.inserted_primary_key[0]
        row = conn.execute(select(loans).where(loans.c.id == lid)).fetchone()
    return _row_to_response(row, _date.today())


@router.get("", response_model=list[LoanResponse])
def list_loans(archived: bool = False, user: AuthUser = Depends(get_current_user)):
    engine = deps.get_ledger(user.id)
    with engine.connect() as conn:
        stmt = select(loans)
        if not archived:
            stmt = stmt.where(loans.c.archived == 0)
        rows = conn.execute(stmt.order_by(loans.c.id.desc())).fetchall()
    today = _date.today()
    return [_row_to_response(r, today) for r in rows]


@router.get("/summary", response_model=LoanSummary)
def loans_summary(user: AuthUser = Depends(get_current_user)):
    engine = deps.get_ledger(user.id)
    with engine.connect() as conn:
        rows = conn.execute(select(loans).where(loans.c.archived == 0)).fetchall()
    today = _date.today()
    states = [(r, compute_loan_state({
        "start_date": r.start_date, "total_months": r.total_months,
        "monthly_payment": r.monthly_payment, "initial_capital": r.initial_capital,
        "archived": r.archived,
    }, today)) for r in rows]
    active = [(r, s) for r, s in states if s["is_active"]]
    return LoanSummary(
        total_monthly_payment=round(sum(r.monthly_payment for r, _ in active), 2),
        total_amount_remaining=round(sum(s["amount_remaining"] for _, s in active), 2),
        last_end_date=max((s["end_date"] for _, s in active), default=None),
        active_count=len(active),
    )


@router.get("/{loan_id}", response_model=LoanResponse)
def get_loan(loan_id: int, user: AuthUser = Depends(get_current_user)):
    engine = deps.get_ledger(user.id)
    with engine.connect() as conn:
        row = conn.execute(select(loans).where(loans.c.id == loan_id)).fetchone()
        if not row:
            raise HTTPException(404, "Prêt introuvable")
    return _row_to_response(row, _date.today())


@router.put("/{loan_id}", response_model=LoanResponse)
def update_loan(loan_id: int, payload: LoanUpdate, user: AuthUser = Depends(get_current_user)):
    engine = deps.get_ledger(user.id)
    values = payload.model_dump(exclude_unset=True)
    if "archived" in values:
        values["archived"] = 1 if values["archived"] else 0
    with engine.begin() as conn:
        existing = conn.execute(select(loans).where(loans.c.id == loan_id)).fetchone()
        if not existing:
            raise HTTPException(404, "Prêt introuvable")
        if values:
            conn.execute(update(loans).where(loans.c.id == loan_id).values(**values))
        row = conn.execute(select(loans).where(loans.c.id == loan_id)).fetchone()
    return _row_to_response(row, _date.today())


@router.delete("/{loan_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_loan(loan_id: int, user: AuthUser = Depends(get_current_user)):
    engine = deps.get_ledger(user.id)
    with engine.begin() as conn:
        existing = conn.execute(select(loans).where(loans.c.id == loan_id)).fetchone()
        if not existing:
            raise HTTPException(404, "Prêt introuvable")
        conn.execute(delete(loans).where(loans.c.id == loan_id))
    return None
```

- [ ] **Step 4 : Wire router**

Modifier `src/api/router.py` :

```python
from src.api.loans import router as loans_router
# ...
api_router.include_router(loans_router)
```

- [ ] **Step 5 : Pass + commit**

```bash
pytest tests/test_api_loans.py -v
git add src/api/loans.py src/api/router.py tests/test_api_loans.py
git commit -m "feat(loans): API CRUD + summary"
```

---

## Task 5 : Frontend — types + client API

**Files:** Create `frontend/src/lib/loans.ts`, `frontend/src/api/loans.ts`

- [ ] **Step 1 : Types** (`frontend/src/lib/loans.ts`)

```typescript
export type LoanType = 'immo' | 'conso' | 'auto' | 'other';

export interface Loan {
  id: number;
  name: string;
  loan_type: LoanType;
  initial_capital: number;
  monthly_payment: number;
  total_months: number;
  start_date: string;
  archived: boolean;
  created_at: string;
  end_date: string;
  months_paid: number;
  months_remaining: number;
  amount_remaining: number;
  progress_pct: number;
  is_active: boolean;
}

export interface LoanCreatePayload {
  name: string;
  loan_type: LoanType;
  initial_capital: number;
  monthly_payment: number;
  total_months: number;
  start_date: string;
}

export interface LoanSummary {
  total_monthly_payment: number;
  total_amount_remaining: number;
  last_end_date: string | null;
  active_count: number;
}

export const LOAN_TYPE_LABELS: Record<LoanType, string> = {
  immo: 'Immobilier',
  conso: 'Consommation',
  auto: 'Auto',
  other: 'Autre',
};
```

- [ ] **Step 2 : Client** (`frontend/src/api/loans.ts`)

```typescript
import { api } from './client';
import type { Loan, LoanCreatePayload, LoanSummary } from '../lib/loans';

export function listLoans(archived = false): Promise<Loan[]> {
  return api.get<Loan[]>('/loans', { archived });
}

export function getLoan(id: number): Promise<Loan> {
  return api.get<Loan>(`/loans/${id}`);
}

export function createLoan(payload: LoanCreatePayload): Promise<Loan> {
  return api.post<Loan>('/loans', payload);
}

export function updateLoan(id: number, patch: Partial<LoanCreatePayload & { archived: boolean }>): Promise<Loan> {
  return api.put<Loan>(`/loans/${id}`, patch);
}

export function deleteLoan(id: number): Promise<void> {
  return api.del(`/loans/${id}`);
}

export function getLoansSummary(): Promise<LoanSummary> {
  return api.get<LoanSummary>('/loans/summary');
}
```

- [ ] **Step 3 : Commit**

```bash
git add frontend/src/lib/loans.ts frontend/src/api/loans.ts
git commit -m "feat(loans): types + client API frontend"
```

---

## Task 6 : Frontend — page liste + modale CRUD

**Files:** Create `frontend/src/pages/Prets.tsx`, `frontend/src/components/LoanFormModal.tsx`, modify `frontend/src/App.tsx`, `frontend/src/layouts/Sidebar.tsx`

**Convention** : suivre le pattern HTML+Tailwind avec tokens `mm-*` (cf. `frontend/src/pages/Objectifs.tsx` pour le pattern de page CRUD), pas HeroUI.

- [ ] **Step 1 : Modale form** (`frontend/src/components/LoanFormModal.tsx`)

```tsx
import { useEffect, useState } from 'react';
import { createLoan, updateLoan } from '@/api/loans';
import type { Loan, LoanType, LoanCreatePayload } from '@/lib/loans';
import { LOAN_TYPE_LABELS } from '@/lib/loans';

interface Props {
  isOpen: boolean;
  loan?: Loan | null;
  onClose: () => void;
  onSaved: () => void;
}

export function LoanFormModal({ isOpen, loan, onClose, onSaved }: Props) {
  const editing = !!loan;
  const [name, setName] = useState('');
  const [loanType, setLoanType] = useState<LoanType>('immo');
  const [initialCapital, setInitialCapital] = useState('');
  const [monthlyPayment, setMonthlyPayment] = useState('');
  const [totalMonths, setTotalMonths] = useState('');
  const [startDate, setStartDate] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen) return;
    if (loan) {
      setName(loan.name);
      setLoanType(loan.loan_type);
      setInitialCapital(String(loan.initial_capital));
      setMonthlyPayment(String(loan.monthly_payment));
      setTotalMonths(String(loan.total_months));
      setStartDate(loan.start_date);
    } else {
      setName(''); setLoanType('immo'); setInitialCapital('');
      setMonthlyPayment(''); setTotalMonths(''); setStartDate('');
    }
    setError(null);
  }, [isOpen, loan]);

  async function submit() {
    setError(null);
    const ic = parseFloat(initialCapital);
    const mp = parseFloat(monthlyPayment);
    const tm = parseInt(totalMonths, 10);
    if (!name.trim() || !(ic > 0) || !(mp > 0) || !(tm > 0) || !startDate) {
      setError('Tous les champs sont obligatoires (montants > 0).');
      return;
    }
    const payload: LoanCreatePayload = {
      name: name.trim(), loan_type: loanType, initial_capital: ic,
      monthly_payment: mp, total_months: tm, start_date: startDate,
    };
    setSubmitting(true);
    try {
      if (editing && loan) await updateLoan(loan.id, payload);
      else await createLoan(payload);
      onSaved();
      onClose();
    } catch (e: any) {
      setError(e?.detail ?? 'Erreur à l\'enregistrement');
    } finally {
      setSubmitting(false);
    }
  }

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={onClose}>
      <div
        className="bg-mm-surface border border-mm-border rounded-[12px] p-6 w-full max-w-lg mx-4 flex flex-col gap-4"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-lg font-semibold text-mm-text">
          {editing ? 'Modifier le prêt' : 'Nouveau prêt'}
        </h2>
        <div className="flex flex-col gap-3">
          <Field label="Nom">
            <input className={inputCls} value={name} onChange={(e) => setName(e.target.value)} placeholder="Ex. Crédit immo Paris" />
          </Field>
          <Field label="Type">
            <select className={inputCls} value={loanType} onChange={(e) => setLoanType(e.target.value as LoanType)}>
              {(Object.keys(LOAN_TYPE_LABELS) as LoanType[]).map((t) => (
                <option key={t} value={t}>{LOAN_TYPE_LABELS[t]}</option>
              ))}
            </select>
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Capital emprunté (€)">
              <input className={inputCls} type="number" value={initialCapital} onChange={(e) => setInitialCapital(e.target.value)} />
            </Field>
            <Field label="Mensualité (€)">
              <input className={inputCls} type="number" value={monthlyPayment} onChange={(e) => setMonthlyPayment(e.target.value)} />
            </Field>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Durée (mois)">
              <input className={inputCls} type="number" value={totalMonths} onChange={(e) => setTotalMonths(e.target.value)} />
            </Field>
            <Field label="Date 1ère mensualité">
              <input className={inputCls} type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
            </Field>
          </div>
          {error && <p className="text-sm text-mm-loss">{error}</p>}
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
            {submitting ? 'Enregistrement…' : editing ? 'Enregistrer' : 'Créer'}
          </button>
        </div>
      </div>
    </div>
  );
}

const inputCls = 'w-full px-3 py-2 bg-mm-surface-elevated border border-mm-border rounded-[8px] text-sm text-mm-text focus:outline-none focus:border-mm-gold';

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-xs text-mm-text-muted">{label}</span>
      {children}
    </label>
  );
}
```

- [ ] **Step 2 : Page liste** (`frontend/src/pages/Prets.tsx`)

```tsx
import { useEffect, useState } from 'react';
import { Pencil, Trash2, Plus } from 'lucide-react';
import { listLoans, deleteLoan } from '@/api/loans';
import type { Loan } from '@/lib/loans';
import { LOAN_TYPE_LABELS } from '@/lib/loans';
import { LoanFormModal } from '@/components/LoanFormModal';
import { formatCurrency, formatShortDate } from '@/lib/format';

export function Prets() {
  const [loans, setLoans] = useState<Loan[]>([]);
  const [loading, setLoading] = useState(true);
  const [showArchived, setShowArchived] = useState(false);
  const [editing, setEditing] = useState<Loan | null>(null);
  const [creating, setCreating] = useState(false);

  async function load() {
    setLoading(true);
    try { setLoans(await listLoans(showArchived)); }
    finally { setLoading(false); }
  }

  useEffect(() => { load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [showArchived]);

  async function handleDelete(loan: Loan) {
    if (!confirm(`Supprimer "${loan.name}" ?`)) return;
    await deleteLoan(loan.id);
    load();
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-[28px] font-semibold text-mm-text">Prêts</h1>
        <div className="flex gap-2">
          <button
            onClick={() => setShowArchived((v) => !v)}
            className={`px-4 py-2 text-sm rounded-[8px] border transition-colors ${
              showArchived ? 'border-mm-gold text-mm-gold' : 'border-mm-border text-mm-text-muted'
            }`}
          >
            {showArchived ? 'Afficher actifs' : 'Afficher archivés'}
          </button>
          <button
            onClick={() => setCreating(true)}
            className="px-4 py-2 bg-mm-gold text-mm-bg text-sm font-semibold rounded-[8px] flex items-center gap-1.5 hover:opacity-90"
          >
            <Plus size={16} /> Nouveau prêt
          </button>
        </div>
      </div>

      {loading && <div className="text-sm text-mm-text-muted">Chargement…</div>}

      {!loading && loans.length === 0 && (
        <div className="bg-mm-surface border border-mm-border rounded-[12px] px-5 py-12 text-center text-sm text-mm-text-muted">
          Aucun prêt déclaré. Crée ton premier prêt pour démarrer le suivi.
        </div>
      )}

      {!loading && loans.length > 0 && (
        <div className="bg-mm-surface border border-mm-border rounded-[12px] overflow-hidden">
          <table className="w-full text-sm">
            <thead className="border-b border-mm-border text-xs text-mm-text-muted">
              <tr>
                <Th>Nom</Th>
                <Th>Type</Th>
                <Th align="right">Mensualité</Th>
                <Th align="right">Restantes</Th>
                <Th>Fin</Th>
                <Th align="right">Restant total</Th>
                <Th align="right">Progression</Th>
                <Th>Actions</Th>
              </tr>
            </thead>
            <tbody>
              {loans.map((l) => (
                <tr key={l.id} className="border-b border-mm-border last:border-0 hover:bg-mm-surface-elevated/30">
                  <td className="px-4 py-3 text-mm-text">{l.name}</td>
                  <td className="px-4 py-3 text-mm-text-muted">{LOAN_TYPE_LABELS[l.loan_type]}</td>
                  <td className="px-4 py-3 text-right font-mono text-mm-text">{formatCurrency(l.monthly_payment, 'EUR')}</td>
                  <td className="px-4 py-3 text-right text-mm-text-muted">{l.months_remaining} / {l.total_months}</td>
                  <td className="px-4 py-3 text-mm-text-muted">{formatShortDate(l.end_date)}</td>
                  <td className="px-4 py-3 text-right font-mono text-mm-text">{formatCurrency(l.amount_remaining, 'EUR')}</td>
                  <td className="px-4 py-3 text-right">
                    <div className="flex items-center justify-end gap-2">
                      <div className="w-20 bg-mm-surface-elevated rounded-full h-1.5 overflow-hidden">
                        <div className="h-full bg-mm-gold rounded-full" style={{ width: `${l.progress_pct}%` }} />
                      </div>
                      <span className="text-xs text-mm-text-muted w-10 text-right">{l.progress_pct.toFixed(0)} %</span>
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex gap-2">
                      <button onClick={() => setEditing(l)} className="text-mm-text-muted hover:text-mm-gold"><Pencil size={14} /></button>
                      <button onClick={() => handleDelete(l)} className="text-mm-text-muted hover:text-mm-loss"><Trash2 size={14} /></button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <LoanFormModal isOpen={creating} onClose={() => setCreating(false)} onSaved={load} />
      <LoanFormModal isOpen={!!editing} loan={editing} onClose={() => setEditing(null)} onSaved={load} />
    </div>
  );
}

function Th({ children, align = 'left' }: { children: React.ReactNode; align?: 'left' | 'right' }) {
  return <th className={`px-4 py-3 font-medium ${align === 'right' ? 'text-right' : 'text-left'}`}>{children}</th>;
}
```

- [ ] **Step 3 : Wire route et nav**

`frontend/src/App.tsx` — ajouter l'import et la route :
```tsx
import { Prets } from "@/pages/Prets";
// ... dans le bloc vaultState === "unlocked" :
<Route path="/prets" element={<Prets />} />
```

`frontend/src/layouts/Sidebar.tsx` — ajouter une entrée nav "Prêts" (icône `Landmark` ou `Banknote` de lucide-react) à côté de "Objectifs", route `/prets`. Lire d'abord le fichier pour respecter le format réel des entrées.

- [ ] **Step 4 : Build clean**

```bash
cd /Users/charles/Desktop/mm-ledger/frontend && bun run build 2>&1 | tail -10
```

- [ ] **Step 5 : Commit**

```bash
git add frontend/src/pages/Prets.tsx frontend/src/components/LoanFormModal.tsx frontend/src/App.tsx frontend/src/layouts/Sidebar.tsx
git commit -m "feat(loans): page /prets + modale CRUD + nav"
```

---

## Task 7 : Card Dashboard

**Files:** Create `frontend/src/components/PretsCard.tsx`, modify `frontend/src/pages/Dashboard.tsx`

- [ ] **Step 1 : Card** (`frontend/src/components/PretsCard.tsx`)

```tsx
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { getLoansSummary } from '@/api/loans';
import type { LoanSummary } from '@/lib/loans';
import { formatCurrency, formatShortDate } from '@/lib/format';

export function PretsCard() {
  const [summary, setSummary] = useState<LoanSummary | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    getLoansSummary()
      .then((s) => { if (!cancelled) setSummary(s); })
      .catch(() => { if (!cancelled) setSummary(null); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  return (
    <div className="bg-mm-surface border border-mm-border rounded-[12px] px-5 py-4 flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <span className="font-medium text-mm-text">Prêts</span>
        <Link to="/prets" className="text-sm text-mm-gold hover:underline">Voir tout →</Link>
      </div>
      {loading && <div className="text-sm text-mm-text-muted">Chargement…</div>}
      {!loading && (!summary || summary.active_count === 0) && (
        <div className="text-sm text-mm-text-muted">
          Aucun prêt actif. <Link to="/prets" className="text-mm-gold hover:underline">En déclarer un</Link>.
        </div>
      )}
      {!loading && summary && summary.active_count > 0 && (
        <>
          <div>
            <div className="text-2xl font-mono text-mm-text">
              {formatCurrency(summary.total_monthly_payment, 'EUR')}
              <span className="text-sm text-mm-text-muted font-sans"> / mois</span>
            </div>
            <div className="text-xs text-mm-text-muted">
              {summary.active_count} prêt{summary.active_count > 1 ? 's' : ''} actif{summary.active_count > 1 ? 's' : ''}
            </div>
          </div>
          <div className="text-xs text-mm-text-muted">
            Restant total : <span className="text-mm-text font-mono">{formatCurrency(summary.total_amount_remaining, 'EUR')}</span>
            {summary.last_end_date && <>, jusqu'en <span className="text-mm-text">{formatShortDate(summary.last_end_date)}</span></>}
          </div>
        </>
      )}
    </div>
  );
}
```

- [ ] **Step 2 : Intégrer dans Dashboard.tsx**

Lire `frontend/src/pages/Dashboard.tsx`, ajouter l'import :
```tsx
import { PretsCard } from '@/components/PretsCard';
```
Et placer `<PretsCard />` dans la grille (à côté de `<ObjectifsCard />` ou en dessous, à un endroit visuellement cohérent).

- [ ] **Step 3 : Build + commit**

```bash
cd /Users/charles/Desktop/mm-ledger/frontend && bun run build 2>&1 | tail -10
git add frontend/src/components/PretsCard.tsx frontend/src/pages/Dashboard.tsx
git commit -m "feat(loans): card Prêts sur le Dashboard"
```

---

## Task 8 : CLAUDE.md + vérif finale

**Files:** Modify `CLAUDE.md`

- [ ] **Step 1 : Note dans CLAUDE.md**

Ajouter à la fin de la section Gotchas :

> **Module Prêts (ERP)** : 2e module v1 du chantier ERP. Suivi déclaratif simple sans amortissement (pas de taux, pas de capital restant dû exact). Calculs calendaires : `months_remaining = total_months − months_paid`, `amount_remaining = mensualité × restantes`. Service pur `src/services/loan_calc.py::compute_loan_state`. API `/api/loans` (CRUD + `/summary`). Page `/prets`, card "Prêts" sur Dashboard. Table `loans` dans le ledger user. Spec : `docs/superpowers/specs/2026-04-27-erp-prets-design.md`.

- [ ] **Step 2 : Vérif globale**

```bash
cd /Users/charles/Desktop/mm-ledger && source .venv/bin/activate && pytest tests/ -q 2>&1 | tail -5
cd frontend && bun run build 2>&1 | tail -5
```

- [ ] **Step 3 : Commit**

```bash
git add CLAUDE.md
git commit -m "docs: note module Prêts dans CLAUDE.md"
```

- [ ] **Step 4 : Test manuel rapide**

Démarrer back + front :
```bash
./start.sh
cd frontend && bun run dev
```

Sur `/prets` :
1. Créer un prêt immo (250 000 €, 1 200 €/mois, 240 mois, début 2020-01-01) → vérifier que l'affichage donne ~72 mensualités payées et fin en 2040.
2. Modifier la mensualité → recalcul du restant total.
3. Supprimer.
4. Sur Dashboard : la card "Prêts" affiche bien la somme des mensualités/mois et la prochaine date de fin.
