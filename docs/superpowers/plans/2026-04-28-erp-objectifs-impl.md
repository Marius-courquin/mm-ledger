# Module Objectifs — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implémenter le module Objectifs (cibles type "asset" et "bucket") avec API backend complète + UI React (page liste, page détail, card Dashboard).

**Architecture:** Tables SQLAlchemy Core dans `src/db/models.py`, services purs dans `src/services/target_progression.py`, routes FastAPI dans `src/api/targets.py`. Front en page dédiée `/objectifs` + détail `/objectifs/:id` + card Dashboard. JWT cookie via `get_current_user`. Multi-user via `deps.get_ledger(user.id)`.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2 Core, Pydantic v2, pytest, React 19, TypeScript, HeroUI, Recharts, TailwindCSS 4.

**Spec source:** `docs/superpowers/specs/2026-04-27-erp-objectifs-design.md`

**File map (created or modified):**
- Modify: `src/db/models.py` (add `targets`, `target_slices` tables)
- Create: `src/schemas/targets.py` (Pydantic)
- Create: `src/services/target_progression.py` (calculs purs)
- Create: `src/api/targets.py` (routes)
- Modify: `src/api/router.py` (wire router)
- Create: `tests/test_api_targets.py`
- Create: `tests/test_target_progression.py`
- Create: `frontend/src/api/targets.ts`
- Create: `frontend/src/lib/targets.ts` (types)
- Create: `frontend/src/pages/Objectifs.tsx`
- Create: `frontend/src/pages/ObjectifDetail.tsx`
- Create: `frontend/src/components/TargetCreateModal.tsx`
- Create: `frontend/src/components/TargetSliceEditor.tsx`
- Create: `frontend/src/components/ObjectifsCard.tsx`
- Modify: `frontend/src/App.tsx` (routes)
- Modify: `frontend/src/layouts/AppLayout.tsx` (nav entry)
- Modify: `frontend/src/pages/Dashboard.tsx` (intégrer la card)

---

## Task 1 : Tables `targets` et `target_slices`

**Files:**
- Modify: `src/db/models.py` (ajout en bas du fichier, avant les `Index`)
- Test: `tests/test_db.py` (ajouter test smoke)

- [ ] **Step 1 : Écrire le test smoke**

Ajouter à `tests/test_db.py` :

```python
def test_targets_tables_created(tmp_path):
    from src.db.engine import create_engine_and_tables
    from src.db.models import targets, target_slices
    from sqlalchemy import inspect

    engine = create_engine_and_tables(tmp_path / "ledger.db")
    insp = inspect(engine)
    assert "targets" in insp.get_table_names()
    assert "target_slices" in insp.get_table_names()
    cols = {c["name"] for c in insp.get_columns("targets")}
    assert {"id", "name", "type", "target_amount", "asset_account_id",
            "asset_symbol", "rate_override", "archived", "created_at"} <= cols
    cols = {c["name"] for c in insp.get_columns("target_slices")}
    assert {"id", "target_id", "account_id", "allocation_kind", "allocation_value"} <= cols
```

- [ ] **Step 2 : Vérifier que le test échoue**

```bash
source .venv/bin/activate && pytest tests/test_db.py::test_targets_tables_created -v
```

Expected : FAIL avec `ImportError: cannot import name 'targets'`.

- [ ] **Step 3 : Ajouter les tables dans `src/db/models.py`**

Ajouter avant la ligne `Index("idx_snapshots_account_date", ...)` (vers la ligne 83) :

```python
targets = Table(
    "targets", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("name", Text, nullable=False),
    Column("type", Text, nullable=False),  # 'asset' | 'bucket'
    Column("target_amount", Real, nullable=False),
    Column("asset_account_id", Text),  # NULL si type='bucket'
    Column("asset_symbol", Text),       # NULL si type='bucket'
    Column("rate_override", Real),      # NULL = auto
    Column("archived", Integer, nullable=False, server_default="0"),
    Column("created_at", Text, server_default="(datetime('now'))"),
)

target_slices = Table(
    "target_slices", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("target_id", Integer, ForeignKey("targets.id", ondelete="CASCADE"), nullable=False),
    Column("account_id", Text, nullable=False),
    Column("allocation_kind", Text, nullable=False),  # 'amount' | 'percent'
    Column("allocation_value", Real, nullable=False),
)

Index("idx_target_slices_target", target_slices.c.target_id)
```

- [ ] **Step 4 : Vérifier que le test passe**

```bash
pytest tests/test_db.py::test_targets_tables_created -v
```

Expected : PASS.

- [ ] **Step 5 : Commit**

```bash
git add src/db/models.py tests/test_db.py
git commit -m "feat(targets): tables targets + target_slices"
```

---

## Task 2 : Schémas Pydantic

**Files:**
- Create: `src/schemas/targets.py`

- [ ] **Step 1 : Créer le fichier schémas**

```python
# src/schemas/targets.py
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
```

- [ ] **Step 2 : Vérifier l'import**

```bash
python -c "from src.schemas.targets import TargetCreate, ProgressionResponse; print('OK')"
```

Expected : `OK`.

- [ ] **Step 3 : Commit**

```bash
git add src/schemas/targets.py
git commit -m "feat(targets): schémas Pydantic"
```

---

## Task 3 : Service `compute_current_value` (type asset)

**Files:**
- Create: `src/services/target_progression.py`
- Create: `tests/test_target_progression.py`

- [ ] **Step 1 : Écrire le test (asset, position existante)**

```python
# tests/test_target_progression.py
from datetime import date
from sqlalchemy import insert
from src.db.engine import create_engine_and_tables
from src.db.models import accounts, balance_snapshots, connectors
from src.services.target_progression import compute_current_value


def _seed_position(tmp_path, symbol="IWDA", value=900.0):
    engine = create_engine_and_tables(tmp_path / "ledger.db")
    with engine.begin() as conn:
        conn.execute(insert(connectors).values(id="tr_1", type="trade_republic"))
        conn.execute(insert(accounts).values(id="tr_CTO", connector_id="tr_1", name="CTO", type="cto"))
        conn.execute(insert(balance_snapshots).values(
            account_id="tr_CTO", date="2026-04-27",
            cash=100, positions_value=value, total_value=100 + value,
            positions=[{"symbol": symbol, "qty": 10, "price": value/10, "value": value}],
        ))
    return engine


def test_current_value_asset_existing(tmp_path):
    engine = _seed_position(tmp_path, symbol="IWDA", value=1234.5)
    target = {"type": "asset", "asset_account_id": "tr_CTO", "asset_symbol": "IWDA"}
    val = compute_current_value(target, [], engine, today=date(2026, 4, 28))
    assert val == 1234.5


def test_current_value_asset_missing(tmp_path):
    engine = _seed_position(tmp_path, symbol="IWDA", value=900)
    target = {"type": "asset", "asset_account_id": "tr_CTO", "asset_symbol": "VWCE"}
    val = compute_current_value(target, [], engine, today=date(2026, 4, 28))
    assert val == 0.0
```

- [ ] **Step 2 : Vérifier que les tests échouent**

```bash
pytest tests/test_target_progression.py::test_current_value_asset_existing -v
```

Expected : FAIL avec `ImportError`.

- [ ] **Step 3 : Implémenter le service (type asset)**

```python
# src/services/target_progression.py
from datetime import date
from sqlalchemy import select, desc
from sqlalchemy.engine import Engine

from src.db.models import balance_snapshots


def compute_current_value(target: dict, slices: list[dict], engine: Engine, today: date) -> float:
    """Valeur courante d'une cible.

    Type 'asset' : valeur de la position (account_id, symbol) la plus récente.
    Type 'bucket' : somme des slices (cf. Task 4).
    """
    if target["type"] == "asset":
        return _current_value_asset(target, engine)
    if target["type"] == "bucket":
        return _current_value_bucket(slices, engine)
    return 0.0


def _current_value_asset(target: dict, engine: Engine) -> float:
    stmt = (
        select(balance_snapshots.c.positions)
        .where(balance_snapshots.c.account_id == target["asset_account_id"])
        .order_by(desc(balance_snapshots.c.date))
        .limit(1)
    )
    with engine.connect() as conn:
        row = conn.execute(stmt).fetchone()
    if not row or not row.positions:
        return 0.0
    for p in row.positions:
        if p.get("symbol") == target["asset_symbol"]:
            return float(p.get("value") or 0.0)
    return 0.0


def _current_value_bucket(slices: list[dict], engine: Engine) -> float:
    # implémenté en Task 4
    return 0.0
```

- [ ] **Step 4 : Vérifier que les tests asset passent**

```bash
pytest tests/test_target_progression.py -v -k current_value_asset
```

Expected : 2 PASS.

- [ ] **Step 5 : Commit**

```bash
git add src/services/target_progression.py tests/test_target_progression.py
git commit -m "feat(targets): service compute_current_value type asset"
```

---

## Task 4 : Service `compute_current_value` (type bucket)

**Files:**
- Modify: `src/services/target_progression.py`
- Modify: `tests/test_target_progression.py`

- [ ] **Step 1 : Ajouter les tests bucket**

Ajouter à `tests/test_target_progression.py` :

```python
def _seed_account_value(tmp_path, account_id="tr_CTO", total=5000.0):
    engine = create_engine_and_tables(tmp_path / "ledger.db")
    with engine.begin() as conn:
        conn.execute(insert(connectors).values(id="tr_1", type="trade_republic"))
        conn.execute(insert(accounts).values(id=account_id, connector_id="tr_1", name="CTO", type="cto"))
        conn.execute(insert(balance_snapshots).values(
            account_id=account_id, date="2026-04-27",
            cash=0, positions_value=total, total_value=total, positions=[],
        ))
    return engine


def test_current_value_bucket_amount_slice(tmp_path):
    engine = _seed_account_value(tmp_path, "livret_A", total=10000)
    target = {"type": "bucket"}
    slices = [{"account_id": "livret_A", "allocation_kind": "amount", "allocation_value": 1500}]
    val = compute_current_value(target, slices, engine, today=date(2026, 4, 28))
    assert val == 1500.0


def test_current_value_bucket_percent_slice(tmp_path):
    engine = _seed_account_value(tmp_path, "tr_CTO", total=10000)
    target = {"type": "bucket"}
    slices = [{"account_id": "tr_CTO", "allocation_kind": "percent", "allocation_value": 30}]
    val = compute_current_value(target, slices, engine, today=date(2026, 4, 28))
    assert val == 3000.0


def test_current_value_bucket_mixed_multi_account(tmp_path):
    engine = create_engine_and_tables(tmp_path / "ledger.db")
    with engine.begin() as conn:
        conn.execute(insert(connectors).values(id="tr_1", type="trade_republic"))
        conn.execute(insert(connectors).values(id="bp_1", type="woob_bank"))
        conn.execute(insert(accounts).values(id="cto", connector_id="tr_1", name="CTO", type="cto"))
        conn.execute(insert(accounts).values(id="livret", connector_id="bp_1", name="Livret", type="cash"))
        conn.execute(insert(balance_snapshots).values(
            account_id="cto", date="2026-04-27",
            cash=0, positions_value=10000, total_value=10000, positions=[],
        ))
        conn.execute(insert(balance_snapshots).values(
            account_id="livret", date="2026-04-27",
            cash=8000, positions_value=0, total_value=8000, positions=[],
        ))
    target = {"type": "bucket"}
    slices = [
        {"account_id": "cto", "allocation_kind": "percent", "allocation_value": 30},     # 3000
        {"account_id": "livret", "allocation_kind": "amount", "allocation_value": 2500}, # 2500
    ]
    val = compute_current_value(target, slices, engine, today=date(2026, 4, 28))
    assert val == 5500.0


def test_current_value_bucket_amount_capped(tmp_path):
    """Si la slice 'amount' dépasse la valeur du compte, on cap à la valeur du compte."""
    engine = _seed_account_value(tmp_path, "livret", total=1000)
    target = {"type": "bucket"}
    slices = [{"account_id": "livret", "allocation_kind": "amount", "allocation_value": 5000}]
    val = compute_current_value(target, slices, engine, today=date(2026, 4, 28))
    assert val == 1000.0
```

- [ ] **Step 2 : Vérifier que les tests échouent**

```bash
pytest tests/test_target_progression.py -v -k bucket
```

Expected : FAIL (les fonctions retournent 0.0).

- [ ] **Step 3 : Implémenter `_current_value_bucket`**

Remplacer dans `src/services/target_progression.py` :

```python
def _current_value_bucket(slices: list[dict], engine: Engine) -> float:
    if not slices:
        return 0.0
    account_ids = {s["account_id"] for s in slices}
    account_values = _latest_account_values(engine, account_ids)
    total = 0.0
    for s in slices:
        acc_total = account_values.get(s["account_id"], 0.0)
        if s["allocation_kind"] == "amount":
            total += min(float(s["allocation_value"]), acc_total)
        elif s["allocation_kind"] == "percent":
            total += acc_total * float(s["allocation_value"]) / 100.0
    return total


def _latest_account_values(engine: Engine, account_ids: set[str]) -> dict[str, float]:
    """Pour chaque account_id, renvoie le total_value du snapshot le plus récent."""
    if not account_ids:
        return {}
    out: dict[str, float] = {}
    with engine.connect() as conn:
        for acc_id in account_ids:
            stmt = (
                select(balance_snapshots.c.total_value)
                .where(balance_snapshots.c.account_id == acc_id)
                .order_by(desc(balance_snapshots.c.date))
                .limit(1)
            )
            row = conn.execute(stmt).fetchone()
            out[acc_id] = float(row.total_value) if row and row.total_value is not None else 0.0
    return out
```

- [ ] **Step 4 : Vérifier que tous les tests passent**

```bash
pytest tests/test_target_progression.py -v
```

Expected : tous PASS.

- [ ] **Step 5 : Commit**

```bash
git add src/services/target_progression.py tests/test_target_progression.py
git commit -m "feat(targets): service compute_current_value type bucket"
```

---

## Task 5 : Service `compute_rate` (auto + override)

**Files:**
- Modify: `src/services/target_progression.py`
- Modify: `tests/test_target_progression.py`

- [ ] **Step 1 : Ajouter les tests rate**

Ajouter à `tests/test_target_progression.py` :

```python
def _seed_history(tmp_path, account_id, dates_values):
    """dates_values: list of (date_str, total_value)."""
    engine = create_engine_and_tables(tmp_path / "ledger.db")
    with engine.begin() as conn:
        conn.execute(insert(connectors).values(id="c", type="trade_republic"))
        conn.execute(insert(accounts).values(id=account_id, connector_id="c", name="A", type="cto"))
        for d, v in dates_values:
            conn.execute(insert(balance_snapshots).values(
                account_id=account_id, date=d,
                cash=0, positions_value=v, total_value=v, positions=[],
            ))
    return engine


def test_rate_override(tmp_path):
    from src.services.target_progression import compute_rate
    engine = _seed_history(tmp_path, "a", [("2026-01-15", 1000), ("2026-04-15", 1300)])
    target = {"type": "bucket", "rate_override": 250.0}
    slices = [{"account_id": "a", "allocation_kind": "percent", "allocation_value": 100}]
    rate, source = compute_rate(target, slices, engine, today=date(2026, 4, 28))
    assert rate == 250.0
    assert source == "override"


def test_rate_auto_3_months(tmp_path):
    """1000 il y a 3 mois → 1300 aujourd'hui : rythme = 100 €/mois."""
    from src.services.target_progression import compute_rate
    engine = _seed_history(tmp_path, "a", [
        ("2026-01-28", 1000),
        ("2026-04-28", 1300),
    ])
    target = {"type": "bucket", "rate_override": None}
    slices = [{"account_id": "a", "allocation_kind": "percent", "allocation_value": 100}]
    rate, source = compute_rate(target, slices, engine, today=date(2026, 4, 28))
    assert abs(rate - 100.0) < 1.0
    assert source == "auto"


def test_rate_auto_no_history(tmp_path):
    """Pas d'historique → rate=0."""
    from src.services.target_progression import compute_rate
    engine = create_engine_and_tables(tmp_path / "ledger.db")
    with engine.begin() as conn:
        conn.execute(insert(connectors).values(id="c", type="trade_republic"))
        conn.execute(insert(accounts).values(id="a", connector_id="c", name="A", type="cto"))
    target = {"type": "bucket", "rate_override": None}
    slices = [{"account_id": "a", "allocation_kind": "percent", "allocation_value": 100}]
    rate, source = compute_rate(target, slices, engine, today=date(2026, 4, 28))
    assert rate == 0.0
    assert source == "auto"
```

- [ ] **Step 2 : Lancer les tests, vérifier l'échec**

```bash
pytest tests/test_target_progression.py -v -k rate
```

Expected : FAIL (`compute_rate` n'existe pas).

- [ ] **Step 3 : Implémenter `compute_rate`**

Ajouter à `src/services/target_progression.py` :

```python
from dateutil.relativedelta import relativedelta


def compute_rate(
    target: dict,
    slices: list[dict],
    engine: Engine,
    today: date,
    lookback_months: int = 3,
) -> tuple[float, str]:
    """Renvoie (rate €/mois, source 'auto'|'override')."""
    if target.get("rate_override") is not None:
        return float(target["rate_override"]), "override"

    value_now = compute_current_value(target, slices, engine, today)
    past_date = today - relativedelta(months=lookback_months)
    value_past = _value_at(target, slices, engine, past_date)

    months_elapsed = lookback_months
    if value_past is None:
        # Tente une fenêtre plus courte (≥ 1 mois)
        for fallback in range(lookback_months - 1, 0, -1):
            past_date = today - relativedelta(months=fallback)
            value_past = _value_at(target, slices, engine, past_date)
            if value_past is not None:
                months_elapsed = fallback
                break
    if value_past is None or months_elapsed == 0:
        return 0.0, "auto"
    return (value_now - value_past) / months_elapsed, "auto"


def _value_at(target: dict, slices: list[dict], engine: Engine, target_date: date) -> float | None:
    """Renvoie la valeur de la cible à une date donnée. None si pas d'historique."""
    if target["type"] == "asset":
        return _value_asset_at(target, engine, target_date)
    return _value_bucket_at(slices, engine, target_date)


def _value_asset_at(target: dict, engine: Engine, target_date: date) -> float | None:
    stmt = (
        select(balance_snapshots.c.positions)
        .where(balance_snapshots.c.account_id == target["asset_account_id"])
        .where(balance_snapshots.c.date <= target_date.isoformat())
        .order_by(desc(balance_snapshots.c.date))
        .limit(1)
    )
    with engine.connect() as conn:
        row = conn.execute(stmt).fetchone()
    if not row or not row.positions:
        return None
    for p in row.positions:
        if p.get("symbol") == target["asset_symbol"]:
            return float(p.get("value") or 0.0)
    return 0.0  # snapshot existait mais pas la position : 0 (pas détenue ce jour)


def _value_bucket_at(slices: list[dict], engine: Engine, target_date: date) -> float | None:
    if not slices:
        return None
    total = 0.0
    found_any = False
    with engine.connect() as conn:
        for s in slices:
            stmt = (
                select(balance_snapshots.c.total_value)
                .where(balance_snapshots.c.account_id == s["account_id"])
                .where(balance_snapshots.c.date <= target_date.isoformat())
                .order_by(desc(balance_snapshots.c.date))
                .limit(1)
            )
            row = conn.execute(stmt).fetchone()
            if row is None:
                continue
            found_any = True
            acc_total = float(row.total_value) if row.total_value is not None else 0.0
            if s["allocation_kind"] == "amount":
                total += min(float(s["allocation_value"]), acc_total)
            else:
                total += acc_total * float(s["allocation_value"]) / 100.0
    return total if found_any else None
```

- [ ] **Step 4 : Vérifier les tests rate**

```bash
pytest tests/test_target_progression.py -v -k rate
```

Expected : 3 PASS.

- [ ] **Step 5 : Commit**

```bash
git add src/services/target_progression.py tests/test_target_progression.py
git commit -m "feat(targets): service compute_rate auto + override"
```

---

## Task 6 : Service `compute_eta`

**Files:**
- Modify: `src/services/target_progression.py`
- Modify: `tests/test_target_progression.py`

- [ ] **Step 1 : Tests ETA**

Ajouter à `tests/test_target_progression.py` :

```python
def test_eta_reached():
    from src.services.target_progression import compute_eta
    months, status = compute_eta(target_amount=1000, current_value=1200, rate=100)
    assert months is None
    assert status == "reached"


def test_eta_ok():
    from src.services.target_progression import compute_eta
    months, status = compute_eta(target_amount=1000, current_value=400, rate=100)
    assert months == 6.0
    assert status == "ok"


def test_eta_insufficient_zero():
    from src.services.target_progression import compute_eta
    months, status = compute_eta(target_amount=1000, current_value=400, rate=0)
    assert months is None
    assert status == "insufficient"


def test_eta_insufficient_negative():
    from src.services.target_progression import compute_eta
    months, status = compute_eta(target_amount=1000, current_value=400, rate=-50)
    assert months is None
    assert status == "insufficient"
```

- [ ] **Step 2 : Vérifier l'échec**

```bash
pytest tests/test_target_progression.py -v -k eta
```

Expected : FAIL.

- [ ] **Step 3 : Implémenter `compute_eta`**

Ajouter à `src/services/target_progression.py` :

```python
def compute_eta(target_amount: float, current_value: float, rate: float) -> tuple[float | None, str]:
    """Renvoie (eta_months, status)."""
    if current_value >= target_amount:
        return None, "reached"
    if rate <= 0:
        return None, "insufficient"
    return (target_amount - current_value) / rate, "ok"
```

- [ ] **Step 4 : Vérifier les tests**

```bash
pytest tests/test_target_progression.py -v -k eta
```

Expected : 4 PASS.

- [ ] **Step 5 : Commit**

```bash
git add src/services/target_progression.py tests/test_target_progression.py
git commit -m "feat(targets): service compute_eta"
```

---

## Task 7 : Service `compute_history` (courbe rétroactive)

**Files:**
- Modify: `src/services/target_progression.py`
- Modify: `tests/test_target_progression.py`

- [ ] **Step 1 : Tests history**

Ajouter à `tests/test_target_progression.py` :

```python
def test_history_bucket_percent(tmp_path):
    from src.services.target_progression import compute_history
    engine = _seed_history(tmp_path, "a", [
        ("2026-02-01", 1000),
        ("2026-03-01", 1100),
        ("2026-04-01", 1200),
    ])
    target = {"type": "bucket"}
    slices = [{"account_id": "a", "allocation_kind": "percent", "allocation_value": 50}]
    points = compute_history(target, slices, engine, today=date(2026, 4, 28))
    by_date = {p["date"]: p["value"] for p in points}
    assert by_date["2026-02-01"] == 500.0
    assert by_date["2026-03-01"] == 550.0
    assert by_date["2026-04-01"] == 600.0


def test_history_asset(tmp_path):
    """Historique d'une position spécifique reconstruit depuis balance_snapshots.positions."""
    from src.services.target_progression import compute_history
    engine = create_engine_and_tables(tmp_path / "ledger.db")
    with engine.begin() as conn:
        conn.execute(insert(connectors).values(id="c", type="trade_republic"))
        conn.execute(insert(accounts).values(id="cto", connector_id="c", name="CTO", type="cto"))
        for d, val in [("2026-02-01", 1000), ("2026-03-01", 1500), ("2026-04-01", 1800)]:
            conn.execute(insert(balance_snapshots).values(
                account_id="cto", date=d,
                cash=0, positions_value=val, total_value=val,
                positions=[{"symbol": "VWCE", "qty": 10, "price": val/10, "value": val}],
            ))
    target = {"type": "asset", "asset_account_id": "cto", "asset_symbol": "VWCE"}
    points = compute_history(target, [], engine, today=date(2026, 4, 28))
    by_date = {p["date"]: p["value"] for p in points}
    assert by_date["2026-02-01"] == 1000.0
    assert by_date["2026-04-01"] == 1800.0


def test_history_empty(tmp_path):
    """Pas de snapshots → pas de courbe."""
    from src.services.target_progression import compute_history
    engine = create_engine_and_tables(tmp_path / "ledger.db")
    with engine.begin() as conn:
        conn.execute(insert(connectors).values(id="c", type="trade_republic"))
        conn.execute(insert(accounts).values(id="a", connector_id="c", name="A", type="cto"))
    target = {"type": "bucket"}
    slices = [{"account_id": "a", "allocation_kind": "percent", "allocation_value": 100}]
    points = compute_history(target, slices, engine, today=date(2026, 4, 28))
    assert points == []
```

- [ ] **Step 2 : Vérifier l'échec**

```bash
pytest tests/test_target_progression.py -v -k history
```

Expected : FAIL.

- [ ] **Step 3 : Implémenter `compute_history`**

Ajouter à `src/services/target_progression.py` :

```python
def compute_history(target: dict, slices: list[dict], engine: Engine, today: date) -> list[dict]:
    """Reconstruit la valeur de la cible jour par jour à partir des snapshots existants.

    Stratégie v1 : on applique l'allocation actuelle rétroactivement.
    Returns: liste triée chronologiquement de {"date": str, "value": float}.
    """
    if target["type"] == "asset":
        return _history_asset(target, engine)
    return _history_bucket(slices, engine)


def _history_asset(target: dict, engine: Engine) -> list[dict]:
    stmt = (
        select(balance_snapshots.c.date, balance_snapshots.c.positions)
        .where(balance_snapshots.c.account_id == target["asset_account_id"])
        .order_by(balance_snapshots.c.date)
    )
    with engine.connect() as conn:
        rows = conn.execute(stmt).fetchall()
    out = []
    for r in rows:
        positions = r.positions or []
        value = 0.0
        for p in positions:
            if p.get("symbol") == target["asset_symbol"]:
                value = float(p.get("value") or 0.0)
                break
        out.append({"date": r.date, "value": value})
    return out


def _history_bucket(slices: list[dict], engine: Engine) -> list[dict]:
    if not slices:
        return []
    # Récupère toutes les dates uniques sur lesquelles au moins un compte source a un snapshot
    account_ids = [s["account_id"] for s in slices]
    with engine.connect() as conn:
        stmt = (
            select(balance_snapshots.c.account_id, balance_snapshots.c.date,
                   balance_snapshots.c.total_value)
            .where(balance_snapshots.c.account_id.in_(account_ids))
            .order_by(balance_snapshots.c.date)
        )
        rows = conn.execute(stmt).fetchall()
    if not rows:
        return []
    # Index par compte pour lookup chronologique
    per_account: dict[str, list[tuple[str, float]]] = {}
    all_dates: set[str] = set()
    for r in rows:
        per_account.setdefault(r.account_id, []).append(
            (r.date, float(r.total_value) if r.total_value is not None else 0.0)
        )
        all_dates.add(r.date)
    out = []
    for d in sorted(all_dates):
        total = 0.0
        for s in slices:
            series = per_account.get(s["account_id"], [])
            # Dernier snapshot ≤ d
            acc_total = 0.0
            for snap_date, val in series:
                if snap_date <= d:
                    acc_total = val
                else:
                    break
            if s["allocation_kind"] == "amount":
                total += min(float(s["allocation_value"]), acc_total)
            else:
                total += acc_total * float(s["allocation_value"]) / 100.0
        out.append({"date": d, "value": total})
    return out
```

- [ ] **Step 4 : Vérifier les tests**

```bash
pytest tests/test_target_progression.py -v -k history
```

Expected : 3 PASS.

- [ ] **Step 5 : Commit**

```bash
git add src/services/target_progression.py tests/test_target_progression.py
git commit -m "feat(targets): service compute_history rétroactif"
```

---

## Task 8 : API CRUD `targets`

**Files:**
- Create: `src/api/targets.py`
- Create: `tests/test_api_targets.py`

- [ ] **Step 1 : Tests CRUD targets**

```python
# tests/test_api_targets.py
from sqlalchemy import insert
from src.db.models import connectors, accounts, balance_snapshots
from src.api import deps
from src.auth import decode_jwt


def _setup(client):
    r = client.post("/api/auth/setup", json={"username": "admin", "password": "testpass123"})
    assert r.status_code == 201
    client.post("/api/vault/setup", json={"password": "test"})
    token = r.cookies.get("mm_session")
    payload = decode_jwt(token, deps.jwt_secret)
    return payload["user_id"]


def _seed_account(user_id, account_id="acc1", value=10000):
    engine = deps.get_ledger(user_id)
    with engine.begin() as conn:
        conn.execute(insert(connectors).values(id="c1", type="trade_republic"))
        conn.execute(insert(accounts).values(id=account_id, connector_id="c1", name="A", type="cto"))
        conn.execute(insert(balance_snapshots).values(
            account_id=account_id, date="2026-04-27",
            cash=0, positions_value=value, total_value=value,
            positions=[{"symbol": "VWCE", "qty": 10, "price": value/10, "value": value}],
        ))


def test_create_asset_target(client):
    user_id = _setup(client)
    _seed_account(user_id)
    r = client.post("/api/targets", json={
        "name": "5K sur VWCE", "type": "asset", "target_amount": 5000,
        "asset_account_id": "acc1", "asset_symbol": "VWCE", "slices": []
    })
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["name"] == "5K sur VWCE"
    assert body["type"] == "asset"
    assert body["id"] > 0


def test_create_bucket_target(client):
    user_id = _setup(client)
    _seed_account(user_id, "acc1")
    r = client.post("/api/targets", json={
        "name": "Apport immo", "type": "bucket", "target_amount": 20000,
        "slices": [{"account_id": "acc1", "allocation_kind": "percent", "allocation_value": 50}]
    })
    assert r.status_code == 201
    body = r.json()
    assert body["type"] == "bucket"
    assert len(body["slices"]) == 1


def test_list_targets(client):
    user_id = _setup(client)
    _seed_account(user_id)
    client.post("/api/targets", json={"name": "T1", "type": "bucket", "target_amount": 1000, "slices": []})
    client.post("/api/targets", json={"name": "T2", "type": "bucket", "target_amount": 2000, "slices": []})
    r = client.get("/api/targets")
    assert r.status_code == 200
    assert len(r.json()) == 2


def test_get_target(client):
    user_id = _setup(client)
    _seed_account(user_id)
    cr = client.post("/api/targets", json={"name": "T1", "type": "bucket", "target_amount": 1000, "slices": []})
    tid = cr.json()["id"]
    r = client.get(f"/api/targets/{tid}")
    assert r.status_code == 200
    assert r.json()["name"] == "T1"


def test_get_target_404(client):
    _setup(client)
    r = client.get("/api/targets/9999")
    assert r.status_code == 404


def test_update_target(client):
    user_id = _setup(client)
    _seed_account(user_id)
    cr = client.post("/api/targets", json={"name": "T1", "type": "bucket", "target_amount": 1000, "slices": []})
    tid = cr.json()["id"]
    r = client.put(f"/api/targets/{tid}", json={"name": "T1 renamed", "target_amount": 1500})
    assert r.status_code == 200
    assert r.json()["name"] == "T1 renamed"
    assert r.json()["target_amount"] == 1500


def test_delete_target(client):
    user_id = _setup(client)
    _seed_account(user_id)
    cr = client.post("/api/targets", json={"name": "T1", "type": "bucket", "target_amount": 1000, "slices": []})
    tid = cr.json()["id"]
    r = client.delete(f"/api/targets/{tid}")
    assert r.status_code == 204
    r = client.get(f"/api/targets/{tid}")
    assert r.status_code == 404


def test_unauth(client):
    r = client.get("/api/targets")
    assert r.status_code == 401
```

- [ ] **Step 2 : Vérifier l'échec**

```bash
pytest tests/test_api_targets.py -v
```

Expected : FAIL (404 sur tous les endpoints car non câblés).

- [ ] **Step 3 : Implémenter `src/api/targets.py`**

```python
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, insert, update, delete

from src.api import deps
from src.api.middleware import get_current_user, AuthUser
from src.db.models import targets, target_slices
from src.schemas.targets import (
    TargetCreate, TargetUpdate, TargetResponse,
    SliceCreate, SliceUpdate, SliceResponse,
)

router = APIRouter(prefix="/api/targets", tags=["targets"])


def _row_to_target(row, slices: list[SliceResponse]) -> TargetResponse:
    return TargetResponse(
        id=row.id, name=row.name, type=row.type, target_amount=row.target_amount,
        asset_account_id=row.asset_account_id, asset_symbol=row.asset_symbol,
        rate_override=row.rate_override, archived=bool(row.archived),
        created_at=row.created_at, slices=slices,
    )


def _load_slices(conn, target_id: int) -> list[SliceResponse]:
    rows = conn.execute(
        select(target_slices).where(target_slices.c.target_id == target_id)
    ).fetchall()
    return [
        SliceResponse(
            id=r.id, account_id=r.account_id,
            allocation_kind=r.allocation_kind, allocation_value=r.allocation_value,
        )
        for r in rows
    ]


@router.post("", response_model=TargetResponse, status_code=status.HTTP_201_CREATED)
def create_target(payload: TargetCreate, user: AuthUser = Depends(get_current_user)):
    if payload.type == "asset" and (not payload.asset_account_id or not payload.asset_symbol):
        raise HTTPException(400, "Une cible 'asset' nécessite asset_account_id et asset_symbol")
    if payload.type == "bucket" and (payload.asset_account_id or payload.asset_symbol):
        raise HTTPException(400, "Une cible 'bucket' ne porte pas asset_account_id/asset_symbol")
    engine = deps.get_ledger(user.id)
    with engine.begin() as conn:
        result = conn.execute(insert(targets).values(
            name=payload.name, type=payload.type, target_amount=payload.target_amount,
            asset_account_id=payload.asset_account_id, asset_symbol=payload.asset_symbol,
            rate_override=payload.rate_override,
        ))
        target_id = result.inserted_primary_key[0]
        if payload.type == "bucket":
            for s in payload.slices:
                conn.execute(insert(target_slices).values(
                    target_id=target_id, account_id=s.account_id,
                    allocation_kind=s.allocation_kind, allocation_value=s.allocation_value,
                ))
        row = conn.execute(select(targets).where(targets.c.id == target_id)).fetchone()
        slices = _load_slices(conn, target_id)
    return _row_to_target(row, slices)


@router.get("", response_model=list[TargetResponse])
def list_targets(archived: bool = False, user: AuthUser = Depends(get_current_user)):
    engine = deps.get_ledger(user.id)
    with engine.connect() as conn:
        stmt = select(targets)
        if not archived:
            stmt = stmt.where(targets.c.archived == 0)
        rows = conn.execute(stmt.order_by(targets.c.id.desc())).fetchall()
        out = [_row_to_target(r, _load_slices(conn, r.id)) for r in rows]
    return out


@router.get("/{target_id}", response_model=TargetResponse)
def get_target(target_id: int, user: AuthUser = Depends(get_current_user)):
    engine = deps.get_ledger(user.id)
    with engine.connect() as conn:
        row = conn.execute(select(targets).where(targets.c.id == target_id)).fetchone()
        if not row:
            raise HTTPException(404, "Cible introuvable")
        slices = _load_slices(conn, target_id)
    return _row_to_target(row, slices)


@router.put("/{target_id}", response_model=TargetResponse)
def update_target(target_id: int, payload: TargetUpdate, user: AuthUser = Depends(get_current_user)):
    engine = deps.get_ledger(user.id)
    values = payload.model_dump(exclude_unset=True)
    if "archived" in values:
        values["archived"] = 1 if values["archived"] else 0
    with engine.begin() as conn:
        existing = conn.execute(select(targets).where(targets.c.id == target_id)).fetchone()
        if not existing:
            raise HTTPException(404, "Cible introuvable")
        if values:
            conn.execute(update(targets).where(targets.c.id == target_id).values(**values))
        row = conn.execute(select(targets).where(targets.c.id == target_id)).fetchone()
        slices = _load_slices(conn, target_id)
    return _row_to_target(row, slices)


@router.delete("/{target_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_target(target_id: int, user: AuthUser = Depends(get_current_user)):
    engine = deps.get_ledger(user.id)
    with engine.begin() as conn:
        existing = conn.execute(select(targets).where(targets.c.id == target_id)).fetchone()
        if not existing:
            raise HTTPException(404, "Cible introuvable")
        conn.execute(delete(target_slices).where(target_slices.c.target_id == target_id))
        conn.execute(delete(targets).where(targets.c.id == target_id))
    return None
```

- [ ] **Step 4 : Wire dans le router**

Modifier `src/api/router.py` :

```python
from src.api.targets import router as targets_router
# ...
api_router.include_router(targets_router)
```

- [ ] **Step 5 : Vérifier les tests CRUD**

```bash
pytest tests/test_api_targets.py -v
```

Expected : tous les tests CRUD PASS (sauf ceux des slices et progression encore non câblés, à venir Tasks 9-10).

- [ ] **Step 6 : Commit**

```bash
git add src/api/targets.py src/api/router.py tests/test_api_targets.py
git commit -m "feat(targets): API CRUD targets"
```

---

## Task 9 : API CRUD `slices`

**Files:**
- Modify: `src/api/targets.py`
- Modify: `tests/test_api_targets.py`

- [ ] **Step 1 : Tests slices**

Ajouter à `tests/test_api_targets.py` :

```python
def test_add_slice(client):
    user_id = _setup(client)
    _seed_account(user_id, "acc1")
    cr = client.post("/api/targets", json={"name": "T", "type": "bucket", "target_amount": 1000, "slices": []})
    tid = cr.json()["id"]
    r = client.post(f"/api/targets/{tid}/slices", json={
        "account_id": "acc1", "allocation_kind": "percent", "allocation_value": 50
    })
    assert r.status_code == 201
    assert r.json()["account_id"] == "acc1"
    g = client.get(f"/api/targets/{tid}").json()
    assert len(g["slices"]) == 1


def test_add_slice_to_asset_target_rejected(client):
    user_id = _setup(client)
    _seed_account(user_id, "acc1")
    cr = client.post("/api/targets", json={
        "name": "T", "type": "asset", "target_amount": 1000,
        "asset_account_id": "acc1", "asset_symbol": "VWCE", "slices": []
    })
    tid = cr.json()["id"]
    r = client.post(f"/api/targets/{tid}/slices", json={
        "account_id": "acc1", "allocation_kind": "percent", "allocation_value": 50
    })
    assert r.status_code == 400


def test_update_slice(client):
    user_id = _setup(client)
    _seed_account(user_id, "acc1")
    cr = client.post("/api/targets", json={
        "name": "T", "type": "bucket", "target_amount": 1000,
        "slices": [{"account_id": "acc1", "allocation_kind": "percent", "allocation_value": 30}]
    })
    tid = cr.json()["id"]
    sid = cr.json()["slices"][0]["id"]
    r = client.put(f"/api/targets/{tid}/slices/{sid}", json={"allocation_value": 75})
    assert r.status_code == 200
    assert r.json()["allocation_value"] == 75


def test_delete_slice(client):
    user_id = _setup(client)
    _seed_account(user_id, "acc1")
    cr = client.post("/api/targets", json={
        "name": "T", "type": "bucket", "target_amount": 1000,
        "slices": [{"account_id": "acc1", "allocation_kind": "amount", "allocation_value": 500}]
    })
    tid = cr.json()["id"]
    sid = cr.json()["slices"][0]["id"]
    r = client.delete(f"/api/targets/{tid}/slices/{sid}")
    assert r.status_code == 204
    g = client.get(f"/api/targets/{tid}").json()
    assert len(g["slices"]) == 0
```

- [ ] **Step 2 : Vérifier l'échec**

```bash
pytest tests/test_api_targets.py -v -k slice
```

Expected : FAIL (404).

- [ ] **Step 3 : Ajouter les routes slices dans `src/api/targets.py`**

Ajouter à la fin du fichier :

```python
@router.post("/{target_id}/slices", response_model=SliceResponse, status_code=status.HTTP_201_CREATED)
def add_slice(target_id: int, payload: SliceCreate, user: AuthUser = Depends(get_current_user)):
    engine = deps.get_ledger(user.id)
    with engine.begin() as conn:
        target = conn.execute(select(targets).where(targets.c.id == target_id)).fetchone()
        if not target:
            raise HTTPException(404, "Cible introuvable")
        if target.type != "bucket":
            raise HTTPException(400, "Les slices ne s'appliquent qu'aux cibles de type 'bucket'")
        result = conn.execute(insert(target_slices).values(
            target_id=target_id, account_id=payload.account_id,
            allocation_kind=payload.allocation_kind, allocation_value=payload.allocation_value,
        ))
        sid = result.inserted_primary_key[0]
    return SliceResponse(
        id=sid, account_id=payload.account_id,
        allocation_kind=payload.allocation_kind, allocation_value=payload.allocation_value,
    )


@router.put("/{target_id}/slices/{slice_id}", response_model=SliceResponse)
def update_slice(target_id: int, slice_id: int, payload: SliceUpdate,
                 user: AuthUser = Depends(get_current_user)):
    engine = deps.get_ledger(user.id)
    values = payload.model_dump(exclude_unset=True)
    with engine.begin() as conn:
        existing = conn.execute(
            select(target_slices).where(target_slices.c.id == slice_id)
                                 .where(target_slices.c.target_id == target_id)
        ).fetchone()
        if not existing:
            raise HTTPException(404, "Slice introuvable")
        if values:
            conn.execute(update(target_slices).where(target_slices.c.id == slice_id).values(**values))
        row = conn.execute(select(target_slices).where(target_slices.c.id == slice_id)).fetchone()
    return SliceResponse(
        id=row.id, account_id=row.account_id,
        allocation_kind=row.allocation_kind, allocation_value=row.allocation_value,
    )


@router.delete("/{target_id}/slices/{slice_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_slice(target_id: int, slice_id: int, user: AuthUser = Depends(get_current_user)):
    engine = deps.get_ledger(user.id)
    with engine.begin() as conn:
        existing = conn.execute(
            select(target_slices).where(target_slices.c.id == slice_id)
                                 .where(target_slices.c.target_id == target_id)
        ).fetchone()
        if not existing:
            raise HTTPException(404, "Slice introuvable")
        conn.execute(delete(target_slices).where(target_slices.c.id == slice_id))
    return None
```

- [ ] **Step 4 : Vérifier les tests slices**

```bash
pytest tests/test_api_targets.py -v -k slice
```

Expected : 4 PASS.

- [ ] **Step 5 : Commit**

```bash
git add src/api/targets.py tests/test_api_targets.py
git commit -m "feat(targets): API CRUD slices"
```

---

## Task 10 : API GET `/api/targets/{id}/progression`

**Files:**
- Modify: `src/api/targets.py`
- Modify: `tests/test_api_targets.py`

- [ ] **Step 1 : Tests progression**

Ajouter à `tests/test_api_targets.py` :

```python
def test_progression_asset(client):
    user_id = _setup(client)
    _seed_account(user_id, "acc1", value=2500)
    cr = client.post("/api/targets", json={
        "name": "T", "type": "asset", "target_amount": 5000,
        "asset_account_id": "acc1", "asset_symbol": "VWCE", "slices": []
    })
    tid = cr.json()["id"]
    r = client.get(f"/api/targets/{tid}/progression")
    assert r.status_code == 200
    body = r.json()
    assert body["target_id"] == tid
    assert body["target_amount"] == 5000
    assert body["current_value"] == 2500
    assert body["progress_pct"] == 50.0


def test_progression_bucket_with_override(client):
    user_id = _setup(client)
    _seed_account(user_id, "acc1", value=10000)
    cr = client.post("/api/targets", json={
        "name": "T", "type": "bucket", "target_amount": 8000,
        "rate_override": 200,
        "slices": [{"account_id": "acc1", "allocation_kind": "percent", "allocation_value": 30}]
    })
    tid = cr.json()["id"]
    r = client.get(f"/api/targets/{tid}/progression")
    body = r.json()
    assert body["current_value"] == 3000.0
    assert body["rate"] == 200.0
    assert body["rate_source"] == "override"
    assert body["eta_status"] == "ok"
    assert abs(body["eta_months"] - 25.0) < 0.1


def test_progression_reached(client):
    user_id = _setup(client)
    _seed_account(user_id, "acc1", value=10000)
    cr = client.post("/api/targets", json={
        "name": "T", "type": "asset", "target_amount": 5000,
        "asset_account_id": "acc1", "asset_symbol": "VWCE", "slices": []
    })
    tid = cr.json()["id"]
    r = client.get(f"/api/targets/{tid}/progression").json()
    assert r["eta_status"] == "reached"
    assert r["eta_months"] is None
```

- [ ] **Step 2 : Vérifier l'échec**

```bash
pytest tests/test_api_targets.py -v -k progression
```

Expected : FAIL (404).

- [ ] **Step 3 : Ajouter la route progression**

Modifier `src/api/targets.py`. En tête, ajouter les imports :

```python
from datetime import date as _date
from src.services.target_progression import (
    compute_current_value, compute_rate, compute_eta, compute_history,
)
from src.schemas.targets import ProgressionResponse, HistoryPoint
```

Et ajouter la route :

```python
@router.get("/{target_id}/progression", response_model=ProgressionResponse)
def get_progression(target_id: int, user: AuthUser = Depends(get_current_user)):
    engine = deps.get_ledger(user.id)
    with engine.connect() as conn:
        row = conn.execute(select(targets).where(targets.c.id == target_id)).fetchone()
        if not row:
            raise HTTPException(404, "Cible introuvable")
        slices_rows = conn.execute(
            select(target_slices).where(target_slices.c.target_id == target_id)
        ).fetchall()

    target = {
        "type": row.type,
        "asset_account_id": row.asset_account_id,
        "asset_symbol": row.asset_symbol,
        "rate_override": row.rate_override,
    }
    slices = [
        {"account_id": s.account_id, "allocation_kind": s.allocation_kind,
         "allocation_value": s.allocation_value}
        for s in slices_rows
    ]
    today = _date.today()
    current = compute_current_value(target, slices, engine, today)
    rate, source = compute_rate(target, slices, engine, today)
    eta_months, eta_status = compute_eta(row.target_amount, current, rate)
    history = compute_history(target, slices, engine, today)
    progress_pct = (current / row.target_amount * 100.0) if row.target_amount > 0 else 0.0

    return ProgressionResponse(
        target_id=target_id,
        target_amount=row.target_amount,
        current_value=current,
        progress_pct=progress_pct,
        rate=rate,
        rate_source=source,
        eta_months=eta_months,
        eta_status=eta_status,
        history=[HistoryPoint(date=p["date"], value=p["value"]) for p in history],
    )
```

- [ ] **Step 4 : Vérifier les tests**

```bash
pytest tests/test_api_targets.py -v
```

Expected : tous PASS (CRUD + slices + progression).

- [ ] **Step 5 : Commit**

```bash
git add src/api/targets.py tests/test_api_targets.py
git commit -m "feat(targets): API progression (current_value + rate + eta + history)"
```

---

## Task 11 : Frontend — types + API client

**Files:**
- Create: `frontend/src/lib/targets.ts`
- Create: `frontend/src/api/targets.ts`

- [ ] **Step 1 : Types**

```typescript
// frontend/src/lib/targets.ts
export type TargetType = 'asset' | 'bucket';
export type AllocationKind = 'amount' | 'percent';
export type RateSource = 'auto' | 'override';
export type EtaStatus = 'reached' | 'ok' | 'insufficient';

export interface Slice {
  id: number;
  account_id: string;
  allocation_kind: AllocationKind;
  allocation_value: number;
}

export interface Target {
  id: number;
  name: string;
  type: TargetType;
  target_amount: number;
  asset_account_id: string | null;
  asset_symbol: string | null;
  rate_override: number | null;
  archived: boolean;
  created_at: string;
  slices: Slice[];
}

export interface HistoryPoint {
  date: string;
  value: number;
}

export interface Progression {
  target_id: number;
  target_amount: number;
  current_value: number;
  progress_pct: number;
  rate: number;
  rate_source: RateSource;
  eta_months: number | null;
  eta_status: EtaStatus;
  history: HistoryPoint[];
}

export interface TargetCreatePayload {
  name: string;
  type: TargetType;
  target_amount: number;
  asset_account_id?: string;
  asset_symbol?: string;
  rate_override?: number | null;
  slices: { account_id: string; allocation_kind: AllocationKind; allocation_value: number }[];
}
```

- [ ] **Step 2 : Client API**

```typescript
// frontend/src/api/targets.ts
import { api } from './client';
import type {
  Target, Progression, Slice, TargetCreatePayload, AllocationKind,
} from '../lib/targets';

export function listTargets(archived = false): Promise<Target[]> {
  return api.get<Target[]>('/targets', { archived });
}

export function getTarget(id: number): Promise<Target> {
  return api.get<Target>(`/targets/${id}`);
}

export function createTarget(payload: TargetCreatePayload): Promise<Target> {
  return api.post<Target>('/targets', payload);
}

export function updateTarget(id: number, patch: Partial<{
  name: string; target_amount: number; rate_override: number | null; archived: boolean;
}>): Promise<Target> {
  return api.put<Target>(`/targets/${id}`, patch);
}

export function deleteTarget(id: number): Promise<void> {
  return api.del(`/targets/${id}`);
}

export function addSlice(targetId: number, payload: {
  account_id: string; allocation_kind: AllocationKind; allocation_value: number;
}): Promise<Slice> {
  return api.post<Slice>(`/targets/${targetId}/slices`, payload);
}

export function updateSlice(targetId: number, sliceId: number, patch: Partial<{
  account_id: string; allocation_kind: AllocationKind; allocation_value: number;
}>): Promise<Slice> {
  return api.put<Slice>(`/targets/${targetId}/slices/${sliceId}`, patch);
}

export function deleteSlice(targetId: number, sliceId: number): Promise<void> {
  return api.del(`/targets/${targetId}/slices/${sliceId}`);
}

export function getProgression(targetId: number): Promise<Progression> {
  return api.get<Progression>(`/targets/${targetId}/progression`);
}
```

- [ ] **Step 3 : Vérifier la compilation TS**

```bash
cd frontend && bun run build 2>&1 | tail -20
```

Expected : pas d'erreurs sur les nouveaux fichiers (peut sortir des warnings sans rapport).

- [ ] **Step 4 : Commit**

```bash
git add frontend/src/lib/targets.ts frontend/src/api/targets.ts
git commit -m "feat(targets): types + client API frontend"
```

---

## Task 12 : Frontend — page liste `/objectifs`

**Note d'ordonnancement frontend (Tasks 12-14) :** ces 3 tâches forment un bloc qui doit être implémenté en succession rapprochée. Entre la fin de Task 12 et celle de Task 13, le build TS sera cassé car `Objectifs.tsx` importe `TargetCreateModal` (créée en T13) ; et la route `/objectifs/:id` référence `ObjectifDetail` (créé en T14). C'est attendu et accepté — on ne lance `bun run build` qu'à la fin de Task 14 pour valider l'ensemble.

**Files:**
- Create: `frontend/src/pages/Objectifs.tsx`
- Modify: `frontend/src/App.tsx` (route)
- Modify: `frontend/src/layouts/AppLayout.tsx` (entrée nav)

- [ ] **Step 1 : Page Objectifs**

```tsx
// frontend/src/pages/Objectifs.tsx
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Card, CardBody, CardHeader, Button, Progress, Chip } from '@heroui/react';
import { listTargets, getProgression } from '@/api/targets';
import type { Target, Progression } from '@/lib/targets';
import { TargetCreateModal } from '@/components/TargetCreateModal';

interface TargetWithProgression extends Target {
  progression?: Progression;
}

export function Objectifs() {
  const [targets, setTargets] = useState<TargetWithProgression[]>([]);
  const [loading, setLoading] = useState(true);
  const [showArchived, setShowArchived] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);

  async function load() {
    setLoading(true);
    try {
      const list = await listTargets(showArchived);
      const withProg = await Promise.all(
        list.map(async (t) => {
          try {
            const p = await getProgression(t.id);
            return { ...t, progression: p } as TargetWithProgression;
          } catch {
            return t as TargetWithProgression;
          }
        })
      );
      setTargets(withProg);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [showArchived]);

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Objectifs</h1>
        <div className="flex gap-2">
          <Button
            variant={showArchived ? 'solid' : 'flat'}
            onPress={() => setShowArchived((v) => !v)}
          >
            {showArchived ? 'Afficher actives' : 'Afficher archivées'}
          </Button>
          <Button color="primary" onPress={() => setCreateOpen(true)}>
            Nouvelle cible
          </Button>
        </div>
      </div>

      {loading && <div className="text-sm text-default-500">Chargement…</div>}

      {!loading && targets.length === 0 && (
        <Card><CardBody className="text-center text-default-500 py-12">
          Aucune cible pour l'instant. Crée ta première cible pour démarrer.
        </CardBody></Card>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {targets.map((t) => {
          const pct = Math.min(100, t.progression?.progress_pct ?? 0);
          const eta = t.progression?.eta_months;
          const status = t.progression?.eta_status;
          return (
            <Link key={t.id} to={`/objectifs/${t.id}`}>
              <Card className="hover:scale-[1.01] transition-transform">
                <CardHeader className="flex justify-between items-start">
                  <div>
                    <div className="font-medium">{t.name}</div>
                    <Chip size="sm" variant="flat" className="mt-1">
                      {t.type === 'asset' ? 'Actif' : 'Bucket'}
                    </Chip>
                  </div>
                  <div className="text-right">
                    <div className="text-sm text-default-500">cible</div>
                    <div className="font-mono">{t.target_amount.toLocaleString('fr-FR')} €</div>
                  </div>
                </CardHeader>
                <CardBody className="space-y-2">
                  <Progress value={pct} className="w-full" />
                  <div className="flex justify-between text-sm">
                    <span>{(t.progression?.current_value ?? 0).toLocaleString('fr-FR')} €</span>
                    <span className="text-default-500">{pct.toFixed(1)} %</span>
                  </div>
                  <div className="text-xs text-default-500">
                    {status === 'reached' && '🎉 Atteint'}
                    {status === 'ok' && eta != null && `À ton rythme : ${Math.round(eta)} mois`}
                    {status === 'insufficient' && 'Rythme insuffisant'}
                  </div>
                </CardBody>
              </Card>
            </Link>
          );
        })}
      </div>

      <TargetCreateModal isOpen={createOpen} onClose={() => setCreateOpen(false)} onCreated={load} />
    </div>
  );
}
```

- [ ] **Step 2 : Wire la route dans `App.tsx`**

Ajouter l'import :

```tsx
import { Objectifs } from "@/pages/Objectifs";
import { ObjectifDetail } from "@/pages/ObjectifDetail";
```

Et dans le bloc `vaultState === "unlocked"`, sous `<Route path="/portfolio" ...>` :

```tsx
<Route path="/objectifs" element={<Objectifs />} />
<Route path="/objectifs/:id" element={<ObjectifDetail />} />
```

(`ObjectifDetail` créé en Task 14, mais on déclare la route maintenant. Note : `Objectifs.tsx` importe `TargetCreateModal` qui n'existe pas encore — créé en Task 13 → bun build va échouer ici, c'est attendu, on le résout en Task 13.)

- [ ] **Step 3 : Ajouter l'entrée nav dans `AppLayout.tsx`**

Lire d'abord `frontend/src/layouts/AppLayout.tsx`, repérer la sidebar, ajouter une entrée "Objectifs" après "Portfolio". Utiliser le même pattern (icône HeroUI + Link). Exemple typique :

```tsx
{ path: '/objectifs', label: 'Objectifs', icon: '🎯' }
```

(à adapter au format réel de la sidebar du projet).

- [ ] **Step 4 : Commit (le build est cassé mais c'est temporaire jusqu'à la Task 13)**

```bash
git add frontend/src/pages/Objectifs.tsx frontend/src/App.tsx frontend/src/layouts/AppLayout.tsx
git commit -m "feat(targets): page liste /objectifs (build cassé jusqu'à modale)"
```

---

## Task 13 : Frontend — modale de création

**Files:**
- Create: `frontend/src/components/TargetCreateModal.tsx`

- [ ] **Step 1 : Modale**

```tsx
// frontend/src/components/TargetCreateModal.tsx
import { useEffect, useState } from 'react';
import {
  Modal, ModalContent, ModalHeader, ModalBody, ModalFooter,
  Button, Input, Select, SelectItem, Tabs, Tab,
} from '@heroui/react';
import { createTarget } from '@/api/targets';
import { getAccounts } from '@/api/accounts';
import type { TargetCreatePayload, AllocationKind } from '@/lib/targets';

interface Account { id: string; name?: string | null; type?: string | null; }

interface Props {
  isOpen: boolean;
  onClose: () => void;
  onCreated: () => void;
}

export function TargetCreateModal({ isOpen, onClose, onCreated }: Props) {
  const [type, setType] = useState<'asset' | 'bucket'>('bucket');
  const [name, setName] = useState('');
  const [targetAmount, setTargetAmount] = useState('');
  const [accounts, setAccounts] = useState<Account[]>([]);

  // Type asset
  const [assetAccount, setAssetAccount] = useState('');
  const [assetSymbol, setAssetSymbol] = useState('');

  // Type bucket
  const [slices, setSlices] = useState<Array<{
    account_id: string; allocation_kind: AllocationKind; allocation_value: number;
  }>>([]);

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (isOpen) {
      getAccounts().then(setAccounts).catch(() => setAccounts([]));
      setName('');
      setTargetAmount('');
      setAssetAccount('');
      setAssetSymbol('');
      setSlices([]);
      setError(null);
    }
  }, [isOpen]);

  async function submit() {
    setError(null);
    const amount = parseFloat(targetAmount);
    if (!name.trim() || !(amount > 0)) {
      setError('Nom et montant cible obligatoires');
      return;
    }
    const payload: TargetCreatePayload = { name, type, target_amount: amount, slices: [] };
    if (type === 'asset') {
      if (!assetAccount || !assetSymbol) {
        setError('Compte et symbole obligatoires pour une cible sur actif');
        return;
      }
      payload.asset_account_id = assetAccount;
      payload.asset_symbol = assetSymbol;
    } else {
      payload.slices = slices;
    }
    setSubmitting(true);
    try {
      await createTarget(payload);
      onCreated();
      onClose();
    } catch (e: any) {
      setError(e?.detail ?? 'Erreur à la création');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal isOpen={isOpen} onClose={onClose} size="2xl">
      <ModalContent>
        <ModalHeader>Nouvelle cible</ModalHeader>
        <ModalBody className="space-y-4">
          <Tabs selectedKey={type} onSelectionChange={(k) => setType(k as 'asset' | 'bucket')}>
            <Tab key="bucket" title="Bucket abstrait">
              <div className="space-y-2 mt-2">
                <p className="text-sm text-default-500">
                  Composé de slices d'allocation sur tes comptes (ex. 30 % du CTO + 1 500 € du Livret A).
                </p>
              </div>
            </Tab>
            <Tab key="asset" title="Actif précis">
              <div className="space-y-2 mt-2">
                <p className="text-sm text-default-500">
                  Lié à une position spécifique (ex. atteindre 5 000 € sur VWCE).
                </p>
              </div>
            </Tab>
          </Tabs>

          <Input label="Nom" value={name} onValueChange={setName} placeholder="Ex. Apport immo" />
          <Input
            label="Montant cible (€)"
            type="number"
            value={targetAmount}
            onValueChange={setTargetAmount}
          />

          {type === 'asset' && (
            <>
              <Select
                label="Compte"
                selectedKeys={assetAccount ? [assetAccount] : []}
                onSelectionChange={(k) => setAssetAccount(Array.from(k)[0] as string ?? '')}
              >
                {accounts.map((a) => (
                  <SelectItem key={a.id}>{a.name ?? a.id}</SelectItem>
                ))}
              </Select>
              <Input
                label="Symbole / ISIN"
                value={assetSymbol}
                onValueChange={setAssetSymbol}
                placeholder="VWCE / IE00BK5BQT80"
              />
            </>
          )}

          {type === 'bucket' && (
            <SliceListEditor accounts={accounts} slices={slices} onChange={setSlices} />
          )}

          {error && <p className="text-sm text-mm-loss">{error}</p>}
        </ModalBody>
        <ModalFooter>
          <Button variant="flat" onPress={onClose}>Annuler</Button>
          <Button color="primary" onPress={submit} isLoading={submitting}>Créer</Button>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
}

function SliceListEditor({
  accounts, slices, onChange,
}: {
  accounts: Account[];
  slices: Array<{ account_id: string; allocation_kind: AllocationKind; allocation_value: number; }>;
  onChange: (s: typeof slices) => void;
}) {
  function addSlice() {
    onChange([...slices, { account_id: accounts[0]?.id ?? '', allocation_kind: 'percent', allocation_value: 0 }]);
  }
  function update(idx: number, patch: Partial<typeof slices[0]>) {
    const next = slices.slice();
    next[idx] = { ...next[idx], ...patch };
    onChange(next);
  }
  function remove(idx: number) {
    onChange(slices.filter((_, i) => i !== idx));
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium">Slices d'allocation</span>
        <Button size="sm" variant="flat" onPress={addSlice}>+ Ajouter</Button>
      </div>
      {slices.length === 0 && (
        <p className="text-xs text-default-500">Ajoute au moins une slice (un compte source + montant ou %).</p>
      )}
      {slices.map((s, i) => (
        <div key={i} className="flex gap-2 items-end">
          <Select
            label="Compte"
            className="flex-1"
            selectedKeys={s.account_id ? [s.account_id] : []}
            onSelectionChange={(k) => update(i, { account_id: Array.from(k)[0] as string ?? '' })}
          >
            {accounts.map((a) => (
              <SelectItem key={a.id}>{a.name ?? a.id}</SelectItem>
            ))}
          </Select>
          <Select
            label="Type"
            className="w-32"
            selectedKeys={[s.allocation_kind]}
            onSelectionChange={(k) => update(i, { allocation_kind: Array.from(k)[0] as AllocationKind })}
          >
            <SelectItem key="percent">%</SelectItem>
            <SelectItem key="amount">€</SelectItem>
          </Select>
          <Input
            label="Valeur"
            type="number"
            className="w-32"
            value={String(s.allocation_value)}
            onValueChange={(v) => update(i, { allocation_value: parseFloat(v) || 0 })}
          />
          <Button size="sm" color="danger" variant="flat" onPress={() => remove(i)}>×</Button>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 2 : Vérifier la syntaxe du fichier modale uniquement**

```bash
cd frontend && bunx tsc --noEmit src/components/TargetCreateModal.tsx 2>&1 | head -20
```

Expected : pas d'erreur sur ce fichier (les erreurs sur `Objectifs.tsx`/`ObjectifDetail.tsx` sont attendues à ce stade — la vérif globale du build se fait en fin de Task 14).

- [ ] **Step 3 : Test manuel rapide (après Task 14 complète)**

Une fois Task 14 finie, démarrer dev :

```bash
./start.sh
# autre terminal
cd frontend && bun run dev
```

Aller sur `http://localhost:3000/objectifs`, cliquer "Nouvelle cible" → modale s'ouvre, créer un bucket, vérifier qu'il apparaît dans la liste.

- [ ] **Step 4 : Commit**

```bash
git add frontend/src/components/TargetCreateModal.tsx
git commit -m "feat(targets): modale de création (asset + bucket)"
```

---

## Task 14 : Frontend — page détail `/objectifs/:id`

**Files:**
- Create: `frontend/src/pages/ObjectifDetail.tsx`
- Create: `frontend/src/components/TargetSliceEditor.tsx`

- [ ] **Step 1 : Composant édition de slices**

```tsx
// frontend/src/components/TargetSliceEditor.tsx
import { useState } from 'react';
import { Button, Input, Select, SelectItem } from '@heroui/react';
import type { Slice, AllocationKind } from '@/lib/targets';
import { addSlice, updateSlice, deleteSlice } from '@/api/targets';

interface Account { id: string; name?: string | null; }

interface Props {
  targetId: number;
  slices: Slice[];
  accounts: Account[];
  onChange: () => void;
}

export function TargetSliceEditor({ targetId, slices, accounts, onChange }: Props) {
  const [pending, setPending] = useState(false);

  async function add() {
    setPending(true);
    try {
      await addSlice(targetId, {
        account_id: accounts[0]?.id ?? '',
        allocation_kind: 'percent',
        allocation_value: 0,
      });
      onChange();
    } finally { setPending(false); }
  }

  async function update(slice: Slice, patch: Partial<{
    account_id: string; allocation_kind: AllocationKind; allocation_value: number;
  }>) {
    await updateSlice(targetId, slice.id, patch);
    onChange();
  }

  async function remove(slice: Slice) {
    await deleteSlice(targetId, slice.id);
    onChange();
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <span className="font-medium">Slices d'allocation</span>
        <Button size="sm" variant="flat" onPress={add} isLoading={pending}>+ Ajouter</Button>
      </div>
      {slices.length === 0 && (
        <p className="text-sm text-default-500">Aucune slice. Ajoute au moins un compte source.</p>
      )}
      {slices.map((s) => (
        <div key={s.id} className="flex gap-2 items-end">
          <Select
            label="Compte"
            className="flex-1"
            selectedKeys={[s.account_id]}
            onSelectionChange={(k) => update(s, { account_id: Array.from(k)[0] as string })}
          >
            {accounts.map((a) => (
              <SelectItem key={a.id}>{a.name ?? a.id}</SelectItem>
            ))}
          </Select>
          <Select
            label="Type"
            className="w-32"
            selectedKeys={[s.allocation_kind]}
            onSelectionChange={(k) => update(s, { allocation_kind: Array.from(k)[0] as AllocationKind })}
          >
            <SelectItem key="percent">%</SelectItem>
            <SelectItem key="amount">€</SelectItem>
          </Select>
          <Input
            label="Valeur"
            type="number"
            className="w-32"
            defaultValue={String(s.allocation_value)}
            onBlur={(e) => {
              const v = parseFloat((e.target as HTMLInputElement).value);
              if (!Number.isNaN(v) && v !== s.allocation_value) update(s, { allocation_value: v });
            }}
          />
          <Button size="sm" color="danger" variant="flat" onPress={() => remove(s)}>×</Button>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 2 : Page détail**

```tsx
// frontend/src/pages/ObjectifDetail.tsx
import { useCallback, useEffect, useState } from 'react';
import { useNavigate, useParams, Link } from 'react-router-dom';
import {
  Card, CardBody, CardHeader, Button, Progress, Chip, Input, Spacer,
} from '@heroui/react';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts';
import { getTarget, deleteTarget, getProgression, updateTarget } from '@/api/targets';
import { getAccounts } from '@/api/accounts';
import { TargetSliceEditor } from '@/components/TargetSliceEditor';
import type { Target, Progression } from '@/lib/targets';

interface Account { id: string; name?: string | null; }

export function ObjectifDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const targetId = Number(id);
  const [target, setTarget] = useState<Target | null>(null);
  const [progression, setProgression] = useState<Progression | null>(null);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [overrideInput, setOverrideInput] = useState('');

  const load = useCallback(async () => {
    const [t, p, accs] = await Promise.all([
      getTarget(targetId), getProgression(targetId), getAccounts(),
    ]);
    setTarget(t);
    setProgression(p);
    setAccounts(accs);
    setOverrideInput(t.rate_override == null ? '' : String(t.rate_override));
  }, [targetId]);

  useEffect(() => { load(); }, [load]);

  async function saveOverride() {
    const val = overrideInput.trim() === '' ? null : parseFloat(overrideInput);
    if (val !== null && Number.isNaN(val)) return;
    await updateTarget(targetId, { rate_override: val });
    load();
  }

  async function remove() {
    if (!confirm('Supprimer cette cible ?')) return;
    await deleteTarget(targetId);
    navigate('/objectifs');
  }

  if (!target || !progression) return <div className="p-6 text-default-500">Chargement…</div>;

  const pct = Math.min(100, progression.progress_pct);
  const eta = progression.eta_months;
  const status = progression.eta_status;

  return (
    <div className="p-6 space-y-4 max-w-5xl mx-auto">
      <div className="flex items-center gap-2 text-sm text-default-500">
        <Link to="/objectifs">← Objectifs</Link>
      </div>

      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold">{target.name}</h1>
          <Chip size="sm" variant="flat" className="mt-1">
            {target.type === 'asset' ? 'Actif précis' : 'Bucket'}
          </Chip>
        </div>
        <Button color="danger" variant="flat" onPress={remove}>Supprimer</Button>
      </div>

      <Card>
        <CardBody className="space-y-3">
          <div className="flex justify-between items-end">
            <div>
              <div className="text-sm text-default-500">Valeur courante</div>
              <div className="text-3xl font-mono">{progression.current_value.toLocaleString('fr-FR')} €</div>
            </div>
            <div className="text-right">
              <div className="text-sm text-default-500">Cible</div>
              <div className="text-2xl font-mono">{target.target_amount.toLocaleString('fr-FR')} €</div>
            </div>
          </div>
          <Progress value={pct} className="w-full" />
          <div className="flex justify-between text-sm text-default-500">
            <span>{pct.toFixed(1)} % atteint</span>
            <span>
              {status === 'reached' && '🎉 Objectif atteint'}
              {status === 'ok' && eta != null && `Au rythme actuel (${progression.rate.toFixed(0)} €/mois) → ${Math.round(eta)} mois`}
              {status === 'insufficient' && 'Rythme insuffisant'}
            </span>
          </div>
        </CardBody>
      </Card>

      <Card>
        <CardHeader>Historique</CardHeader>
        <CardBody>
          {progression.history.length === 0 ? (
            <p className="text-sm text-default-500">Pas encore d'historique disponible.</p>
          ) : (
            <ResponsiveContainer width="100%" height={240}>
              <LineChart data={progression.history}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="date" />
                <YAxis />
                <Tooltip />
                <Line type="monotone" dataKey="value" stroke="var(--mm-gain)" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          )}
        </CardBody>
      </Card>

      <Card>
        <CardHeader>Rythme estimé</CardHeader>
        <CardBody className="space-y-2">
          <div className="text-sm text-default-500">
            Source : {progression.rate_source === 'auto' ? 'calcul automatique sur 3 mois' : 'override manuel'}.
            Valeur : {progression.rate.toFixed(2)} €/mois.
          </div>
          <div className="flex gap-2 items-end">
            <Input
              label="Override (€/mois)"
              placeholder={progression.rate_source === 'auto' ? `auto: ${progression.rate.toFixed(0)}` : ''}
              value={overrideInput}
              onValueChange={setOverrideInput}
              type="number"
            />
            <Button onPress={saveOverride}>Enregistrer</Button>
          </div>
          <p className="text-xs text-default-500">Vide = retour au calcul automatique.</p>
        </CardBody>
      </Card>

      {target.type === 'bucket' && (
        <Card>
          <CardHeader>Composition (slices)</CardHeader>
          <CardBody>
            <TargetSliceEditor
              targetId={targetId}
              slices={target.slices}
              accounts={accounts}
              onChange={load}
            />
          </CardBody>
        </Card>
      )}

      {target.type === 'asset' && (
        <Card>
          <CardHeader>Position suivie</CardHeader>
          <CardBody className="text-sm">
            <p>Compte : <code>{target.asset_account_id}</code></p>
            <p>Symbole : <code>{target.asset_symbol}</code></p>
            <p className="text-default-500 mt-2">
              La valeur courante est lue automatiquement depuis cette position.
            </p>
          </CardBody>
        </Card>
      )}

      <Spacer y={4} />
    </div>
  );
}
```

- [ ] **Step 3 : Vérifier le build**

```bash
cd frontend && bun run build 2>&1 | tail -10
```

Expected : pas d'erreur. La route `/objectifs/:id` est maintenant connectée.

- [ ] **Step 4 : Test manuel**

Lancer back + front, créer une cible bucket, ouvrir le détail, ajouter une slice, vérifier que la valeur courante s'actualise.

- [ ] **Step 5 : Commit**

```bash
git add frontend/src/pages/ObjectifDetail.tsx frontend/src/components/TargetSliceEditor.tsx
git commit -m "feat(targets): page détail /objectifs/:id (header, courbe, rythme, slices)"
```

---

## Task 15 : Frontend — card Dashboard

**Files:**
- Create: `frontend/src/components/ObjectifsCard.tsx`
- Modify: `frontend/src/pages/Dashboard.tsx` (intégration)

- [ ] **Step 1 : Card dashboard**

```tsx
// frontend/src/components/ObjectifsCard.tsx
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Card, CardBody, CardHeader, Progress } from '@heroui/react';
import { listTargets, getProgression } from '@/api/targets';
import type { Target, Progression } from '@/lib/targets';

interface Row { target: Target; progression?: Progression; }

export function ObjectifsCard() {
  const [rows, setRows] = useState<Row[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const targets = await listTargets(false);
        const enriched = await Promise.all(
          targets.map(async (t) => {
            try {
              const p = await getProgression(t.id);
              return { target: t, progression: p } as Row;
            } catch {
              return { target: t } as Row;
            }
          })
        );
        if (!cancelled) {
          enriched.sort((a, b) => (b.progression?.progress_pct ?? 0) - (a.progression?.progress_pct ?? 0));
          setRows(enriched.slice(0, 3));
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  return (
    <Card>
      <CardHeader className="flex justify-between">
        <span className="font-medium">Objectifs</span>
        <Link to="/objectifs" className="text-sm text-primary">Voir tout →</Link>
      </CardHeader>
      <CardBody className="space-y-3">
        {loading && <div className="text-sm text-default-500">Chargement…</div>}
        {!loading && rows.length === 0 && (
          <div className="text-sm text-default-500">
            Pas encore de cible. <Link to="/objectifs" className="text-primary">En créer une</Link>.
          </div>
        )}
        {rows.map((r) => {
          const pct = Math.min(100, r.progression?.progress_pct ?? 0);
          return (
            <div key={r.target.id} className="space-y-1">
              <div className="flex justify-between text-sm">
                <Link to={`/objectifs/${r.target.id}`} className="hover:underline">{r.target.name}</Link>
                <span className="text-default-500">{pct.toFixed(0)} %</span>
              </div>
              <Progress value={pct} size="sm" />
            </div>
          );
        })}
      </CardBody>
    </Card>
  );
}
```

- [ ] **Step 2 : Intégrer dans Dashboard.tsx**

Lire `frontend/src/pages/Dashboard.tsx`, ajouter l'import :

```tsx
import { ObjectifsCard } from '@/components/ObjectifsCard';
```

Et placer `<ObjectifsCard />` dans la grille des cards (à l'endroit qui fait le plus de sens visuellement, ex. sous les KPIs principaux).

- [ ] **Step 3 : Test manuel**

Vérifier que la card apparaît sur le Dashboard avec les top 3 cibles, et que les liens fonctionnent.

- [ ] **Step 4 : Commit**

```bash
git add frontend/src/components/ObjectifsCard.tsx frontend/src/pages/Dashboard.tsx
git commit -m "feat(targets): card Objectifs sur le Dashboard"
```

---

## Task 16 : Mise à jour CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1 : Ajouter une note sur le module Objectifs**

Ajouter à la fin de la section "Layout" / "Conventions" / "Gotchas" (selon le contexte le plus pertinent) une ligne :

> **Module Objectifs (ERP)** : nouveau module v1. Cibles type asset (lien vers une position) ou bucket (slices d'allocation compte-niveau, % ou €). API `/api/targets`, page `/objectifs`. Spec : `docs/superpowers/specs/2026-04-27-erp-objectifs-design.md`.

- [ ] **Step 2 : Commit**

```bash
git add CLAUDE.md
git commit -m "docs: note module Objectifs dans CLAUDE.md"
```

---

## Vérification finale

- [ ] **Tous les tests backend**

```bash
source .venv/bin/activate && pytest tests/ -v
```

Expected : aucune régression sur les suites existantes, toutes les nouvelles passent.

- [ ] **Build frontend**

```bash
cd frontend && bun run build
```

Expected : build clean.

- [ ] **Test manuel end-to-end**

1. `./start.sh` (backend) + `cd frontend && bun run dev` (front).
2. Login.
3. Aller sur `/objectifs` → liste vide.
4. "Nouvelle cible" → bucket "Apport immo" 20 000 € avec une slice 30 % d'un compte CTO.
5. Vérifier la card sur le détail (valeur courante non nulle si le compte a un snapshot).
6. Ajouter une seconde slice (1 500 € sur Livret).
7. Saisir un override (300 €/mois) → vérifier que l'ETA recalcule.
8. Vider l'override → retour au calcul auto.
9. Retourner sur `/objectifs` → la cible apparaît avec sa progression.
10. Sur le Dashboard → la card "Objectifs" affiche la cible.
11. Créer une cible "asset" sur un ISIN connu d'une position existante → vérifier que `current_value` colle.

- [ ] **Commit final si nécessaire**

Aucun commit attendu si les tests/build passent sans changement.
