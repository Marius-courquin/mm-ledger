# Performance Chart TWR Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remplacer le chart "Capital NET" du dashboard (et celui des pages détail compte) par un composant à toggle **Valeur | Perf** où la vue Perf montre une vraie courbe TWR (Modified Dietz), calculée par reconstruction des positions historiques à partir des transactions + prix historiques de chaque broker.

**Architecture:** Module Python pur `src/performance.py` (calcul Modified Dietz, testable unitairement sans I/O). Nouvelle table `portfolio_history_daily` peuplée par le manager à la réception d'un event `history_data` émis par chaque worker CTO après connect. Endpoint `/api/performance/history` lit la table, filtre par user/connector/account, renvoie les 2 séries (valeur + cum_pct). Frontend : composant `PortfolioPerfChart` avec toggle, couleurs `--mm-gain` / `--mm-loss` (DA projet).

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2, SQLCipher, React 19, Recharts, TypeScript, `ib_async`, Trade Republic WebSocket API.

**Spec :** `docs/superpowers/specs/2026-04-22-perf-chart-twr-design.md`

---

## Task 1 : Module pur — `performance.reconstruct_timeline`

**Files:**
- Create: `src/performance.py`
- Test: `tests/test_performance.py`

- [ ] **Step 1 : Écrire les tests**

Créer `tests/test_performance.py` :

```python
from src.performance import reconstruct_timeline, TxEvent


def _tx(date: str, kind: str, **kw) -> TxEvent:
    return TxEvent(
        date=date, kind=kind,
        symbol=kw.get("symbol"),
        qty=kw.get("qty", 0.0),
        price=kw.get("price", 0.0),
        amount=kw.get("amount", 0.0),
    )


def test_reconstruct_empty():
    assert reconstruct_timeline([], {}, start_date="2026-01-01", end_date="2026-01-03") == []


def test_reconstruct_buy_only_single_day():
    txs = [_tx("2026-01-02", "buy", symbol="AMZN", qty=1.0, price=200.0, amount=-200.0)]
    prices = {"AMZN": [
        {"date": "2026-01-01", "close": 195.0},
        {"date": "2026-01-02", "close": 200.0},
        {"date": "2026-01-03", "close": 210.0},
    ]}
    timeline = reconstruct_timeline(txs, prices, start_date="2026-01-01", end_date="2026-01-03")
    assert len(timeline) == 3
    # Jour 1 : rien détenu, cash = 0
    assert timeline[0]["date"] == "2026-01-01"
    assert timeline[0]["positions_value"] == 0.0
    assert timeline[0]["cash"] == 0.0
    # Jour 2 : achat 1 AMZN @ 200, cash -200, pos 200 @ close 200
    assert timeline[1]["cash"] == -200.0
    assert timeline[1]["positions_value"] == 200.0
    # Jour 3 : toujours 1 AMZN, close 210 → pos 210
    assert timeline[2]["positions_value"] == 210.0
    assert timeline[2]["total_value"] == -200.0 + 210.0


def test_reconstruct_buy_then_sell():
    txs = [
        _tx("2026-01-02", "buy", symbol="AMZN", qty=2.0, price=200.0, amount=-400.0),
        _tx("2026-01-03", "sell", symbol="AMZN", qty=-1.0, price=250.0, amount=250.0),
    ]
    prices = {"AMZN": [
        {"date": "2026-01-01", "close": 195.0},
        {"date": "2026-01-02", "close": 200.0},
        {"date": "2026-01-03", "close": 250.0},
        {"date": "2026-01-04", "close": 260.0},
    ]}
    timeline = reconstruct_timeline(txs, prices, start_date="2026-01-01", end_date="2026-01-04")
    # Jour 4 : reste 1 AMZN @ 260, cash = -400 + 250 = -150 → total 260 - 150 = 110
    assert timeline[3]["positions_value"] == 260.0
    assert timeline[3]["cash"] == -150.0
    assert timeline[3]["total_value"] == 110.0


def test_reconstruct_external_deposit_tagged():
    txs = [_tx("2026-01-02", "deposit", amount=1000.0)]
    timeline = reconstruct_timeline(txs, {}, start_date="2026-01-01", end_date="2026-01-03")
    assert timeline[0]["cash_flow_external"] == 0.0
    assert timeline[1]["cash_flow_external"] == 1000.0
    assert timeline[1]["cash"] == 1000.0
    assert timeline[2]["cash"] == 1000.0
    assert timeline[2]["cash_flow_external"] == 0.0


def test_reconstruct_dividend_is_internal_gain():
    txs = [
        _tx("2026-01-02", "buy", symbol="AMZN", qty=1.0, price=200.0, amount=-200.0),
        _tx("2026-01-03", "dividend", symbol="AMZN", amount=5.0),
    ]
    prices = {"AMZN": [
        {"date": "2026-01-01", "close": 200.0},
        {"date": "2026-01-02", "close": 200.0},
        {"date": "2026-01-03", "close": 200.0},
    ]}
    timeline = reconstruct_timeline(txs, prices, start_date="2026-01-01", end_date="2026-01-03")
    # Dividende n'est PAS un cash_flow_external — il compte comme perf
    assert timeline[2]["cash_flow_external"] == 0.0
    # Cash = -200 + 5 = -195
    assert timeline[2]["cash"] == -195.0
    # Total = -195 + 200 = 5 (exactement le gain du dividende)
    assert timeline[2]["total_value"] == 5.0
```

- [ ] **Step 2 : Vérifier l'échec**

```
cd /Users/charles/Desktop/mm-ledger && source .venv/bin/activate && pytest tests/test_performance.py -v
```

Expected : FAIL — module `src.performance` inexistant.

- [ ] **Step 3 : Implémenter le module**

Créer `src/performance.py` :

```python
"""Calcul de performance (TWR Modified Dietz) — logique pure, sans I/O.

Entrées : transactions normalisées + prix historiques (tout déjà en base currency).
Sortie : timeline journalière + courbe cumulée %."""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

TxKind = Literal["buy", "sell", "deposit", "withdrawal", "dividend", "fee", "interest"]

# Types de tx classés comme cash flow externe (apport ou retrait — neutralisés dans TWR).
EXTERNAL_KINDS: set[str] = {"deposit", "withdrawal"}


@dataclass
class TxEvent:
    """Transaction normalisée dans la base currency du compte.

    amount : impact signé sur le cash (dépôt +, retrait -, buy -, sell +, dividende +, fee -).
    qty : pour buy/sell uniquement, signé (achat > 0, vente < 0).
    """
    date: str          # YYYY-MM-DD
    kind: TxKind
    symbol: str | None = None
    qty: float = 0.0
    price: float = 0.0
    amount: float = 0.0


def _daterange(start: str, end: str) -> list[str]:
    d0 = date.fromisoformat(start)
    d1 = date.fromisoformat(end)
    return [(d0 + timedelta(days=i)).isoformat() for i in range((d1 - d0).days + 1)]


def reconstruct_timeline(
    transactions: list[TxEvent],
    historical_prices: dict[str, list[dict]],
    start_date: str,
    end_date: str,
) -> list[dict]:
    """Rebuild daily portfolio state from transactions + historical prices.

    Returns : list[{date, cash, positions_value, total_value, cash_flow_external}] sorted ASC.
    """
    if start_date > end_date:
        return []

    price_by_date: dict[str, dict[str, float]] = {}
    for symbol, bars in historical_prices.items():
        for bar in bars:
            price_by_date.setdefault(bar["date"], {})[symbol] = float(bar["close"])

    txs_by_date: dict[str, list[TxEvent]] = {}
    for tx in transactions:
        txs_by_date.setdefault(tx.date, []).append(tx)

    cash = 0.0
    positions: dict[str, float] = {}       # symbol → qty détenue
    result = []

    for d in _daterange(start_date, end_date):
        daily_external_cf = 0.0
        for tx in txs_by_date.get(d, []):
            cash += tx.amount
            if tx.kind in EXTERNAL_KINDS:
                daily_external_cf += tx.amount
            if tx.kind in ("buy", "sell") and tx.symbol:
                positions[tx.symbol] = positions.get(tx.symbol, 0.0) + tx.qty
                if abs(positions[tx.symbol]) < 1e-9:
                    positions.pop(tx.symbol, None)

        positions_value = 0.0
        day_prices = price_by_date.get(d, {})
        for symbol, qty in positions.items():
            price = day_prices.get(symbol)
            if price is None:
                # Fallback : dernier close connu avant d
                price = _last_known_close(historical_prices.get(symbol, []), d)
            if price is not None:
                positions_value += qty * price

        result.append({
            "date": d,
            "cash": round(cash, 4),
            "positions_value": round(positions_value, 4),
            "total_value": round(cash + positions_value, 4),
            "cash_flow_external": round(daily_external_cf, 4),
        })

    return result


def _last_known_close(bars: list[dict], as_of: str) -> float | None:
    candidates = [float(b["close"]) for b in bars if b["date"] <= as_of]
    return candidates[-1] if candidates else None
```

- [ ] **Step 4 : Vérifier que les tests passent**

```
pytest tests/test_performance.py -v
```

Expected : 5 tests PASS.

- [ ] **Step 5 : Commit**

```
git add src/performance.py tests/test_performance.py
git commit -m "feat(performance): module pur reconstruct_timeline (TWR fondation)

Rebuild daily [cash, positions_value, total_value, cash_flow_external]
à partir de transactions normalisées + prix historiques. Cash flows
externes (deposits/withdrawals) taggés pour être neutralisés plus tard
par le calcul TWR."
```

---

## Task 2 : Module pur — `compute_twr` (Modified Dietz chaîné)

**Files:**
- Modify: `src/performance.py`
- Test: `tests/test_performance.py`

- [ ] **Step 1 : Tests**

Ajouter à `tests/test_performance.py` :

```python
from src.performance import compute_twr


def test_twr_flat_no_move():
    timeline = [
        {"date": "2026-01-01", "cash": 0, "positions_value": 1000, "total_value": 1000, "cash_flow_external": 0},
        {"date": "2026-01-02", "cash": 0, "positions_value": 1000, "total_value": 1000, "cash_flow_external": 0},
    ]
    curve = compute_twr(timeline)
    assert len(curve) == 2
    assert curve[0]["cum_pct"] == 0.0
    assert curve[1]["cum_pct"] == 0.0


def test_twr_simple_gain():
    # 1000 → 1100 = +10%
    timeline = [
        {"date": "2026-01-01", "cash": 0, "positions_value": 1000, "total_value": 1000, "cash_flow_external": 0},
        {"date": "2026-01-02", "cash": 0, "positions_value": 1100, "total_value": 1100, "cash_flow_external": 0},
    ]
    curve = compute_twr(timeline)
    assert abs(curve[1]["cum_pct"] - 10.0) < 0.01


def test_twr_neutralizes_deposit():
    # Jour 1 : 1000. Jour 2 : dépôt 500 → total 1500 (pas un gain). Jour 3 : +10% sur 1500 → 1650.
    # TWR doit donner +10% (le dépôt est neutralisé).
    timeline = [
        {"date": "2026-01-01", "cash": 0, "positions_value": 1000, "total_value": 1000, "cash_flow_external": 0},
        {"date": "2026-01-02", "cash": 500, "positions_value": 1000, "total_value": 1500, "cash_flow_external": 500},
        {"date": "2026-01-03", "cash": 500, "positions_value": 1150, "total_value": 1650, "cash_flow_external": 0},
    ]
    curve = compute_twr(timeline)
    # Jour 1 : 0%. Jour 2 : dépôt pur, perf 0%. Jour 3 : gain de 150 sur 1500 = 10%.
    assert abs(curve[0]["cum_pct"] - 0.0) < 0.01
    assert abs(curve[1]["cum_pct"] - 0.0) < 0.01
    assert abs(curve[2]["cum_pct"] - 10.0) < 0.01


def test_twr_handles_zero_base():
    # Compte vide puis premier dépôt : la perf démarre à 0% à partir du dépôt.
    timeline = [
        {"date": "2026-01-01", "cash": 0, "positions_value": 0, "total_value": 0, "cash_flow_external": 0},
        {"date": "2026-01-02", "cash": 1000, "positions_value": 0, "total_value": 1000, "cash_flow_external": 1000},
        {"date": "2026-01-03", "cash": 0, "positions_value": 1100, "total_value": 1100, "cash_flow_external": 0},
    ]
    curve = compute_twr(timeline)
    assert curve[0]["cum_pct"] == 0.0
    assert curve[1]["cum_pct"] == 0.0
    # Jour 3 : gain 100 sur 1000 = +10%
    assert abs(curve[2]["cum_pct"] - 10.0) < 0.01
```

- [ ] **Step 2 : Vérifier l'échec**

```
pytest tests/test_performance.py -v
```

Expected : FAIL — `compute_twr` n'existe pas.

- [ ] **Step 3 : Implémenter**

Ajouter à `src/performance.py` :

```python
def compute_twr(timeline: list[dict]) -> list[dict]:
    """Chaîne les rendements journaliers Modified Dietz.

    Formule par jour i :
        r_i = (V_i - V_{i-1} - CF_i) / V_{i-1}
    (le cash flow externe du jour est considéré appliqué en début de jour → neutralisé au
    dénominateur V_{i-1} car il n'y est pas. Version simplifiée du Modified Dietz — suffisante
    pour une granularité journalière où les cash flows intraday ne sont pas observables.)

    Rendement cumulé : ∏ (1 + r_i) − 1, exprimé en pourcentage.
    """
    if not timeline:
        return []

    curve = [{"date": timeline[0]["date"], "cum_pct": 0.0}]
    cumulative_factor = 1.0

    for i in range(1, len(timeline)):
        prev_v = timeline[i - 1]["total_value"]
        curr_v = timeline[i]["total_value"]
        cf = timeline[i].get("cash_flow_external", 0.0)

        if prev_v <= 0:
            # Base nulle ou négative : on ne peut pas dériver un taux, on reporte le cumul sans bouger.
            curve.append({"date": timeline[i]["date"], "cum_pct": round((cumulative_factor - 1) * 100, 4)})
            continue

        daily_return = (curr_v - prev_v - cf) / prev_v
        cumulative_factor *= (1.0 + daily_return)
        curve.append({
            "date": timeline[i]["date"],
            "cum_pct": round((cumulative_factor - 1) * 100, 4),
        })

    return curve
```

- [ ] **Step 4 : Tests passent**

```
pytest tests/test_performance.py -v
```

Expected : 9 tests PASS (5 de Task 1 + 4 nouveaux).

- [ ] **Step 5 : Commit**

```
git add src/performance.py tests/test_performance.py
git commit -m "feat(performance): compute_twr (Modified Dietz chaîné)

Rendement cumulé journalier neutralisant les cash flows externes.
Vérifié : dépôt de 500 au milieu n'affecte pas le %, seul le mouvement
de marché contribue."
```

---

## Task 3 : Module pur — `aggregate_timelines` (multi-connecteur)

**Files:**
- Modify: `src/performance.py`
- Test: `tests/test_performance.py`

- [ ] **Step 1 : Test**

Ajouter :

```python
from src.performance import aggregate_timelines


def test_aggregate_two_connectors_sum_values():
    t1 = [
        {"date": "2026-01-01", "cash": 100, "positions_value": 500, "total_value": 600, "cash_flow_external": 0},
        {"date": "2026-01-02", "cash": 100, "positions_value": 550, "total_value": 650, "cash_flow_external": 0},
    ]
    t2 = [
        {"date": "2026-01-01", "cash": 50, "positions_value": 300, "total_value": 350, "cash_flow_external": 0},
        {"date": "2026-01-02", "cash": 50, "positions_value": 330, "total_value": 380, "cash_flow_external": 0},
    ]
    merged = aggregate_timelines([t1, t2])
    assert len(merged) == 2
    assert merged[0]["total_value"] == 950
    assert merged[1]["total_value"] == 1030
    assert merged[0]["cash_flow_external"] == 0
    assert merged[1]["cash_flow_external"] == 0


def test_aggregate_handles_different_date_ranges():
    # t1 commence plus tôt, t2 plus tard — l'union couvre toute la plage
    t1 = [
        {"date": "2026-01-01", "cash": 0, "positions_value": 100, "total_value": 100, "cash_flow_external": 0},
        {"date": "2026-01-02", "cash": 0, "positions_value": 110, "total_value": 110, "cash_flow_external": 0},
    ]
    t2 = [
        {"date": "2026-01-02", "cash": 0, "positions_value": 200, "total_value": 200, "cash_flow_external": 200},
    ]
    merged = aggregate_timelines([t1, t2])
    assert [m["date"] for m in merged] == ["2026-01-01", "2026-01-02"]
    # Jour 1 : seul t1 a un point, t2 est 0 avant son début
    assert merged[0]["total_value"] == 100
    assert merged[1]["total_value"] == 310
    assert merged[1]["cash_flow_external"] == 200
```

- [ ] **Step 2 : Vérifier échec** (`aggregate_timelines` n'existe pas)

- [ ] **Step 3 : Implémenter**

Ajouter à `src/performance.py` :

```python
def aggregate_timelines(timelines: list[list[dict]]) -> list[dict]:
    """Fusionne plusieurs timelines (1 par connecteur) en sommant les champs numériques
    par date. Avant le premier point d'une timeline donnée, elle contribue à 0."""
    if not timelines:
        return []
    all_dates = sorted({pt["date"] for t in timelines for pt in t})
    if not all_dates:
        return []

    per_timeline_by_date = [
        {pt["date"]: pt for pt in t} for t in timelines
    ]

    merged = []
    for d in all_dates:
        cash = 0.0
        positions_value = 0.0
        total_value = 0.0
        cf_ext = 0.0
        for by_date in per_timeline_by_date:
            pt = by_date.get(d)
            if pt is None:
                continue
            cash += pt["cash"]
            positions_value += pt["positions_value"]
            total_value += pt["total_value"]
            cf_ext += pt.get("cash_flow_external", 0.0)
        merged.append({
            "date": d,
            "cash": round(cash, 4),
            "positions_value": round(positions_value, 4),
            "total_value": round(total_value, 4),
            "cash_flow_external": round(cf_ext, 4),
        })
    return merged
```

- [ ] **Step 4 : Tests passent** (11 tests au total)

- [ ] **Step 5 : Commit**

```
git add src/performance.py tests/test_performance.py
git commit -m "feat(performance): aggregate_timelines (multi-connecteur)"
```

---

## Task 4 : Table DB `portfolio_history_daily`

**Files:**
- Modify: `src/db/models.py`

- [ ] **Step 1 : Ajouter la table dans models.py**

Dans `src/db/models.py`, ajouter après `net_worth_snapshots` :

```python
portfolio_history_daily = Table(
    "portfolio_history_daily", metadata,
    Column("connector_id", Text, nullable=False),
    Column("account_id", Text, nullable=False),
    Column("date", Text, nullable=False),
    Column("total_value", REAL, nullable=False),
    Column("cash", REAL, nullable=False),
    Column("positions_value", REAL, nullable=False),
    Column("cash_flow_external", REAL, nullable=False, default=0.0),
    Column("currency", Text, nullable=False, default="EUR"),
    UniqueConstraint("connector_id", "account_id", "date"),
)

Index(
    "idx_portfolio_history_connector_date",
    portfolio_history_daily.c.connector_id,
    portfolio_history_daily.c.date,
)
```

- [ ] **Step 2 : Vérifier import de `REAL`**

Lire les premières lignes de `src/db/models.py` pour confirmer que `REAL`, `Index`, `UniqueConstraint`, `Text` sont tous importés. Si `REAL` est déjà là (il est utilisé par `balance_snapshots`), OK. Sinon ajouter à l'import.

- [ ] **Step 3 : Smoke test — la table se crée**

```
cd /Users/charles/Desktop/mm-ledger && source .venv/bin/activate && python -c "
from src.db.engine import create_engine_from_path
import tempfile, os
with tempfile.TemporaryDirectory() as d:
    db = os.path.join(d, 'test.db')
    eng = create_engine_from_path(db, password='x')
    from sqlalchemy import inspect
    print('tables:', inspect(eng).get_table_names())
"
```

Expected : sortie inclut `'portfolio_history_daily'`.

- [ ] **Step 4 : Commit**

```
git add src/db/models.py
git commit -m "feat(db): table portfolio_history_daily pour courbe TWR"
```

---

## Task 5 : Base worker — méthode `fetch_history_data`

**Files:**
- Modify: `src/connectors/base.py`

- [ ] **Step 1 : Test**

Ajouter à `tests/test_manager.py` à la fin :

```python
def test_fetch_history_data_cmd_emits_history_data_event():
    mgr = ConnectorManager()

    class HistoryEmittingWorker(ConnectorWorker):
        def connect(self, credentials: dict):
            self.event_queue.put({"type": "status", "state": "connected"})

        def disconnect(self): pass
        def fetch_accounts(self): return []
        def fetch_positions(self): return []
        def fetch_balances(self): return []
        def fetch_transactions(self): return []
        def submit_2fa(self, code: str): pass

        def fetch_history_data(self):
            return {"transactions": [], "historical_prices": {}, "account_id": "ACC1"}

    mgr.register_worker_class("hist", HistoryEmittingWorker)
    mgr.spawn("histuser:conn1", "hist", {})
    time.sleep(0.3)
    mgr.send_command("histuser:conn1", {"type": "fetch_history_data"})
    time.sleep(0.3)
    events = mgr.collect_events()
    history_events = [e for e in events if e.get("type") == "history_data"]
    assert len(history_events) == 1
    assert history_events[0]["data"]["account_id"] == "ACC1"
    mgr.stop("histuser:conn1")
```

Il faut déclarer `HistoryEmittingWorker` au niveau module (comme les autres workers de test) pour que multiprocessing puisse le pickler. **Déplacer la classe avant la fonction de test.**

- [ ] **Step 2 : Vérifier l'échec**

```
pytest tests/test_manager.py::test_fetch_history_data_cmd_emits_history_data_event -v
```

Expected : FAIL — `fetch_history_data` n'est pas dans la dispatch table, donc `KeyError` → event `error`.

- [ ] **Step 3 : Ajouter la méthode + dispatch dans `base.py`**

Dans `src/connectors/base.py`, ajouter une méthode après `submit_2fa` :

```python
    def fetch_history_data(self) -> dict:
        """Retourne {transactions: list[TxEvent-like], historical_prices: dict[symbol, list], account_id: str}.
        Défaut vide — overridable par les connecteurs qui exposent un historique de trades + prix."""
        return {"transactions": [], "historical_prices": {}, "account_id": ""}
```

Et ajouter dans la dispatch table de `run()` :

```python
                handler = {
                    "connect": lambda: self.connect(cmd.get("credentials", {})),
                    "disconnect": self.disconnect,
                    "fetch_accounts": self.fetch_accounts,
                    "fetch_positions": self.fetch_positions,
                    "fetch_balances": self.fetch_balances,
                    "fetch_transactions": self.fetch_transactions,
                    "fetch_history_data": self.fetch_history_data,
                    "submit_2fa": lambda: self.submit_2fa(cmd["code"]),
                }[cmd["type"]]
```

Le mapping `fetch_` → event type : `fetch_history_data` → `"history_data"`. Ça marche déjà grâce à `cmd["type"].replace("fetch_", "")`.

- [ ] **Step 4 : Tests passent**

```
pytest tests/test_manager.py -v
```

Expected : tous PASS.

- [ ] **Step 5 : Commit**

```
git add src/connectors/base.py tests/test_manager.py
git commit -m "feat(base-worker): méthode fetch_history_data + dispatch event history_data"
```

---

## Task 6 : Manager — handler `history_data` qui persiste en DB

**Files:**
- Modify: `src/manager.py`
- Test: `tests/test_manager.py`

- [ ] **Step 1 : Test**

Ajouter à `tests/test_manager.py` :

```python
def test_history_data_event_is_persisted_to_db(tmp_path, monkeypatch):
    """Quand un worker émet history_data, le manager reconstruit la timeline
    et upsert dans portfolio_history_daily."""
    import os
    os.environ["MM_LEDGER_DATA_DIR"] = str(tmp_path)

    from src.api import deps
    from src.db.engine import create_engine_from_path
    from src.db.models import portfolio_history_daily
    from sqlalchemy import select

    db_path = tmp_path / "ledger.db"
    test_engine = create_engine_from_path(str(db_path), password="testpwd")
    monkeypatch.setattr(deps, "get_ledger", lambda user_id: test_engine)

    class HistWorker(ConnectorWorker):
        def connect(self, credentials):
            self.event_queue.put({"type": "status", "state": "connected"})
        def disconnect(self): pass
        def fetch_accounts(self): return []
        def fetch_positions(self): return []
        def fetch_balances(self): return []
        def fetch_transactions(self): return []
        def submit_2fa(self, c): pass
        def fetch_history_data(self):
            from src.performance import TxEvent
            return {
                "account_id": "ACC1",
                "transactions": [
                    {"date": "2026-01-02", "kind": "buy", "symbol": "X",
                     "qty": 1.0, "price": 100.0, "amount": -100.0}
                ],
                "historical_prices": {"X": [
                    {"date": "2026-01-01", "close": 100.0},
                    {"date": "2026-01-02", "close": 100.0},
                    {"date": "2026-01-03", "close": 110.0},
                ]},
                "start_date": "2026-01-01",
                "end_date": "2026-01-03",
                "currency": "EUR",
            }

    mgr = ConnectorManager()
    mgr.register_worker_class("hist", HistWorker)
    mgr.spawn("user42:histconn", "hist", {})
    time.sleep(0.3)
    mgr.send_command("user42:histconn", {"type": "fetch_history_data"})
    time.sleep(0.5)
    mgr.collect_events()

    with test_engine.connect() as conn:
        rows = conn.execute(select(portfolio_history_daily)).fetchall()
    assert len(rows) == 3
    dates = sorted(r.date for r in rows)
    assert dates == ["2026-01-01", "2026-01-02", "2026-01-03"]
    mgr.stop("user42:histconn")
```

Le worker doit être module-level pour pickling : **déplace `HistWorker` au niveau module du fichier de test**.

- [ ] **Step 2 : Vérifier échec**

```
pytest tests/test_manager.py::test_history_data_event_is_persisted_to_db -v
```

Expected : FAIL — rows vide ou erreur.

- [ ] **Step 3 : Implémenter le hook dans `manager.py`**

Dans `src/manager.py`, dans `collect_events`, ajouter le traitement du type `history_data` :

```python
                    elif evt_type == "history_data":
                        self._persist_history_for_worker(cid, event.get("data", {}))
                    elif evt_type in ("accounts", "balances", "positions", "transactions"):
                        if cid not in self.live_data:
                            self.live_data[cid] = {"accounts": [], "balances": [], "positions": [], "transactions": []}
                        self.live_data[cid][evt_type] = event.get("data", [])
```

Et ajouter la méthode :

```python
    def _persist_history_for_worker(self, composite_key: str, data: dict) -> None:
        """Reconstruit la timeline depuis data et upsert dans portfolio_history_daily."""
        if ":" not in composite_key:
            return
        user_id, connector_id = composite_key.split(":", 1)
        account_id = data.get("account_id") or connector_id
        raw_txs = data.get("transactions", [])
        historical_prices = data.get("historical_prices", {})
        start = data.get("start_date")
        end = data.get("end_date")
        currency = data.get("currency", "EUR")
        if not start or not end or not raw_txs:
            return

        from src.performance import reconstruct_timeline, TxEvent
        tx_events = [
            TxEvent(
                date=t["date"], kind=t["kind"],
                symbol=t.get("symbol"),
                qty=float(t.get("qty", 0.0)),
                price=float(t.get("price", 0.0)),
                amount=float(t.get("amount", 0.0)),
            )
            for t in raw_txs
        ]
        timeline = reconstruct_timeline(tx_events, historical_prices, start_date=start, end_date=end)

        from src.api import deps
        from src.db.models import portfolio_history_daily
        from sqlalchemy import insert
        engine = deps.get_ledger(user_id)
        with engine.begin() as conn:
            for pt in timeline:
                conn.execute(
                    insert(portfolio_history_daily).prefix_with("OR REPLACE").values(
                        connector_id=connector_id,
                        account_id=account_id,
                        date=pt["date"],
                        total_value=pt["total_value"],
                        cash=pt["cash"],
                        positions_value=pt["positions_value"],
                        cash_flow_external=pt["cash_flow_external"],
                        currency=currency,
                    )
                )
```

- [ ] **Step 4 : Tests passent**

```
pytest tests/test_manager.py -v
```

Expected : tous PASS.

- [ ] **Step 5 : Commit**

```
git add src/manager.py tests/test_manager.py
git commit -m "feat(manager): persistance timeline dans portfolio_history_daily

Sur event history_data d'un worker, reconstruit via performance.reconstruct_timeline
puis upsert par (connector_id, account_id, date). User isolation via composite key."
```

---

## Task 7 : API — `GET /api/performance/history`

**Files:**
- Modify: `src/api/performance.py` (réécriture complète, l'endpoint actuel n'est pas utilisé)
- Test: `tests/test_api_performance.py` (nouveau)

- [ ] **Step 1 : Test**

Créer `tests/test_api_performance.py` :

```python
import pytest
from fastapi.testclient import TestClient

from src.main import create_app
from src.api import deps
from tests.conftest import _seed_user, _login


@pytest.fixture
def client_with_history(tmp_path, monkeypatch):
    monkeypatch.setenv("MM_LEDGER_DATA_DIR", str(tmp_path))
    app = create_app()
    client = TestClient(app)
    user_id = _seed_user(client, "test", "pwd")
    _login(client, "test", "pwd")

    # Insert fixture rows directly
    from src.db.models import portfolio_history_daily
    from sqlalchemy import insert
    engine = deps.get_ledger(user_id)
    rows = [
        {"connector_id": "ibkr", "account_id": "U1", "date": "2026-01-01",
         "total_value": 1000, "cash": 1000, "positions_value": 0,
         "cash_flow_external": 1000, "currency": "EUR"},
        {"connector_id": "ibkr", "account_id": "U1", "date": "2026-01-02",
         "total_value": 1050, "cash": 1000, "positions_value": 50,
         "cash_flow_external": 0, "currency": "EUR"},
        {"connector_id": "tr", "account_id": "ST1", "date": "2026-01-02",
         "total_value": 2000, "cash": 0, "positions_value": 2000,
         "cash_flow_external": 0, "currency": "EUR"},
    ]
    with engine.begin() as conn:
        for r in rows:
            conn.execute(insert(portfolio_history_daily).values(**r))
    return client


def test_history_aggregated(client_with_history):
    r = client_with_history.get("/api/performance/history?period=All")
    assert r.status_code == 200
    data = r.json()
    assert "series" in data
    # 2 dates uniques dans le fixture
    assert len(data["series"]) == 2
    # Jour 2 : total = 1050 (ibkr) + 2000 (tr) = 3050
    last = data["series"][-1]
    assert last["value"] == 3050


def test_history_filtered_by_connector(client_with_history):
    r = client_with_history.get("/api/performance/history?connector_id=ibkr&period=All")
    assert r.status_code == 200
    data = r.json()
    assert len(data["series"]) == 2
    assert data["series"][-1]["value"] == 1050


def test_history_filtered_by_account(client_with_history):
    r = client_with_history.get("/api/performance/history?account_id=ST1&period=All")
    assert r.status_code == 200
    data = r.json()
    assert len(data["series"]) == 1
    assert data["series"][0]["value"] == 2000
```

Note : les helpers `_seed_user` / `_login` doivent déjà exister dans `tests/conftest.py`. Sinon, lire un test existant comme `tests/test_api_connectors.py` et copier le pattern de setup-auth.

- [ ] **Step 2 : Vérifier échec**

```
pytest tests/test_api_performance.py -v
```

Expected : FAIL — endpoint `/api/performance/history` absent ou ancien schéma.

- [ ] **Step 3 : Réécrire `src/api/performance.py`**

Remplacer intégralement par :

```python
from datetime import date, timedelta
from fastapi import APIRouter, Query, Depends
from sqlalchemy import select

from src.api import deps
from src.api.middleware import get_current_user, AuthUser
from src.db.models import portfolio_history_daily
from src.performance import compute_twr, aggregate_timelines

router = APIRouter(prefix="/api/performance", tags=["performance"])

PERIOD_DAYS = {"1W": 7, "1M": 30, "3M": 90, "1Y": 365, "All": None}


def _period_start(period: str) -> str | None:
    days = PERIOD_DAYS.get(period, 90)
    if days is None:
        return None
    return (date.today() - timedelta(days=days)).isoformat()


@router.get("/history")
def get_history(
    period: str = Query("3M"),
    connector_id: str | None = None,
    account_id: str | None = None,
    user: AuthUser = Depends(get_current_user),
):
    """Courbe Valeur + courbe Perf TWR sur la période, scoped user (+ optionnel connector/account)."""
    since = _period_start(period)
    stmt = select(portfolio_history_daily).order_by(
        portfolio_history_daily.c.connector_id,
        portfolio_history_daily.c.account_id,
        portfolio_history_daily.c.date,
    )
    if since:
        stmt = stmt.where(portfolio_history_daily.c.date >= since)
    if connector_id:
        stmt = stmt.where(portfolio_history_daily.c.connector_id == connector_id)
    if account_id:
        stmt = stmt.where(portfolio_history_daily.c.account_id == account_id)

    with deps.get_ledger(user.id).connect() as conn:
        rows = conn.execute(stmt).fetchall()

    # Group par (connector_id, account_id) → list de timelines
    grouped: dict[tuple[str, str], list[dict]] = {}
    for r in rows:
        grouped.setdefault((r.connector_id, r.account_id), []).append({
            "date": r.date,
            "total_value": r.total_value,
            "cash": r.cash,
            "positions_value": r.positions_value,
            "cash_flow_external": r.cash_flow_external,
        })
    timelines = list(grouped.values())
    merged = aggregate_timelines(timelines) if timelines else []

    perf_curve = compute_twr(merged)
    total_pct = perf_curve[-1]["cum_pct"] if perf_curve else 0.0
    value_now = merged[-1]["total_value"] if merged else 0.0
    value_start = merged[0]["total_value"] if merged else 0.0
    currency = rows[0].currency if rows else "EUR"

    # Zip the 2 series par date
    perf_by_date = {p["date"]: p["cum_pct"] for p in perf_curve}
    series = [
        {"date": pt["date"], "value": pt["total_value"], "cum_pct": perf_by_date.get(pt["date"], 0.0)}
        for pt in merged
    ]
    return {
        "period": period,
        "series": series,
        "total_pct": total_pct,
        "value_now": value_now,
        "value_start": value_start,
        "currency": currency,
    }
```

- [ ] **Step 4 : Tests passent**

```
pytest tests/test_api_performance.py -v
```

Expected : 3 tests PASS.

- [ ] **Step 5 : Commit**

```
git add src/api/performance.py tests/test_api_performance.py
git commit -m "feat(api): GET /api/performance/history (Valeur + Perf TWR agrégés)

Scoped user, filtres optionnels connector_id + account_id. Série {date, value,
cum_pct} calculée via aggregate_timelines + compute_twr. Table portfolio_history_daily."
```

---

## Task 8 : Frontend — client API performance

**Files:**
- Create: `frontend/src/api/performance.ts`

- [ ] **Step 1 : Créer le fichier**

```typescript
import { api } from './client';

export interface PerfPoint {
  date: string;
  value: number;
  cum_pct: number;
}

export interface PerfHistory {
  period: string;
  series: PerfPoint[];
  total_pct: number;
  value_now: number;
  value_start: number;
  currency: string;
}

export function getPerformanceHistory(params: {
  period?: string;
  connector_id?: string;
  account_id?: string;
} = {}): Promise<PerfHistory> {
  const query: Record<string, string> = {};
  if (params.period) query.period = params.period;
  if (params.connector_id) query.connector_id = params.connector_id;
  if (params.account_id) query.account_id = params.account_id;
  return api.get('/performance/history', query) as Promise<PerfHistory>;
}
```

- [ ] **Step 2 : Build TS**

```
cd /Users/charles/Desktop/mm-ledger/frontend && bun run build
```

Expected : 0 erreur TS.

- [ ] **Step 3 : Commit**

```
git add frontend/src/api/performance.ts
git commit -m "feat(front): client api performance history"
```

---

## Task 9 : Frontend — composant `PortfolioPerfChart` avec toggle

**Files:**
- Create: `frontend/src/components/PortfolioPerfChart.tsx`

- [ ] **Step 1 : Créer le composant**

```tsx
import { useState } from 'react';
import {
  AreaChart, Area, LineChart, Line, ReferenceLine,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts';
import type { PerfPoint } from '@/api/performance';
import { formatCurrency, formatPercent } from '@/lib/format';

interface Props {
  series: PerfPoint[];
  totalPct: number;
  valueNow: number;
  currency: string;
  periods: string[];
  activePeriod: string;
  onPeriodChange: (p: string) => void;
  periodLabel: string; // ex. "1 an" pour l'affichage "Rendement sur 1 an"
}

type Mode = 'value' | 'perf';

export function PortfolioPerfChart({
  series, totalPct, valueNow, currency, periods, activePeriod, onPeriodChange, periodLabel,
}: Props) {
  const [mode, setMode] = useState<Mode>('value');

  const positive = totalPct >= 0;
  const accentColor = mode === 'value'
    ? 'var(--mm-accent-gold)'
    : (positive ? 'var(--mm-gain)' : 'var(--mm-loss)');

  return (
    <div className="bg-mm-surface border border-mm-border rounded-[12px] p-5">
      {/* Header : toggle + périodes */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-1">
          <button
            onClick={() => setMode('value')}
            className={['rounded-[4px] px-3 py-1.5 text-xs transition-colors',
              mode === 'value'
                ? 'bg-mm-surface-elevated border border-mm-gold text-mm-gold font-semibold'
                : 'border border-transparent text-mm-text-muted'].join(' ')}
          >Valeur</button>
          <button
            onClick={() => setMode('perf')}
            className={['rounded-[4px] px-3 py-1.5 text-xs transition-colors',
              mode === 'perf'
                ? 'bg-mm-surface-elevated border border-mm-gold text-mm-gold font-semibold'
                : 'border border-transparent text-mm-text-muted'].join(' ')}
          >Perf</button>
        </div>
        <div className="flex items-center gap-1">
          {periods.map((p) => {
            const active = p === activePeriod;
            return (
              <button key={p} onClick={() => onPeriodChange(p)}
                className={['rounded-[4px] px-3 py-1.5 text-xs transition-colors',
                  active
                    ? 'bg-mm-surface-elevated border border-mm-gold text-mm-gold font-semibold'
                    : 'border border-transparent text-mm-text-muted'].join(' ')}>
                {p}
              </button>
            );
          })}
        </div>
      </div>

      {/* Big number */}
      <div className="mb-3">
        <div className="text-[28px] font-semibold" style={{ color: accentColor }}>
          {mode === 'value'
            ? formatCurrency(valueNow, currency)
            : `${positive ? '+' : ''}${formatPercent(totalPct / 100)}`}
        </div>
        <div className="text-[11px] text-mm-text-muted mt-0.5">
          {mode === 'value' ? 'Valeur actuelle' : `Rendement sur ${periodLabel}`}
        </div>
      </div>

      {/* Chart */}
      <ResponsiveContainer width="100%" height={240}>
        {mode === 'value' ? (
          <AreaChart data={series} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
            <defs>
              <linearGradient id="perfGoldGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="var(--mm-accent-gold)" stopOpacity={0.25} />
                <stop offset="100%" stopColor="var(--mm-accent-gold)" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid stroke="#1a3d4d40" horizontal vertical={false} />
            <XAxis dataKey="date" axisLine={false} tickLine={false}
              tick={{ fill: 'rgba(226,207,234,0.5)', fontSize: 10 }} />
            <YAxis axisLine={false} tickLine={false}
              tick={{ fill: 'rgba(226,207,234,0.5)', fontSize: 10 }} />
            <Tooltip contentStyle={{ backgroundColor: '#143a42', border: '1px solid #1a3d4d', borderRadius: 8, color: '#f0ece4', fontSize: 12 }} />
            <Area type="monotone" dataKey="value" stroke="var(--mm-accent-gold)" strokeWidth={2} fill="url(#perfGoldGrad)" />
          </AreaChart>
        ) : (
          <LineChart data={series} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
            <CartesianGrid stroke="#1a3d4d40" horizontal vertical={false} />
            <XAxis dataKey="date" axisLine={false} tickLine={false}
              tick={{ fill: 'rgba(226,207,234,0.5)', fontSize: 10 }} />
            <YAxis axisLine={false} tickLine={false}
              tick={{ fill: 'rgba(226,207,234,0.5)', fontSize: 10 }}
              tickFormatter={(v) => `${v >= 0 ? '+' : ''}${v.toFixed(1)}%`} />
            <Tooltip contentStyle={{ backgroundColor: '#143a42', border: '1px solid #1a3d4d', borderRadius: 8, color: '#f0ece4', fontSize: 12 }}
              formatter={(v: number) => [`${v >= 0 ? '+' : ''}${v.toFixed(2)}%`, 'Perf']} />
            <ReferenceLine y={0} stroke="rgba(226,207,234,0.35)" strokeDasharray="3 3" />
            <Line type="monotone" dataKey="cum_pct"
              stroke={accentColor}
              strokeWidth={2} dot={false} />
          </LineChart>
        )}
      </ResponsiveContainer>
    </div>
  );
}
```

- [ ] **Step 2 : Build TS**

```
cd /Users/charles/Desktop/mm-ledger/frontend && bun run build
```

Expected : 0 erreur TS.

- [ ] **Step 3 : Commit**

```
git add frontend/src/components/PortfolioPerfChart.tsx
git commit -m "feat(front): composant PortfolioPerfChart avec toggle Valeur/Perf

Vue Valeur : area chart gold. Vue Perf : line chart avec ligne 0 dashed,
couleur dynamique --mm-gain / --mm-loss selon signe du total_pct."
```

---

## Task 10 : Dashboard — utiliser `PortfolioPerfChart`

**Files:**
- Modify: `frontend/src/pages/Dashboard.tsx`

- [ ] **Step 1 : Modifier Dashboard**

Dans `frontend/src/pages/Dashboard.tsx` :

1. Remplacer l'import :
```tsx
import { PortfolioPerfChart } from '@/components/PortfolioPerfChart';
import { getPerformanceHistory, type PerfHistory } from '@/api/performance';
```
(et retirer `import { PerformanceChart } from '@/components/PerformanceChart';`)

2. Ajouter state :
```tsx
const [perfHistory, setPerfHistory] = useState<PerfHistory | null>(null);
```

3. Dans `fetchAllData`, ajouter `getPerformanceHistory({ period: activePeriod })` dans le `Promise.all`, et setter `setPerfHistory(result)`.

4. Re-fetch au changement de période :
```tsx
useEffect(() => {
  getPerformanceHistory({ period: activePeriod }).then(setPerfHistory).catch(() => {});
}, [activePeriod]);
```

5. Remplacer le rendu `<PerformanceChart ... />` par :
```tsx
<PortfolioPerfChart
  series={perfHistory?.series ?? []}
  totalPct={perfHistory?.total_pct ?? 0}
  valueNow={perfHistory?.value_now ?? 0}
  currency={perfHistory?.currency ?? 'EUR'}
  periods={[...PERIODS]}
  activePeriod={activePeriod}
  onPeriodChange={setActivePeriod}
  periodLabel={periodLabelFr(activePeriod)}
/>
```

6. Ajouter helper local :
```tsx
function periodLabelFr(p: string): string {
  return { '1W': '7 jours', '1M': '1 mois', '3M': '3 mois', '1Y': '1 an', 'All': 'tout' }[p] ?? p;
}
```

7. Supprimer la logique obsolète `chartData` (useMemo basé sur netWorthHistory) — le chart ne l'utilise plus. Garder `netWorthHistory` et `getNetWorthHistory` si utilisés ailleurs dans le fichier ; sinon les retirer aussi.

- [ ] **Step 2 : Build TS**

```
cd /Users/charles/Desktop/mm-ledger/frontend && bun run build
```

Expected : 0 erreur.

- [ ] **Step 3 : Commit**

```
git add frontend/src/pages/Dashboard.tsx
git commit -m "feat(dashboard): courbe perf agrégée via /api/performance/history"
```

---

## Task 11 : AccountDetail — utiliser `PortfolioPerfChart` scopé

**Files:**
- Modify: `frontend/src/pages/AccountDetail.tsx`

- [ ] **Step 1 : Repérer le chart actuel**

Lire `frontend/src/pages/AccountDetail.tsx` pour localiser le chart (probablement `PerformanceChart` importé). Repérer la variable `account_id` (ID du compte affiché) et `connector_id` (si présent).

- [ ] **Step 2 : Remplacer par PortfolioPerfChart**

1. Imports :
```tsx
import { PortfolioPerfChart } from '@/components/PortfolioPerfChart';
import { getPerformanceHistory, type PerfHistory } from '@/api/performance';
```

2. State + fetch :
```tsx
const [perfHistory, setPerfHistory] = useState<PerfHistory | null>(null);
const [activePeriod, setActivePeriod] = useState<string>('3M');

useEffect(() => {
  if (!accountId) return;
  getPerformanceHistory({ period: activePeriod, account_id: accountId })
    .then(setPerfHistory).catch(() => {});
}, [accountId, activePeriod]);
```

3. Remplacer le rendu du chart par le même JSX que Dashboard, avec `periods={['1W', '1M', '3M', '1Y', 'All']}`.

- [ ] **Step 3 : Build TS**

```
cd /Users/charles/Desktop/mm-ledger/frontend && bun run build
```

Expected : 0 erreur.

- [ ] **Step 4 : Commit**

```
git add frontend/src/pages/AccountDetail.tsx
git commit -m "feat(front): chart perf scopé par compte sur AccountDetail"
```

---

## Task 12 : IBKR — implémenter `fetch_history_data`

**Files:**
- Modify: `src/connectors/ibkr.py`
- Test: `tests/test_connector_ibkr.py`

- [ ] **Step 1 : Test**

Ajouter à `tests/test_connector_ibkr.py` :

```python
def test_fetch_history_data_returns_normalized_shape():
    w = _make_worker("u1:ib")
    with _patch_connect_dependencies() as ctx:
        w.connect(_creds())
    # Mock executions + positions
    from unittest.mock import MagicMock
    exec_fill = MagicMock()
    exec_fill.execution.time = MagicMock()
    exec_fill.execution.time.date.return_value = MagicMock()
    exec_fill.execution.time.date().isoformat = lambda: "2026-01-15"
    exec_fill.execution.shares = 1.0
    exec_fill.execution.price = 200.0
    exec_fill.execution.side = "BOT"
    exec_fill.contract.symbol = "AMZN"
    exec_fill.contract.conId = 123
    exec_fill.contract.currency = "USD"
    ctx["ib"].fills.return_value = [exec_fill]

    bar = MagicMock()
    bar.date.isoformat = lambda: "2026-01-15"
    bar.close = 200.0
    ctx["ib"].reqHistoricalData.return_value = [bar]

    from unittest.mock import MagicMock as MM
    pos = MM()
    pos.contract.conId = 123
    pos.contract.symbol = "AMZN"
    pos.contract.currency = "USD"
    pos.position = 1.0
    pos.avgCost = 200.0
    pos.account = "U1"
    ctx["ib"].positions.return_value = [pos]

    data = w.fetch_history_data()
    assert data["account_id"]  # ID du compte détecté
    assert "transactions" in data
    assert "historical_prices" in data
    assert "start_date" in data and "end_date" in data
    assert len(data["transactions"]) >= 1
    tx = data["transactions"][0]
    assert tx["kind"] in ("buy", "sell")
    assert tx["symbol"] == "AMZN"
```

- [ ] **Step 2 : Vérifier échec** (`fetch_history_data` retourne `{"transactions": [], "historical_prices": {}, "account_id": ""}` par défaut).

- [ ] **Step 3 : Implémenter `fetch_history_data` dans `IBKRWorker`**

Ajouter à `src/connectors/ibkr.py` à la fin de la classe :

```python
    def fetch_history_data(self) -> dict:
        """Historique IBKR : executions (buy/sell), prix historiques, positions actuelles.
        Cash flows externes assumés à 0 en v1 (pas de Flex Query)."""
        if not self._ib:
            return {"transactions": [], "historical_prices": {}, "account_id": ""}

        from datetime import date, timedelta
        end = date.today().isoformat()
        start = (date.today() - timedelta(days=730)).isoformat()

        fx_to_base, base_currency = self._fx_to_base()
        positions = self._ib.positions()
        account_id = positions[0].account if positions else ""

        # 1. Executions (trades)
        fills = []
        try:
            fills = self._ib.fills()
        except Exception as e:
            log.warning("IBKR: fills() failed: %s", type(e).__name__)

        txs: list[dict] = []
        contracts_seen: dict[int, object] = {}
        for f in fills:
            ex = f.execution
            ct = f.contract
            rate = fx_to_base.get(ct.currency, 1.0)
            qty = float(ex.shares)
            if ex.side == "SLD":
                qty = -qty
            price_base = float(ex.price) * rate
            amount_base = -qty * price_base  # buy = cash sortant (négatif)
            tx_date = ex.time.date().isoformat() if hasattr(ex.time, "date") else str(ex.time)[:10]
            txs.append({
                "date": tx_date,
                "kind": "buy" if qty > 0 else "sell",
                "symbol": ct.symbol,
                "qty": qty,
                "price": price_base,
                "amount": amount_base,
            })
            contracts_seen[ct.conId] = ct

        # Aussi, pour les positions actuelles qui n'apparaîtraient pas dans fills
        for p in positions:
            if p.contract.conId not in contracts_seen:
                contracts_seen[p.contract.conId] = p.contract

        # 2. Historical prices
        historical_prices: dict[str, list[dict]] = {}
        for conId, contract in contracts_seen.items():
            try:
                bars = self._ib.reqHistoricalData(
                    contract, endDateTime="", durationStr="2 Y",
                    barSizeSetting="1 day", whatToShow="TRADES",
                    useRTH=True, formatDate=1,
                )
            except Exception as e:
                log.warning("IBKR: hist data failed for %s: %s", contract.symbol, type(e).__name__)
                continue
            rate = fx_to_base.get(contract.currency, 1.0)
            historical_prices[contract.symbol] = [
                {
                    "date": bar.date.isoformat() if hasattr(bar.date, "isoformat") else str(bar.date),
                    "close": float(bar.close) * rate,
                }
                for bar in bars
            ]

        log.info(
            "IBKR: history_data account=%s txs=%d symbols=%d",
            account_id, len(txs), len(historical_prices),
        )
        return {
            "account_id": account_id,
            "transactions": txs,
            "historical_prices": historical_prices,
            "start_date": start,
            "end_date": end,
            "currency": base_currency,
        }
```

Et dans `_fetch_and_emit_initial`, ajouter `fetch_history_data` :

```python
    def _fetch_and_emit_initial(self) -> None:
        for fetch_name in ("fetch_accounts", "fetch_balances", "fetch_positions", "fetch_history_data"):
            ...
```

- [ ] **Step 4 : Tests passent**

```
pytest tests/test_connector_ibkr.py -v
```

Expected : tous PASS (22 → 23).

- [ ] **Step 5 : Commit**

```
git add src/connectors/ibkr.py tests/test_connector_ibkr.py
git commit -m "feat(ibkr): fetch_history_data via fills() + reqHistoricalData

Normalise executions en {kind, symbol, qty, price, amount} avec conversion
en base currency via _fx_to_base. Cash flows externes = 0 en v1 (assumé).
Fetch auto au connect via _fetch_and_emit_initial."
```

---

## Task 13 : TR — implémenter `fetch_history_data`

**Files:**
- Modify: `src/connectors/trade_republic.py`

- [ ] **Step 1 : Implémenter**

Ajouter à la classe `TradeRepublicWorker` dans `src/connectors/trade_republic.py` :

```python
    def fetch_history_data(self) -> dict:
        """Historique TR : timelineTransactions (déjà fetched) + priceHistory par ISIN."""
        import websockets.sync.client as ws_client
        import json
        from datetime import date, timedelta

        end = date.today().isoformat()
        start = (date.today() - timedelta(days=730)).isoformat()

        # 1. Fetch transactions (réutilise fetch_transactions existant qui retourne liste normalisée)
        raw_txs = self.fetch_transactions()

        # Classification via raw_type
        BUY_TYPES = {"ORDER_EXECUTED", "TRADE_EXECUTED", "SAVINGS_PLAN_EXECUTED"}
        SELL_TYPES = {"TRADE_SELL_EXECUTED"}
        DEPOSIT_TYPES = {"INCOMING_TRANSFER", "PAYMENT_INBOUND", "PAYMENT_INBOUND_SEPA_DIRECT_DEBIT"}
        WITHDRAWAL_TYPES = {"PAYMENT_OUTBOUND", "OUTGOING_TRANSFER"}
        DIVIDEND_TYPES = {"CREDIT", "ssp_corporate_action_invoice_cash"}
        INTEREST_TYPES = {"INTEREST_PAYOUT_CREATED", "INTEREST_PAYOUT"}

        txs: list[dict] = []
        isins_seen: set[str] = set()
        for t in raw_txs:
            rt = t.get("raw_type", "")
            amount = float(t.get("amount", 0))
            d = str(t.get("date", ""))[:10]
            if not d:
                continue
            if rt in BUY_TYPES:
                # Pour les buy/sell TR, le détail (ISIN, qty, price) n'est pas dans timelineTransactions.
                # En v1 simplifié : on traite ça comme un cash flow interne neutre + on récupère les
                # ISIN via la WS `timelineDetailV2` pour chaque transaction plus tard. Pour l'instant
                # on stocke juste le cash impact et on skippe la reconstruction de position.
                txs.append({"date": d, "kind": "buy", "symbol": None, "qty": 0, "price": 0, "amount": amount})
            elif rt in SELL_TYPES:
                txs.append({"date": d, "kind": "sell", "symbol": None, "qty": 0, "price": 0, "amount": amount})
            elif rt in DEPOSIT_TYPES:
                txs.append({"date": d, "kind": "deposit", "amount": amount})
            elif rt in WITHDRAWAL_TYPES:
                txs.append({"date": d, "kind": "withdrawal", "amount": amount})
            elif rt in DIVIDEND_TYPES:
                txs.append({"date": d, "kind": "dividend", "amount": amount})
            elif rt in INTEREST_TYPES:
                txs.append({"date": d, "kind": "interest", "amount": amount})

        # 2. Prix historiques pour chaque ISIN détenu aujourd'hui (récupérés via positions actuelles).
        # Les ISINs sont disponibles dans les positions live (déjà fetchées par fetch_positions).
        historical_prices: dict[str, list[dict]] = {}
        try:
            positions = self.fetch_positions()
            for acc_data in positions:
                for cat in acc_data.get("categories", []):
                    for p in cat.get("positions", []):
                        isin = p.get("isin") or p.get("shortName")
                        if isin and isin not in isins_seen:
                            isins_seen.add(isin)
        except Exception as e:
            log.warning(f"TR: fetch positions for hist failed: {e}")

        # WS priceHistory pour chaque ISIN
        if isins_seen:
            try:
                with ws_client.connect("wss://api.traderepublic.com") as ws:
                    self._ws_connect(ws)
                    for isin in isins_seen:
                        try:
                            bars_resp = self._ws_sub(ws, {
                                "type": "aggregateHistoryLight",
                                "token": self._session_token,
                                "id": f"{isin}.LSX",
                                "range": "2y",
                                "resolution": "1d",
                            })
                            if isinstance(bars_resp, dict) and "aggregates" in bars_resp:
                                historical_prices[isin] = [
                                    {"date": a.get("time", "")[:10], "close": float(a.get("close", 0))}
                                    for a in bars_resp["aggregates"]
                                    if a.get("time")
                                ]
                        except Exception as e:
                            log.warning(f"TR: priceHistory {isin} failed: {e}")
            except Exception as e:
                log.warning(f"TR: WS connect for history failed: {e}")

        log.info(f"TR: history_data txs={len(txs)} isins={len(historical_prices)}")
        return {
            "account_id": "tr",   # TR n'a pas d'account ID standard — on scope au connector_id
            "transactions": txs,
            "historical_prices": historical_prices,
            "start_date": start,
            "end_date": end,
            "currency": "EUR",
        }
```

- [ ] **Step 2 : Pas de test unitaire fait ici** (TR dépend de Selenium + WS, cher à mocker). On s'appuie sur le test d'intégration de Task 6 avec FakeWorker pour la persistance, et sur la validation manuelle E2E.

- [ ] **Step 3 : Suite complète toujours verte**

```
cd /Users/charles/Desktop/mm-ledger && source .venv/bin/activate && pytest tests/ -q
```

Expected : tous PASS.

- [ ] **Step 4 : Commit**

```
git add src/connectors/trade_republic.py
git commit -m "feat(tr): fetch_history_data via timelineTransactions + aggregateHistoryLight

Classification des raw_type TR en {buy, sell, deposit, withdrawal, dividend,
interest}. Prix historiques via WS aggregateHistoryLight par ISIN détenu.
Limites v1 : les ISIN/qty/prix des trades TR ne sont pas extraits de timeline
(nécessiterait timelineDetailV2) — pour l'instant les buys/sells affectent
le cash mais pas la reconstruction de positions (→ suit Task 12 + v2)."
```

---

## Task 14 : Scheduler — append point quotidien

**Files:**
- Modify: `src/scheduler.py`

- [ ] **Step 1 : Étendre `daily_snapshot`**

Dans `src/scheduler.py`, ajouter à la fin de `daily_snapshot` (après la section net_worth) :

```python
    # Portfolio history daily : append point du jour pour chaque worker CTO connecté
    for user_id, worker_keys in user_workers.items():
        if not user_id:
            continue
        for composite_key in worker_keys:
            try:
                deps.manager.send_command(composite_key, {"type": "fetch_history_data"})
                await asyncio.sleep(5)  # laisse le temps au fetch + conversion
                deps.manager.collect_events()  # déclenche _persist_history_for_worker
            except Exception as e:
                _last_results["daily_snapshot"] = f"history append error ({composite_key}): {e}"
```

- [ ] **Step 2 : Smoke test — import OK**

```
cd /Users/charles/Desktop/mm-ledger && source .venv/bin/activate && python -c "from src.scheduler import daily_snapshot; print('ok')"
```

Expected : `ok`.

- [ ] **Step 3 : Commit**

```
git add src/scheduler.py
git commit -m "feat(scheduler): append point quotidien dans portfolio_history_daily

À 23h, chaque worker CTO connecté refetch fetch_history_data → le manager
upsert le nouveau point du jour. Les points passés restent intacts
(upsert par PRIMARY KEY (connector_id, account_id, date))."
```

---

## Task 15 : Validation end-to-end manuelle

**Files:** (aucun — validation runtime)

- [ ] **Step 1 : Backend + front en dev**

Terminal 1 :
```
cd /Users/charles/Desktop/mm-ledger && ./start.sh
```

Terminal 2 :
```
cd /Users/charles/Desktop/mm-ledger/frontend && bun run dev
```

- [ ] **Step 2 : Flow IBKR**

1. Login + déverrouille le vault sur http://localhost:3000
2. Disconnect puis Reconnect IBKR (pour déclencher `fetch_history_data` via `_fetch_and_emit_initial`)
3. Attendre ~10-20s (fills + reqHistoricalData par position)
4. Dans les logs uvicorn, chercher :
   ```
   [INFO] src.connectors.ibkr: IBKR: history_data account=U... txs=N symbols=M
   ```
5. Ouvrir la base de données : `python -c "from src.db.engine import create_engine_from_path; ..."` OU via Swagger `/docs` GET `/api/performance/history?period=All` — doit retourner une liste de points.

- [ ] **Step 3 : Flow UI**

1. Dashboard → chart principal montre maintenant toggle Valeur/Perf.
2. Vue "Perf" → courbe avec ligne 0, couleur selon signe, pourcentage en gros.
3. Cliquer sur période 1W / 1M / 3M / 1Y / All → chart se met à jour.
4. Naviguer vers AccountDetail (clic sur un compte IBKR) → même chart, mais scopé à l'account_id.

- [ ] **Step 4 : Flow TR** (si TR connecté)

1. Disconnect/Reconnect TR (2FA via SMS nécessaire)
2. Vérifier dans les logs : `TR: history_data txs=N isins=M`
3. Vérifier que la courbe agrégée (sans filtre) est différente du scope IBKR seul.

- [ ] **Step 5 : Résultats**

Si tout marche : passer à Task 16 (docs).
Si des problèmes :
- `txs=0` côté IBKR → `ib.fills()` n'a pas retourné (peut-être trop récent, retry après quelques minutes).
- `isins=0` côté TR → le WS `aggregateHistoryLight` n'est pas le bon nom de message ; pull l'URL `/` via l'inspecteur de WS TR pour trouver le message exact, ajuster `trade_republic.py`.
- Courbe vide sur le dashboard avec data en DB → checker la série d'erreur TS, la signature de la réponse API.

Pas de commit ici — validation uniquement.

---

## Task 16 : Docs — CLAUDE.md + README

**Files:**
- Modify: `CLAUDE.md`
- Modify: `README.md`

- [ ] **Step 1 : CLAUDE.md**

Ajouter dans la section Gotchas de `CLAUDE.md` :

```markdown
- **Courbe performance** : `PortfolioPerfChart` sur dashboard et AccountDetail. Données dans `portfolio_history_daily` (reconstruite via `src/performance.py` à partir de `fetch_history_data` des workers CTO). Endpoint : `GET /api/performance/history?period&connector_id?&account_id?`. Toggle Valeur/Perf côté UI ; couleurs semantic `--mm-gain` / `--mm-loss`.
```

- [ ] **Step 2 : README.md**

Ajouter une sous-section dans l'architecture ou la fonctionnalité :

```markdown
### Performance TWR

Le chart "Portfolio Performance" du dashboard et des pages compte calcule une perf TWR (Modified Dietz) à partir de l'historique des trades + prix de chaque broker. Reconstruction complète au premier connect (2 ans), mis à jour chaque soir à 23h.
```

- [ ] **Step 3 : Commit**

```
git add CLAUDE.md README.md
git commit -m "docs: courbe de performance TWR — CLAUDE.md + README"
```

---

## Self-Review

- **Spec coverage** : reconstruct_timeline (T1), compute_twr (T2), aggregate_timelines (T3), DB table (T4), hook manager (T6), API endpoint (T7), connector base (T5), IBKR impl (T12), TR impl (T13), scheduler (T14), frontend component (T9), dashboard (T10), account detail (T11), docs (T16). ✅ Toutes les sections du spec ont une task.

- **Placeholders** : une note "en v1 simplifié" sur T13 (TR trades sans ISIN) — c'est assumé dans le spec comme limite connue, OK.

- **Type consistency** : `TxEvent` dataclass défini en T1, utilisé en T6. `PerfPoint` défini en T8, utilisé en T9/T10/T11. `portfolio_history_daily` défini en T4 avec les mêmes colonnes utilisées partout.

- **Risques d'exécution** :
  - T6 : les tests manager avec DB réelle nécessitent `conftest.py` avec les helpers `_seed_user`, `_login` — si absents, à écrire en premier.
  - T12 mock ib_async — la signature de `fills()` + `reqHistoricalData()` est complexe à mocker, prévoir quelques itérations.
  - T13 — TR `aggregateHistoryLight` est un message reversé, nom peut être différent. Si ça fail silencieusement, courbe TR vide mais IBKR continue de fonctionner.

- **Ordre** : chaque task produit un commit + état vert. T5/T6 enchaînables. T8-T11 frontend linéaire. T12-T13 en parallèle possible. T14-T16 en fin.
