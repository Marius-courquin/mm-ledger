# Canonical Normalization + Loan Auto-Detection — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduire une couche de normalisation canonical (Pydantic) entre les `ConnectorWorker` et les API/UI, refondre les API Comptes/Soldes/Positions sur ce schéma, et permettre l'auto-détection des comptes de type prêt avec un lien stable vers le module Prêts.

**Architecture:** Schéma canonical (`CanonicalAccount/Balance/Position`) + un `Normalizer` par connecteur dans `src/normalizers/`, invoqué par `ConnectorManager.collect_events()` à la réception. Le `live_data` du manager ne contient plus que du canonical. Une table `loan_account_link` (3 états : candidat / lié / ignoré) garantit l'idempotence du lien prêt ↔ compte bancaire ; `compute_loan_state` lit le solde bancaire si dispo (< 7 j), sinon fallback calendaire.

**Tech Stack:** Python 3.12, Pydantic, SQLAlchemy 2 + Alembic, FastAPI, pytest, React 19 + TypeScript.

**Spec source:** `docs/superpowers/specs/2026-04-30-canonical-normalization-design.md`

---

## File Structure

**Nouveaux fichiers**
- `src/normalizers/__init__.py` — registry `get_normalizer(connector_type)`
- `src/normalizers/types.py` — Pydantic `CanonicalAccount`, `CanonicalBalance`, `CanonicalPosition`, enums
- `src/normalizers/base.py` — `Normalizer` ABC
- `src/normalizers/trade_republic.py` — `TRNormalizer`
- `src/normalizers/woob_bank.py` — `WoobNormalizer`
- `src/normalizers/enable_banking.py` — `BankingNormalizer`
- `src/normalizers/ibkr.py` — `IBKRNormalizer`
- `tests/normalizers/__init__.py`
- `tests/normalizers/test_trade_republic.py`
- `tests/normalizers/test_woob_bank.py`
- `tests/normalizers/test_enable_banking.py`
- `tests/normalizers/test_ibkr.py`
- `src/db/migrations/versions/<id>_add_loan_account_link.py` — Alembic
- `frontend/src/components/LoanCandidates.tsx` — UI candidats

**Fichiers modifiés**
- `src/manager.py` — stocker `connector_type` dans `WorkerHandle` ; appliquer normalizer dans `collect_events`
- `src/api/accounts.py` — consommer canonical
- `src/api/portfolio.py` — consommer canonical positions
- `src/api/loans.py` — endpoints candidats + link + from-account ; injecter `linked_balance` dans `compute_loan_state`
- `src/services/loan_calc.py` — étendre avec `linked_balance` + `amount_source`
- `src/db/models.py` — table `loan_account_link`
- `src/schemas/loans.py` — `LoanResponse.linked_account_id`, `amount_source`, `linked_balance` ; nouveaux schémas `LoanCandidate`, `LinkRequest`, `FromAccountRequest`
- `frontend/src/lib/types.ts` — types `Account`, `Position` enrichis
- `frontend/src/pages/Dashboard.tsx` — utiliser `account.label` direct, icônes par `kind`
- `frontend/src/pages/Prets.tsx` — section candidats
- `frontend/src/api/loans.ts` — clients pour les nouveaux endpoints

---

## Phase 0 — Infrastructure canonical (no behavior change yet)

### Task 1: Schéma canonical Pydantic

**Files:**
- Create: `src/normalizers/__init__.py`
- Create: `src/normalizers/types.py`
- Test: `tests/normalizers/__init__.py` (vide)

- [ ] **Step 1: Créer le package**

```bash
mkdir -p src/normalizers tests/normalizers
touch src/normalizers/__init__.py tests/normalizers/__init__.py
```

- [ ] **Step 2: Écrire `src/normalizers/types.py`**

```python
"""Canonical types pour Comptes / Soldes / Positions.

Tout connecteur produit ces types via son Normalizer dédié. Aucun consommateur
(API, scheduler, snapshot) ne doit interpréter du raw connecteur — uniquement
ces shapes.
"""
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

AccountKind = Literal["cash", "securities", "liability"]

TaxWrapper = Literal[
    "none", "cto", "pea", "pea_pme", "per", "av",
    "livret_a", "livret_jeune", "ldds", "lep", "cel", "pel",
]

AssetClass = Literal["equity", "etf", "bond", "crypto", "private", "other"]


class CanonicalAccount(BaseModel):
    """Compte normalisé, identifiant stable cross-sync."""

    id: str = Field(..., description="ID stable préfixé par connecteur (tr:, ibkr:, woob:..., eb:)")
    connector_id: str
    connector_type: str
    label: str
    kind: AccountKind
    tax_wrapper: TaxWrapper = "none"
    currency: str = "EUR"


class CanonicalBalance(BaseModel):
    """Solde d'un compte. Pour kind=liability, total_value est négatif (dette)."""

    account_id: str
    cash: Decimal | None = None
    positions_value: Decimal | None = None
    total_value: Decimal
    currency: str = "EUR"
    as_of: datetime


class CanonicalPosition(BaseModel):
    account_id: str
    symbol: str
    isin: str | None = None
    name: str
    quantity: Decimal
    average_price: Decimal | None = None
    current_price: Decimal | None = None
    value: Decimal
    asset_class: AssetClass
    currency: str = "EUR"
```

- [ ] **Step 3: Smoke test des types**

Créer `tests/normalizers/test_types.py` :

```python
from datetime import datetime
from decimal import Decimal

from src.normalizers.types import CanonicalAccount, CanonicalBalance, CanonicalPosition


def test_canonical_account_minimal():
    acc = CanonicalAccount(
        id="tr:DA1234",
        connector_id="user1:tr-1",
        connector_type="trade_republic",
        label="PEA",
        kind="securities",
        tax_wrapper="pea",
    )
    assert acc.currency == "EUR"
    assert acc.tax_wrapper == "pea"


def test_canonical_balance_negative_for_liability():
    bal = CanonicalBalance(
        account_id="woob:bp:abc",
        total_value=Decimal("-3800.00"),
        as_of=datetime(2026, 4, 30, 10, 0, 0),
    )
    assert bal.total_value < 0


def test_canonical_position_value_decimal():
    pos = CanonicalPosition(
        account_id="tr:DA1234",
        symbol="AAPL",
        isin="US0378331005",
        name="Apple Inc.",
        quantity=Decimal("10"),
        current_price=Decimal("180.50"),
        value=Decimal("1805.00"),
        asset_class="equity",
    )
    assert pos.asset_class == "equity"
    assert pos.value == Decimal("1805.00")
```

- [ ] **Step 4: Lancer les tests**

```bash
source .venv/bin/activate && pytest tests/normalizers/test_types.py -v
```
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/normalizers/ tests/normalizers/
git commit -m "feat(normalizers): canonical Pydantic types pour Account/Balance/Position"
```

---

### Task 2: Normalizer ABC + registry

**Files:**
- Create: `src/normalizers/base.py`
- Modify: `src/normalizers/__init__.py`

- [ ] **Step 1: Écrire `src/normalizers/base.py`**

```python
"""ABC commun à tous les normalizers."""
from abc import ABC, abstractmethod
from typing import Any

from src.normalizers.types import CanonicalAccount, CanonicalBalance, CanonicalPosition


class Normalizer(ABC):
    """Convertit le raw d'un connecteur en types canonical.

    Les méthodes `normalize_balances` et `normalize_positions` reçoivent les
    `accounts` déjà normalisés pour pouvoir matcher les soldes/positions à
    leur compte par ID canonical.
    """

    @abstractmethod
    def normalize_accounts(self, raw: Any, connector_id: str) -> list[CanonicalAccount]: ...

    @abstractmethod
    def normalize_balances(
        self, raw: Any, accounts: list[CanonicalAccount]
    ) -> list[CanonicalBalance]: ...

    @abstractmethod
    def normalize_positions(
        self, raw: Any, accounts: list[CanonicalAccount]
    ) -> list[CanonicalPosition]: ...
```

- [ ] **Step 2: Écrire le registry dans `src/normalizers/__init__.py`**

```python
"""Registry des normalizers par connector_type."""
from src.normalizers.base import Normalizer
from src.normalizers.types import (
    AccountKind,
    AssetClass,
    CanonicalAccount,
    CanonicalBalance,
    CanonicalPosition,
    TaxWrapper,
)

_REGISTRY: dict[str, Normalizer] = {}


def register(connector_type: str, normalizer: Normalizer) -> None:
    _REGISTRY[connector_type] = normalizer


def get_normalizer(connector_type: str) -> Normalizer | None:
    return _REGISTRY.get(connector_type)


__all__ = [
    "Normalizer", "AccountKind", "AssetClass", "TaxWrapper",
    "CanonicalAccount", "CanonicalBalance", "CanonicalPosition",
    "register", "get_normalizer",
]
```

- [ ] **Step 3: Test du registry**

Ajouter dans `tests/normalizers/test_types.py` :

```python
from src.normalizers import get_normalizer, register
from src.normalizers.base import Normalizer


def test_registry_get_returns_none_for_unknown():
    assert get_normalizer("does_not_exist") is None


def test_registry_register_and_get():
    class StubNormalizer(Normalizer):
        def normalize_accounts(self, raw, connector_id): return []
        def normalize_balances(self, raw, accounts): return []
        def normalize_positions(self, raw, accounts): return []

    stub = StubNormalizer()
    register("stub", stub)
    assert get_normalizer("stub") is stub
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/normalizers/test_types.py -v
```
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add src/normalizers/ tests/normalizers/test_types.py
git commit -m "feat(normalizers): ABC Normalizer + registry par connector_type"
```

---

### Task 3: Manager — stocker `connector_type` dans `WorkerHandle`

**Files:**
- Modify: `src/manager.py`
- Test: `tests/test_manager.py`

- [ ] **Step 1: Test failing — connector_type accessible après spawn**

Ajouter dans `tests/test_manager.py` (à la fin) :

```python
def test_worker_handle_stores_connector_type():
    from src.manager import ConnectorManager
    from src.connectors.base import ConnectorWorker

    class DummyWorker(ConnectorWorker):
        def connect(self, credentials): pass
        def disconnect(self): pass

    mgr = ConnectorManager()
    mgr.register_worker_class("dummy", DummyWorker)
    mgr.spawn("user1:test", "dummy", credentials={})
    try:
        assert mgr._workers["user1:test"].connector_type == "dummy"
    finally:
        mgr.stop_all()
```

- [ ] **Step 2: Run — devrait fail (pas d'attribut)**

```bash
pytest tests/test_manager.py::test_worker_handle_stores_connector_type -v
```
Expected: FAIL avec AttributeError.

- [ ] **Step 3: Modifier `src/manager.py`**

Dans `WorkerHandle` (ligne 21-28), ajouter le champ :

```python
@dataclass
class WorkerHandle:
    process: Process
    cmd_queue: Queue
    event_queue: Queue
    connector_type: str = ""
    state: str = "connecting"
    detail: str | None = None
    started_at: float = field(default_factory=time.time)
```

Dans `spawn` (ligne 57), passer le type :

```python
        handle = WorkerHandle(
            process=proc, cmd_queue=cmd_q, event_queue=event_q,
            connector_type=connector_type,
        )
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_manager.py -v
```
Expected: tous green, dont le nouveau.

- [ ] **Step 5: Commit**

```bash
git add src/manager.py tests/test_manager.py
git commit -m "refactor(manager): stocker connector_type dans WorkerHandle"
```

---

## Phase 1 — TR Normalizer + Manager wiring + API refonte

### Task 4: Trade Republic normalizer

**Files:**
- Create: `src/normalizers/trade_republic.py`
- Test: `tests/normalizers/test_trade_republic.py`

- [ ] **Step 1: Écrire les fixtures de test**

Créer `tests/normalizers/test_trade_republic.py` :

```python
"""Tests du TR normalizer.

Fixtures = payloads bruts tels qu'émis par le worker TR (cf.
src/connectors/trade_republic.py auto_fetch).
"""
from datetime import datetime
from decimal import Decimal

import pytest

from src.normalizers.trade_republic import TRNormalizer


@pytest.fixture
def raw_accounts():
    """Payload tel que retourné par accountPairs (extrait `accounts`)."""
    return [
        {"securitiesAccountNumber": "DA1111", "cashAccountNumber": "CA1111", "productType": "DEFAULT"},
        {"securitiesAccountNumber": "DA2222", "cashAccountNumber": "CA2222", "productType": "TAX_WRAPPER"},
        {"securitiesAccountNumber": "DA3333", "cashAccountNumber": "CA3333", "productType": "CRYPTO"},
    ]


@pytest.fixture
def raw_cash():
    return [
        {"accountNumber": "CA1111", "amount": "150.50", "currencyId": "EUR"},
        {"accountNumber": "CA2222", "amount": "0.00", "currencyId": "EUR"},
        {"accountNumber": "CA3333", "amount": "10.00", "currencyId": "EUR"},
    ]


@pytest.fixture
def raw_positions():
    """Liste d'objets account_data tels qu'émis par auto_fetch (event positions)."""
    return [
        {
            "secAccNo": "DA1111", "productType": "DEFAULT", "label": "CTO",
            "categories": [
                {
                    "categoryType": "stocks",
                    "positions": [
                        {
                            "isin": "US0378331005", "shortName": "AAPL", "name": "Apple Inc.",
                            "netSize": "5", "averageBuyIn": "150", "currentPrice": 180.0,
                            "accountId": "DA1111",
                        }
                    ],
                }
            ],
        },
        {
            "secAccNo": "DA2222", "productType": "TAX_WRAPPER", "label": "PEA",
            "categories": [
                {
                    "categoryType": "etfs",
                    "positions": [
                        {
                            "isin": "FR0010315770", "shortName": "CW8", "name": "Amundi MSCI World",
                            "netSize": "20", "averageBuyIn": "350", "currentPrice": 400.0,
                            "accountId": "DA2222",
                        }
                    ],
                }
            ],
        },
        {
            "secAccNo": "DA3333", "productType": "CRYPTO", "label": "Crypto",
            "categories": [
                {
                    "categoryType": "cryptos",
                    "positions": [
                        {
                            "isin": "BTC", "shortName": "BTC", "name": "Bitcoin",
                            "netSize": "0.01", "averageBuyIn": "30000", "currentPrice": 60000.0,
                            "accountId": "DA3333",
                        }
                    ],
                }
            ],
        },
    ]


def test_normalize_accounts_maps_product_type(raw_accounts):
    norm = TRNormalizer()
    accs = norm.normalize_accounts(raw_accounts, connector_id="user1:tr-1")
    by_id = {a.id: a for a in accs}
    assert by_id["tr:DA1111"].label == "CTO"
    assert by_id["tr:DA1111"].kind == "securities"
    assert by_id["tr:DA1111"].tax_wrapper == "cto"
    assert by_id["tr:DA2222"].label == "PEA"
    assert by_id["tr:DA2222"].tax_wrapper == "pea"
    assert by_id["tr:DA3333"].label == "Crypto"


def test_normalize_balances_pea_no_longer_zero(raw_accounts, raw_cash, raw_positions):
    """Régression : avant fix, le PEA renvoyait 0€ à cause du mismatch sec/cash."""
    norm = TRNormalizer()
    accs = norm.normalize_accounts(raw_accounts, connector_id="user1:tr-1")
    # Positions doivent être normalisées d'abord pour positions_value (ou injection directe)
    norm.normalize_positions(raw_positions, accs)
    bals = norm.normalize_balances(raw_cash, accs)
    by_id = {b.account_id: b for b in bals}
    # PEA = 0 cash + 20 * 400 = 8000 (positions_value)
    assert by_id["tr:DA2222"].total_value == Decimal("8000.00")
    assert by_id["tr:DA2222"].positions_value == Decimal("8000.00")
    # CTO = 150.50 + 5 * 180 = 1050.50
    assert by_id["tr:DA1111"].total_value == Decimal("1050.50")


def test_normalize_positions_includes_crypto(raw_positions, raw_accounts):
    """Régression : crypto + private equity étaient absents de la valo."""
    norm = TRNormalizer()
    accs = norm.normalize_accounts(raw_accounts, connector_id="user1:tr-1")
    poss = norm.normalize_positions(raw_positions, accs)
    by_account = {p.account_id: p for p in poss}
    assert "tr:DA3333" in by_account
    assert by_account["tr:DA3333"].asset_class == "crypto"
    assert by_account["tr:DA3333"].value == Decimal("600.00")  # 0.01 * 60000


def test_normalize_positions_handles_private_markets_without_price():
    """Private equity n'a pas de currentPrice — value = 0, current_price = None."""
    norm = TRNormalizer()
    accs = norm.normalize_accounts(
        [{"securitiesAccountNumber": "DA4444", "cashAccountNumber": "CA4444", "productType": "PRIVATE_EQUITY"}],
        connector_id="user1:tr-1",
    )
    raw_pos = [{
        "secAccNo": "DA4444", "productType": "PRIVATE_EQUITY", "label": "Private Equity",
        "categories": [{
            "categoryType": "privateMarkets",
            "positions": [{
                "isin": "PE001", "shortName": "PE Fund", "name": "Private Fund X",
                "netSize": "1", "averageBuyIn": "10000", "accountId": "DA4444",
            }],
        }],
    }]
    poss = norm.normalize_positions(raw_pos, accs)
    assert len(poss) == 1
    assert poss[0].asset_class == "private"
    assert poss[0].current_price is None
    assert poss[0].value == Decimal("0")
```

- [ ] **Step 2: Run — devrait fail (TRNormalizer n'existe pas)**

```bash
pytest tests/normalizers/test_trade_republic.py -v
```
Expected: ImportError.

- [ ] **Step 3: Implémenter `src/normalizers/trade_republic.py`**

```python
"""Normalizer Trade Republic.

Mappings :
- productType → (label, kind, tax_wrapper)
- categoryType → asset_class
- ID préfixé `tr:{securitiesAccountNumber}`
"""
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from src.normalizers import register
from src.normalizers.base import Normalizer
from src.normalizers.types import CanonicalAccount, CanonicalBalance, CanonicalPosition

PRODUCT_TYPE_MAP = {
    # productType : (label, kind, tax_wrapper)
    "DEFAULT":        ("CTO", "securities", "cto"),
    "TAX_WRAPPER":    ("PEA", "securities", "pea"),
    "PEA":            ("PEA", "securities", "pea"),
    "CRYPTO":         ("Crypto", "securities", "none"),
    "PRIVATE_EQUITY": ("Private Equity", "securities", "none"),
}

CATEGORY_TO_ASSET_CLASS = {
    "stocks": "equity",
    "etfs": "etf",
    "bonds": "bond",
    "cryptos": "crypto",
    "privateMarkets": "private",
    "derivatives": "other",
}


def _decimal(value: Any) -> Decimal:
    if value is None or value == "":
        return Decimal("0")
    return Decimal(str(value))


class TRNormalizer(Normalizer):
    def __init__(self) -> None:
        self._positions_by_account: dict[str, list[CanonicalPosition]] = {}

    def normalize_accounts(
        self, raw: list[dict], connector_id: str
    ) -> list[CanonicalAccount]:
        out: list[CanonicalAccount] = []
        for entry in raw:
            sec_no = entry.get("securitiesAccountNumber") or entry.get("cashAccountNumber")
            if not sec_no:
                continue
            product_type = entry.get("productType", "DEFAULT")
            label, kind, tax = PRODUCT_TYPE_MAP.get(
                product_type, (product_type, "securities", "none")
            )
            out.append(CanonicalAccount(
                id=f"tr:{sec_no}",
                connector_id=connector_id,
                connector_type="trade_republic",
                label=label,
                kind=kind,
                tax_wrapper=tax,
                currency=entry.get("currencyId", "EUR"),
            ))
        return out

    def normalize_positions(
        self, raw: list[dict], accounts: list[CanonicalAccount]
    ) -> list[CanonicalPosition]:
        positions: list[CanonicalPosition] = []
        self._positions_by_account = {}
        for acc_data in raw:
            sec_no = acc_data.get("secAccNo", "")
            account_id = f"tr:{sec_no}"
            for cat in acc_data.get("categories", []):
                cat_type = cat.get("categoryType", "")
                asset_class = CATEGORY_TO_ASSET_CLASS.get(cat_type, "other")
                for pos in cat.get("positions", []):
                    qty = _decimal(pos.get("netSize") or pos.get("quantity"))
                    avg = _decimal(pos.get("averageBuyIn") or pos.get("avg_price"))
                    cur_raw = pos.get("currentPrice") or pos.get("current_price")
                    cur = _decimal(cur_raw) if cur_raw else None
                    value = qty * cur if cur else Decimal("0")
                    canonical = CanonicalPosition(
                        account_id=account_id,
                        symbol=pos.get("shortName") or pos.get("symbol") or pos.get("isin", ""),
                        isin=pos.get("isin"),
                        name=pos.get("name", ""),
                        quantity=qty,
                        average_price=avg if avg > 0 else None,
                        current_price=cur,
                        value=value,
                        asset_class=asset_class,
                        currency=pos.get("currencyId", "EUR"),
                    )
                    positions.append(canonical)
                    self._positions_by_account.setdefault(account_id, []).append(canonical)
        return positions

    def normalize_balances(
        self, raw: list[dict], accounts: list[CanonicalAccount]
    ) -> list[CanonicalBalance]:
        # Map cashAccountNumber → securitiesAccountNumber pour matcher les comptes.
        # Le worker enrichit déjà le cash entry avec productType ; mais on se base sur
        # accountNumber (= cashAccountNumber). Côté accounts canonical on utilise sec.
        # Solution : on cherche dans le raw les paires sec↔cash via un dict externe injecté
        # à la normalisation. Ici, on accepte que `raw` soit une liste de cash entries
        # qui contient potentiellement un champ accountNumber correspondant à un cash
        # ou un sec id ; et on accepte aussi un fallback par index.
        as_of = datetime.now(timezone.utc)
        out: list[CanonicalBalance] = []
        # Indexer accounts par les deux IDs candidats (sec + cash) — on tracke les deux.
        # Comme TR connaît les paires sec↔cash dans accountPairs, on les accepte si
        # le worker les remonte ; sinon, fallback : pour chaque cash entry, on prend
        # l'account du même connector_id (assuré par contexte).
        for cash_entry in raw:
            cash_account_no = cash_entry.get("accountNumber", "")
            # Trouver l'account dont l'ID se termine par cash ou sec correspondant.
            # Stratégie : le worker doit enrichir cash_entry avec "secAccNo" (à patcher
            # côté worker plus tard). En attendant on tente un match par suffixe :
            target_account = None
            sec_candidate = cash_entry.get("secAccNo")
            if sec_candidate:
                target_account = next(
                    (a for a in accounts if a.id == f"tr:{sec_candidate}"), None
                )
            if target_account is None:
                # Fallback heuristique : map cash_account_no → sec via préfixe commun.
                # CA1111 ↔ DA1111 (chez TR, ils diffèrent uniquement par le 1er char).
                if cash_account_no:
                    suffix = cash_account_no[2:] if len(cash_account_no) > 2 else cash_account_no
                    target_account = next(
                        (a for a in accounts if a.id.endswith(suffix)), None
                    )
            if target_account is None:
                continue

            cash = _decimal(cash_entry.get("amount", 0))
            pos_list = self._positions_by_account.get(target_account.id, [])
            positions_value = sum(
                (p.value for p in pos_list), start=Decimal("0")
            ) if pos_list else None

            total = cash + (positions_value or Decimal("0"))
            out.append(CanonicalBalance(
                account_id=target_account.id,
                cash=cash,
                positions_value=positions_value,
                total_value=total,
                currency=cash_entry.get("currencyId", "EUR"),
                as_of=as_of,
            ))
        return out


register("trade_republic", TRNormalizer())
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/normalizers/test_trade_republic.py -v
```
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/normalizers/trade_republic.py tests/normalizers/test_trade_republic.py
git commit -m "feat(normalizers): TR — corrige PEA label + balance + crypto/PE dans valo"
```

---

### Task 5: Wire normalizers dans `ConnectorManager.collect_events`

**Files:**
- Modify: `src/manager.py:88-122`
- Modify: `src/main.py` (importer normalizers pour enregistrer)
- Test: `tests/test_manager.py`

- [ ] **Step 1: Test failing — live_data contient des CanonicalAccount**

Ajouter dans `tests/test_manager.py` :

```python
def test_collect_events_normalizes_accounts():
    """Après dispatch d'un event 'accounts' raw TR, live_data contient du canonical."""
    from src.normalizers.types import CanonicalAccount
    import src.normalizers.trade_republic  # noqa: enregistre TRNormalizer
    from src.manager import ConnectorManager

    mgr = ConnectorManager()

    # On simule un event en injectant directement dans la queue d'un faux handle.
    from multiprocessing import Queue
    from dataclasses import replace
    cmd_q, event_q = Queue(), Queue()
    from src.manager import WorkerHandle
    from multiprocessing import Process
    proc = Process(target=lambda: None)  # pas démarré ; on n'a pas besoin
    # On bypasse spawn pour ne pas démarrer un vrai process
    mgr._workers["user1:tr-1"] = WorkerHandle(
        process=proc, cmd_queue=cmd_q, event_queue=event_q,
        connector_type="trade_republic",
    )
    mgr.live_data["user1:tr-1"] = {"accounts": [], "balances": [], "positions": [], "transactions": []}

    event_q.put({"type": "accounts", "data": [
        {"securitiesAccountNumber": "DA1234", "cashAccountNumber": "CA1234", "productType": "TAX_WRAPPER"},
    ]})

    mgr.collect_events()
    accs = mgr.live_data["user1:tr-1"]["accounts"]
    assert len(accs) == 1
    assert isinstance(accs[0], CanonicalAccount)
    assert accs[0].id == "tr:DA1234"
    assert accs[0].label == "PEA"
```

- [ ] **Step 2: Run — devrait fail (live_data contient le raw, pas le canonical)**

```bash
pytest tests/test_manager.py::test_collect_events_normalizes_accounts -v
```
Expected: FAIL — `accs[0]` est un `dict`.

- [ ] **Step 3: Modifier `src/manager.py:88-122`**

Remplacer la branche `evt_type in ("accounts", "balances", "positions", "transactions")` :

```python
                    elif evt_type in ("accounts", "balances", "positions", "transactions"):
                        from src.normalizers import get_normalizer
                        if cid not in self.live_data:
                            self.live_data[cid] = {"accounts": [], "balances": [], "positions": [], "transactions": []}
                        bucket = self.live_data[cid]
                        data = event.get("data", [])
                        normalizer = get_normalizer(handle.connector_type)
                        if normalizer is None or evt_type == "transactions":
                            bucket[evt_type] = data
                        elif evt_type == "accounts":
                            bucket["accounts"] = normalizer.normalize_accounts(data, connector_id=cid)
                        elif evt_type == "positions":
                            bucket["positions"] = normalizer.normalize_positions(
                                data, bucket.get("accounts", [])
                            )
                        elif evt_type == "balances":
                            bucket["balances"] = normalizer.normalize_balances(
                                data, bucket.get("accounts", [])
                            )
```

- [ ] **Step 4: Importer les normalizers au boot**

Dans `src/main.py`, après les imports, ajouter (avant `create_app`) :

```python
# Enregistre tous les normalizers (effets de bord à l'import)
import src.normalizers.trade_republic  # noqa: F401
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/test_manager.py -v
```
Expected: tous green.

- [ ] **Step 6: Commit**

```bash
git add src/manager.py src/main.py tests/test_manager.py
git commit -m "feat(manager): normaliser accounts/balances/positions à la réception"
```

---

### Task 6: Refonte API `/api/accounts` + `/api/accounts/{id}/balance`

**Files:**
- Modify: `src/api/accounts.py`
- Modify: `src/schemas/account.py`
- Test: `tests/test_api_data.py` (ou `test_api_accounts.py` à créer)

- [ ] **Step 1: Étendre `src/schemas/account.py`**

Ajouter les champs `kind` et `tax_wrapper` (si pas déjà) :

```python
from pydantic import BaseModel
from typing import Literal

class AccountResponse(BaseModel):
    id: str
    connector_id: str
    connector_type: str
    name: str               # = label canonical
    kind: Literal["cash", "securities", "liability"]
    tax_wrapper: str = "none"
    currency: str = "EUR"
```

- [ ] **Step 2: Test failing — endpoint retourne kind + tax_wrapper**

Dans `tests/test_api_data.py` (ou nouveau `tests/test_api_accounts.py`), ajouter :

```python
def test_accounts_endpoint_exposes_kind_and_tax_wrapper(client, auth_headers):
    """L'endpoint /api/accounts retourne kind et tax_wrapper depuis le canonical."""
    # Setup: injecter manuellement dans live_data un CanonicalAccount
    from src.normalizers.types import CanonicalAccount
    from src.api import deps
    deps.manager.live_data["user1:tr-1"] = {
        "accounts": [
            CanonicalAccount(
                id="tr:DA1234",
                connector_id="user1:tr-1",
                connector_type="trade_republic",
                label="PEA",
                kind="securities",
                tax_wrapper="pea",
            )
        ],
        "balances": [], "positions": [], "transactions": [],
    }
    # auth_headers fixture à mocker pour pointer sur user1
    resp = client.get("/api/accounts", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert any(a["kind"] == "securities" and a["tax_wrapper"] == "pea" for a in data)
```

(Adapter à la fixture `auth_headers` existante du projet ; cf. `tests/test_api_accounts.py` ou `test_api_loans.py` pour le pattern.)

- [ ] **Step 3: Run — fail (champs manquants)**

```bash
pytest tests/test_api_accounts.py -v
```

- [ ] **Step 4: Réécrire `src/api/accounts.py`**

```python
from fastapi import APIRouter, Depends
from sqlalchemy import select

from src.api import deps
from src.api.middleware import get_current_user, AuthUser
from src.db.models import accounts, balance_snapshots
from src.schemas.account import AccountResponse, BalanceResponse

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


@router.get("", response_model=list[AccountResponse])
def list_accounts(
    connector_id: str | None = None,
    user: AuthUser = Depends(get_current_user),
):
    """Liste les comptes du user. Source : live_data canonical du manager."""
    out: list[AccountResponse] = []
    seen_ids: set[str] = set()

    all_data = deps.manager.get_user_live_data(user.id)
    for cid, data in all_data.items():
        if connector_id and cid != connector_id:
            continue
        for acc in data.get("accounts", []):
            # `acc` est un CanonicalAccount (Pydantic) après wiring du manager.
            if acc.id in seen_ids:
                continue
            out.append(AccountResponse(
                id=acc.id,
                connector_id=acc.connector_id,
                connector_type=acc.connector_type,
                name=acc.label,
                kind=acc.kind,
                tax_wrapper=acc.tax_wrapper,
                currency=acc.currency,
            ))
            seen_ids.add(acc.id)

    # Fallback DB pour les comptes pas live (worker offline)
    stmt = select(accounts)
    if connector_id:
        stmt = stmt.where(accounts.c.connector_id == connector_id)
    with deps.get_ledger(user.id).connect() as conn:
        rows = conn.execute(stmt).fetchall()
    for r in rows:
        if r.id in seen_ids:
            continue
        out.append(AccountResponse(
            id=r.id, connector_id=r.connector_id, connector_type=r.type or "",
            name=r.name, kind="cash", tax_wrapper="none",
            currency=r.currency or "EUR",
        ))
        seen_ids.add(r.id)
    return out


@router.get("/{account_id}/balance", response_model=BalanceResponse)
def get_balance(account_id: str, user: AuthUser = Depends(get_current_user)):
    """Solde d'un compte. Lit le canonical en mémoire."""
    all_data = deps.manager.get_user_live_data(user.id)
    for _cid, data in all_data.items():
        for bal in data.get("balances", []):
            if bal.account_id == account_id:
                return BalanceResponse(
                    account_id=bal.account_id,
                    cash=float(bal.cash) if bal.cash is not None else None,
                    positions_value=float(bal.positions_value) if bal.positions_value is not None else None,
                    total_value=float(bal.total_value),
                    currency=bal.currency,
                    updated_at=bal.as_of,
                )
    # Fallback DB
    stmt = select(balance_snapshots).where(
        balance_snapshots.c.account_id == account_id
    ).order_by(balance_snapshots.c.date.desc()).limit(1)
    with deps.get_ledger(user.id).connect() as conn:
        row = conn.execute(stmt).fetchone()
    if not row:
        return BalanceResponse(account_id=account_id, total_value=0.0)
    return BalanceResponse(
        account_id=account_id,
        cash=row.cash,
        positions_value=row.positions_value,
        total_value=row.total_value or 0.0,
        currency=row.currency or "EUR",
        updated_at=row.created_at,
    )
```

Compléter `src/schemas/account.py` :

```python
from datetime import datetime
from pydantic import BaseModel

class BalanceResponse(BaseModel):
    account_id: str
    cash: float | None = None
    positions_value: float | None = None
    total_value: float = 0.0
    currency: str = "EUR"
    updated_at: datetime | None = None
```

- [ ] **Step 5: Run all tests**

```bash
pytest tests/ -v
```
Expected: tous green (les anciens tests qui touchaient `/api/accounts` peuvent nécessiter mise à jour si ils assertaient l'ancien shape).

- [ ] **Step 6: Commit**

```bash
git add src/api/accounts.py src/schemas/account.py tests/
git commit -m "feat(api): /api/accounts retourne kind + tax_wrapper depuis canonical"
```

---

### Task 7: Refonte API `/api/portfolio` pour consommer canonical positions

**Files:**
- Modify: `src/api/portfolio.py`
- Modify: `src/schemas/portfolio.py`
- Test: `tests/test_api_data.py`

- [ ] **Step 1: Étendre `PositionResponse`**

Dans `src/schemas/portfolio.py`, ajouter le champ `asset_class` :

```python
class PositionResponse(BaseModel):
    connector_id: str
    account_id: str
    instrument: str          # = isin
    name: str
    symbol: str
    asset_class: Literal["equity", "etf", "bond", "crypto", "private", "other"]
    category: str            # rétrocompat avec front, = asset_class pour l'instant
    quantity: float
    avg_price: float | None = None
    current_price: float | None = None
    value: float | None = None
    pnl: float | None = None
    pnl_pct: float | None = None
    currency: str = "EUR"
```

- [ ] **Step 2: Réécrire `src/api/portfolio.py`**

```python
from fastapi import APIRouter, Depends

from src.api import deps
from src.api.middleware import get_current_user, AuthUser
from src.schemas.portfolio import PortfolioResponse, PositionResponse

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


@router.get("")
def get_portfolio(
    connector_id: str | None = None,
    user: AuthUser = Depends(get_current_user),
):
    """Portfolio agrégé par compte.

    Lit `positions` (CanonicalPosition list) + `balances` (CanonicalBalance list)
    + `accounts` (CanonicalAccount list) du manager.
    """
    all_data = deps.manager.get_user_live_data(user.id)

    accounts_out: list[dict] = []
    grand_total_value = 0.0
    grand_total_invested = 0.0
    grand_total_cash = 0.0

    for cid, data in all_data.items():
        if connector_id and cid != connector_id:
            continue

        accounts = data.get("accounts", [])
        balances = data.get("balances", [])
        positions = data.get("positions", [])

        balances_by_account = {b.account_id: b for b in balances}
        positions_by_account: dict[str, list] = {}
        for pos in positions:
            positions_by_account.setdefault(pos.account_id, []).append(pos)

        for acc in accounts:
            bal = balances_by_account.get(acc.id)
            cash = float(bal.cash) if bal and bal.cash is not None else 0.0
            grand_total_cash += cash

            acc_positions = positions_by_account.get(acc.id, [])
            acc_total_value = 0.0
            acc_total_invested = 0.0

            positions_out = []
            for pos in acc_positions:
                qty = float(pos.quantity)
                avg = float(pos.average_price) if pos.average_price else 0.0
                cur = float(pos.current_price) if pos.current_price else None
                val = float(pos.value) if pos.value else None
                invested = qty * avg
                pnl = (val - invested) if (val is not None and invested) else None
                pnl_pct = (pnl / invested * 100) if (pnl is not None and invested) else None

                if val is not None:
                    acc_total_value += val
                acc_total_invested += invested

                positions_out.append(PositionResponse(
                    connector_id=acc.connector_id,
                    account_id=acc.id,
                    instrument=pos.isin or "",
                    name=pos.name,
                    symbol=pos.symbol,
                    asset_class=pos.asset_class,
                    category=pos.asset_class,
                    quantity=qty,
                    avg_price=avg if avg else None,
                    current_price=cur,
                    value=val,
                    pnl=pnl,
                    pnl_pct=pnl_pct,
                    currency=pos.currency,
                ).model_dump())

            grand_total_value += acc_total_value
            grand_total_invested += acc_total_invested

            accounts_out.append({
                "account_id": acc.id,
                "label": acc.label,
                "kind": acc.kind,
                "tax_wrapper": acc.tax_wrapper,
                "cash": cash,
                "total_value": acc_total_value + cash,
                "total_invested": acc_total_invested,
                "positions": positions_out,
            })

    return {
        "accounts": accounts_out,
        "total_cash": grand_total_cash,
        "total_value": grand_total_value + grand_total_cash,
        "total_invested": grand_total_invested,
    }
```

- [ ] **Step 3: Run tests**

```bash
pytest tests/test_api_data.py -v
```
Adapter les tests existants si l'ancien shape était asserté.

- [ ] **Step 4: Commit**

```bash
git add src/api/portfolio.py src/schemas/portfolio.py tests/
git commit -m "feat(api): /api/portfolio consomme positions canonical (asset_class inclus)"
```

---

### Task 8: Frontend — types canonical + Dashboard

**Files:**
- Modify: `frontend/src/lib/types.ts`
- Modify: `frontend/src/pages/Dashboard.tsx:300-340`

- [ ] **Step 1: Étendre `frontend/src/lib/types.ts`**

```typescript
export type AccountKind = 'cash' | 'securities' | 'liability';
export type TaxWrapper =
  | 'none' | 'cto' | 'pea' | 'pea_pme' | 'per' | 'av'
  | 'livret_a' | 'livret_jeune' | 'ldds' | 'lep' | 'cel' | 'pel';
export type AssetClass = 'equity' | 'etf' | 'bond' | 'crypto' | 'private' | 'other';

export interface Account {
  id: string;
  connector_id: string;
  connector_type: ConnectorType;
  name: string;            // = label canonical
  kind: AccountKind;
  tax_wrapper: TaxWrapper;
  currency: string;
}
```

- [ ] **Step 2: Modifier `frontend/src/pages/Dashboard.tsx`**

Dans `connectorIcons` ou une nouvelle map, dériver l'icône par `kind` plutôt que `connector.type` :

```typescript
const kindIcons: Record<AccountKind, { icon: LucideIcon; bg: string }> = {
  cash:       { icon: Wallet,     bg: 'bg-emerald-900/40' },
  securities: { icon: TrendingUp, bg: 'bg-violet-900/40' },
  liability:  { icon: Receipt,    bg: 'bg-rose-900/40' },
};
```

Puis dans la `accts.map((acct) => ...)` ligne ~324 :

```tsx
const kindInfo = kindIcons[acct.kind] ?? kindIcons.cash;
const KindIcon = kindInfo.icon;
return (
  <AccountRow
    key={acct.id}
    name={acct.name}
    subtitle={connectorSubtitle(connector.type)}
    balance={bal ? formatCurrency(bal.total_value, bal.currency) : '--'}
    perf={formatPercent(0)}
    iconBg={kindInfo.bg}
    icon={<KindIcon size={16} className="text-mm-text" />}
  />
);
```

- [ ] **Step 3: Smoke test manuel**

```bash
cd frontend && bun run dev
```
Ouvrir le dashboard, vérifier :
- Le PEA TR s'affiche "PEA" (plus "TAX_WRAPPER")
- Le solde du PEA n'est plus 0 si positions
- Icônes : violet pour PEA/CTO, vert pour livrets, rose pour le compte prêt

- [ ] **Step 4: Commit**

```bash
git add frontend/src/
git commit -m "feat(frontend): consommer kind + tax_wrapper canonical"
```

---

## Phase 2 — Autres normalizers

### Task 9: Woob normalizer

**Files:**
- Create: `src/normalizers/woob_bank.py`
- Test: `tests/normalizers/test_woob_bank.py`

- [ ] **Step 1: Écrire les fixtures + tests**

```python
"""Tests Woob normalizer."""
import re
from decimal import Decimal

import pytest
from src.normalizers.woob_bank import WoobNormalizer


@pytest.fixture
def raw_accounts():
    """Format émis par le worker Woob (cf. src/connectors/woob_bank.py)."""
    return [
        {
            "id": "abc123", "backend": "bp", "label": "Compte individuel M CHARLES",
            "type": 1, "balance": "971.76", "currency": "EUR",  # TYPE_CHECKING=1
        },
        {
            "id": "abc456", "backend": "bp", "label": "Livret A-Particuliers M CHARLES",
            "type": 2, "balance": "12345.30", "currency": "EUR",  # TYPE_SAVINGS=2
        },
        {
            "id": "abc789", "backend": "bp", "label": "Livret Jeune M CHARLES",
            "type": 2, "balance": "100.00", "currency": "EUR",
        },
        {
            "id": "abc999", "backend": "bp", "label": "Vcc - Pret Jeune Standard M CHARLES",
            "type": 3, "balance": "-4000.00", "currency": "EUR",  # TYPE_LOAN=3
        },
    ]


def test_normalize_loan_kind_liability(raw_accounts):
    norm = WoobNormalizer()
    accs = norm.normalize_accounts(raw_accounts, connector_id="user1:woob-1")
    by_id = {a.id: a for a in accs}
    loan = by_id["woob:bp:abc999"]
    assert loan.kind == "liability"
    assert loan.label == "Vcc - Pret Jeune Standard M CHARLES"
    assert loan.tax_wrapper == "none"


def test_normalize_livret_a_tax_wrapper(raw_accounts):
    norm = WoobNormalizer()
    accs = norm.normalize_accounts(raw_accounts, connector_id="user1:woob-1")
    by_id = {a.id: a for a in accs}
    assert by_id["woob:bp:abc456"].tax_wrapper == "livret_a"
    assert by_id["woob:bp:abc789"].tax_wrapper == "livret_jeune"


def test_normalize_balances_loan_negative(raw_accounts):
    norm = WoobNormalizer()
    accs = norm.normalize_accounts(raw_accounts, connector_id="user1:woob-1")
    bals = norm.normalize_balances(raw_accounts, accs)
    by_id = {b.account_id: b for b in bals}
    assert by_id["woob:bp:abc999"].total_value == Decimal("-4000.00")
    assert by_id["woob:bp:abc456"].total_value == Decimal("12345.30")
```

- [ ] **Step 2: Run — fail**

```bash
pytest tests/normalizers/test_woob_bank.py -v
```

- [ ] **Step 3: Implémenter `src/normalizers/woob_bank.py`**

```python
"""Normalizer Woob (banques FR)."""
import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from src.normalizers import register
from src.normalizers.base import Normalizer
from src.normalizers.types import CanonicalAccount, CanonicalBalance, CanonicalPosition

# Constantes Woob (équivalentes à `from woob.capabilities.bank import Account`).
# On les redéfinit pour ne pas faire dépendre le normalizer de woob (testabilité).
WOOB_TYPE_CHECKING = 1
WOOB_TYPE_SAVINGS = 2
WOOB_TYPE_LOAN = 3
WOOB_TYPE_MARKET = 4
WOOB_TYPE_DEPOSIT = 5
WOOB_TYPE_CARD = 6
WOOB_TYPE_LIFE_INSURANCE = 7
WOOB_TYPE_PEA = 8
WOOB_TYPE_PERP = 13

TYPE_TO_KIND = {
    WOOB_TYPE_CHECKING: "cash",
    WOOB_TYPE_SAVINGS: "cash",
    WOOB_TYPE_DEPOSIT: "cash",
    WOOB_TYPE_LOAN: "liability",
    WOOB_TYPE_CARD: "liability",
    WOOB_TYPE_MARKET: "securities",
    WOOB_TYPE_PEA: "securities",
    WOOB_TYPE_LIFE_INSURANCE: "securities",
    WOOB_TYPE_PERP: "securities",
}

TYPE_TO_TAX_WRAPPER = {
    WOOB_TYPE_PEA: "pea",
    WOOB_TYPE_LIFE_INSURANCE: "av",
    WOOB_TYPE_PERP: "per",
}

LABEL_PATTERNS = [
    (re.compile(r"\bLivret\s+A\b", re.IGNORECASE), "livret_a"),
    (re.compile(r"\bLivret\s+Jeune\b", re.IGNORECASE), "livret_jeune"),
    (re.compile(r"\bLDDS?\b", re.IGNORECASE), "ldds"),
    (re.compile(r"\bLEP\b", re.IGNORECASE), "lep"),
    (re.compile(r"\bCEL\b", re.IGNORECASE), "cel"),
    (re.compile(r"\bPEL\b", re.IGNORECASE), "pel"),
]


def _wrapper_from_label(label: str) -> str:
    for pattern, wrapper in LABEL_PATTERNS:
        if pattern.search(label):
            return wrapper
    return "none"


class WoobNormalizer(Normalizer):
    def normalize_accounts(self, raw, connector_id):
        out = []
        for entry in raw:
            backend = entry.get("backend", "x")
            acc_id = f"woob:{backend}:{entry.get('id', '')}"
            woob_type = int(entry.get("type", WOOB_TYPE_CHECKING))
            kind = TYPE_TO_KIND.get(woob_type, "cash")
            tax = TYPE_TO_TAX_WRAPPER.get(woob_type)
            if not tax:
                tax = _wrapper_from_label(entry.get("label", "")) if kind == "cash" else "none"
            out.append(CanonicalAccount(
                id=acc_id,
                connector_id=connector_id,
                connector_type="woob_bank",
                label=entry.get("label", ""),
                kind=kind,
                tax_wrapper=tax,
                currency=entry.get("currency", "EUR"),
            ))
        return out

    def normalize_balances(self, raw, accounts):
        as_of = datetime.now(timezone.utc)
        by_lookup = {a.id: a for a in accounts}
        out = []
        for entry in raw:
            backend = entry.get("backend", "x")
            acc_id = f"woob:{backend}:{entry.get('id', '')}"
            account = by_lookup.get(acc_id)
            if not account:
                continue
            balance = Decimal(str(entry.get("balance", "0")))
            # Convention : kind=liability → total_value négatif.
            if account.kind == "liability":
                total = -abs(balance)
            else:
                total = balance
            out.append(CanonicalBalance(
                account_id=acc_id,
                cash=balance if account.kind != "securities" else None,
                positions_value=None,
                total_value=total,
                currency=entry.get("currency", "EUR"),
                as_of=as_of,
            ))
        return out

    def normalize_positions(self, raw, accounts):
        return []  # Woob ne remonte pas de positions par défaut


register("woob_bank", WoobNormalizer())
```

- [ ] **Step 4: Run tests + ajout de l'import dans `src/main.py`**

Dans `src/main.py`, ajouter :
```python
import src.normalizers.woob_bank  # noqa: F401
```

```bash
pytest tests/normalizers/test_woob_bank.py -v
```
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/normalizers/woob_bank.py tests/normalizers/test_woob_bank.py src/main.py
git commit -m "feat(normalizers): woob_bank — kind=liability pour TYPE_LOAN, tax_wrapper inferred"
```

---

### Task 10: Enable Banking normalizer

**Files:**
- Create: `src/normalizers/enable_banking.py`
- Test: `tests/normalizers/test_enable_banking.py`

- [ ] **Step 1: Tests**

```python
import pytest
from decimal import Decimal
from src.normalizers.enable_banking import BankingNormalizer


@pytest.fixture
def raw_accounts():
    """Format Enable Banking (PSD2)."""
    return [
        {"uid": "uid-1", "name": "Compte courant", "product": "CHECKING",
         "cashAccountType": "CACC", "currency": "EUR",
         "balances": [{"balanceAmount": {"amount": "500.00", "currency": "EUR"}}]},
        {"uid": "uid-2", "name": "Crédit auto", "product": "LOAN",
         "cashAccountType": "LOAN", "currency": "EUR",
         "balances": [{"balanceAmount": {"amount": "-15000.00", "currency": "EUR"}}]},
    ]


def test_normalize_loan(raw_accounts):
    norm = BankingNormalizer()
    accs = norm.normalize_accounts(raw_accounts, connector_id="user1:eb-1")
    by_id = {a.id: a for a in accs}
    assert by_id["eb:uid-2"].kind == "liability"


def test_normalize_balances_negative(raw_accounts):
    norm = BankingNormalizer()
    accs = norm.normalize_accounts(raw_accounts, connector_id="user1:eb-1")
    bals = norm.normalize_balances(raw_accounts, accs)
    by_id = {b.account_id: b for b in bals}
    assert by_id["eb:uid-2"].total_value == Decimal("-15000.00")
```

- [ ] **Step 2: Implémenter**

```python
"""Normalizer Enable Banking (PSD2)."""
from datetime import datetime, timezone
from decimal import Decimal

from src.normalizers import register
from src.normalizers.base import Normalizer
from src.normalizers.types import CanonicalAccount, CanonicalBalance

PSD2_TYPE_TO_KIND = {
    "CACC": "cash", "SVGS": "cash", "MOMA": "cash",
    "LOAN": "liability", "CARD": "liability",
}


class BankingNormalizer(Normalizer):
    def normalize_accounts(self, raw, connector_id):
        out = []
        for entry in raw:
            psd2_type = (entry.get("cashAccountType") or "CACC").upper()
            kind = PSD2_TYPE_TO_KIND.get(psd2_type, "cash")
            out.append(CanonicalAccount(
                id=f"eb:{entry.get('uid', '')}",
                connector_id=connector_id,
                connector_type="banking",
                label=entry.get("name") or entry.get("product", ""),
                kind=kind,
                tax_wrapper="none",
                currency=entry.get("currency", "EUR"),
            ))
        return out

    def normalize_balances(self, raw, accounts):
        as_of = datetime.now(timezone.utc)
        by_id = {a.id: a for a in accounts}
        out = []
        for entry in raw:
            acc_id = f"eb:{entry.get('uid', '')}"
            account = by_id.get(acc_id)
            if not account:
                continue
            balances = entry.get("balances", [])
            if not balances:
                continue
            amount_raw = balances[0].get("balanceAmount", {}).get("amount", "0")
            amount = Decimal(str(amount_raw))
            if account.kind == "liability":
                total = -abs(amount)
            else:
                total = amount
            out.append(CanonicalBalance(
                account_id=acc_id, cash=amount,
                positions_value=None, total_value=total,
                currency=entry.get("currency", "EUR"), as_of=as_of,
            ))
        return out

    def normalize_positions(self, raw, accounts):
        return []


register("banking", BankingNormalizer())
```

- [ ] **Step 3: Run tests + ajout import `src/main.py`**

```python
import src.normalizers.enable_banking  # noqa: F401
```

```bash
pytest tests/normalizers/test_enable_banking.py -v
```

- [ ] **Step 4: Commit**

```bash
git add src/normalizers/enable_banking.py tests/normalizers/test_enable_banking.py src/main.py
git commit -m "feat(normalizers): enable_banking — PSD2 cashAccountType → kind"
```

---

### Task 11: IBKR normalizer

**Files:**
- Create: `src/normalizers/ibkr.py`
- Test: `tests/normalizers/test_ibkr.py`

- [ ] **Step 1: Tests**

```python
import pytest
from decimal import Decimal
from src.normalizers.ibkr import IBKRNormalizer


def test_normalize_account():
    norm = IBKRNormalizer()
    raw = [{"account_id": "U24281721", "currency": "EUR"}]
    accs = norm.normalize_accounts(raw, connector_id="user1:ibkr-1")
    assert accs[0].id == "ibkr:U24281721"
    assert accs[0].kind == "securities"
    assert accs[0].tax_wrapper == "cto"


def test_normalize_position_asset_class_from_sec_type():
    norm = IBKRNormalizer()
    accs = norm.normalize_accounts(
        [{"account_id": "U1", "currency": "EUR"}], connector_id="user1:ibkr-1"
    )
    raw_pos = [{
        "account_id": "U1", "symbol": "AAPL", "secType": "STK",
        "isin": "US0378331005", "name": "Apple",
        "quantity": "10", "avg_price": "150", "current_price": "180",
    }]
    poss = norm.normalize_positions(raw_pos, accs)
    assert poss[0].asset_class == "equity"
    assert poss[0].value == Decimal("1800")
```

- [ ] **Step 2: Implémenter**

```python
"""Normalizer IBKR."""
from datetime import datetime, timezone
from decimal import Decimal

from src.normalizers import register
from src.normalizers.base import Normalizer
from src.normalizers.types import CanonicalAccount, CanonicalBalance, CanonicalPosition

SEC_TYPE_TO_ASSET_CLASS = {
    "STK": "equity", "ETF": "etf", "BOND": "bond",
    "CRYPTO": "crypto", "FUT": "other", "OPT": "other", "FOP": "other",
}


class IBKRNormalizer(Normalizer):
    def normalize_accounts(self, raw, connector_id):
        out = []
        for entry in raw:
            acc_id = entry.get("account_id") or entry.get("accountId", "")
            out.append(CanonicalAccount(
                id=f"ibkr:{acc_id}",
                connector_id=connector_id,
                connector_type="ibkr",
                label=acc_id,
                kind="securities",
                tax_wrapper="cto",
                currency=entry.get("currency", "EUR"),
            ))
        return out

    def normalize_balances(self, raw, accounts):
        as_of = datetime.now(timezone.utc)
        out = []
        by_id = {a.id: a for a in accounts}
        for entry in raw:
            acc_id = f"ibkr:{entry.get('account_id') or entry.get('accountId', '')}"
            if acc_id not in by_id:
                continue
            cash = Decimal(str(entry.get("cash", "0")))
            pv = Decimal(str(entry.get("positions_value", "0")))
            out.append(CanonicalBalance(
                account_id=acc_id, cash=cash, positions_value=pv,
                total_value=cash + pv, currency=entry.get("currency", "EUR"),
                as_of=as_of,
            ))
        return out

    def normalize_positions(self, raw, accounts):
        out = []
        by_acc = {a.id: a for a in accounts}
        for pos in raw:
            acc_id = f"ibkr:{pos.get('account_id') or pos.get('accountId', '')}"
            if acc_id not in by_acc:
                continue
            sec_type = pos.get("secType", "STK").upper()
            asset_class = SEC_TYPE_TO_ASSET_CLASS.get(sec_type, "other")
            qty = Decimal(str(pos.get("quantity", 0)))
            avg = Decimal(str(pos.get("avg_price", 0)))
            cur_raw = pos.get("current_price")
            cur = Decimal(str(cur_raw)) if cur_raw else None
            value = qty * cur if cur else Decimal("0")
            out.append(CanonicalPosition(
                account_id=acc_id,
                symbol=pos.get("symbol", ""),
                isin=pos.get("isin"),
                name=pos.get("name", pos.get("symbol", "")),
                quantity=qty,
                average_price=avg if avg > 0 else None,
                current_price=cur,
                value=value,
                asset_class=asset_class,
                currency=pos.get("currency", "EUR"),
            ))
        return out


register("ibkr", IBKRNormalizer())
```

- [ ] **Step 3: Run tests + import dans main.py**

```python
import src.normalizers.ibkr  # noqa: F401
```

```bash
pytest tests/normalizers/test_ibkr.py -v
```

- [ ] **Step 4: Commit**

```bash
git add src/normalizers/ibkr.py tests/normalizers/test_ibkr.py src/main.py
git commit -m "feat(normalizers): ibkr — asset_class via secType"
```

---

## Phase 3 — Auto-détection prêts + lien

### Task 12: Migration `loan_account_link` table

**Files:**
- Create: `src/db/migrations/versions/<timestamp>_add_loan_account_link.py`
- Modify: `src/db/models.py`

- [ ] **Step 1: Générer le squelette Alembic**

```bash
source .venv/bin/activate
alembic -c alembic.ini revision -m "add loan_account_link table"
```
Note : `mm-ledger` utilise potentiellement un script d'initialisation custom (cf. `src/db/init.py`). Si pas d'Alembic actif, créer le fichier de migration manuellement dans `src/db/migrations/versions/` ou ajouter un `CREATE TABLE IF NOT EXISTS` au bootstrap.

- [ ] **Step 2: Écrire la migration**

```python
"""add loan_account_link table

Revision ID: <auto>
"""
import sqlalchemy as sa
from alembic import op

revision = "<auto>"
down_revision = "<previous>"


def upgrade():
    op.create_table(
        "loan_account_link",
        sa.Column("account_id", sa.Text, primary_key=True),
        sa.Column("loan_id", sa.Integer,
                  sa.ForeignKey("loans.id", ondelete="SET NULL"), nullable=True),
        sa.Column("ignored", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_balance", sa.Float, nullable=True),
        sa.Column("last_seen_at", sa.Text, nullable=True),
        sa.Column("created_at", sa.Text, nullable=False, server_default=sa.text("(datetime('now'))")),
    )
    op.create_index("idx_loan_account_link_loan", "loan_account_link", ["loan_id"])


def downgrade():
    op.drop_index("idx_loan_account_link_loan", table_name="loan_account_link")
    op.drop_table("loan_account_link")
```

- [ ] **Step 3: Ajouter la `Table` dans `src/db/models.py`**

```python
loan_account_link = Table(
    "loan_account_link", metadata,
    Column("account_id", Text, primary_key=True),
    Column("loan_id", Integer, ForeignKey("loans.id", ondelete="SET NULL"), nullable=True),
    Column("ignored", Integer, nullable=False, server_default="0"),
    Column("last_balance", Float, nullable=True),
    Column("last_seen_at", Text, nullable=True),
    Column("created_at", Text, nullable=False, server_default=text("(datetime('now'))")),
)
```

- [ ] **Step 4: Tester la création de table**

Lancer un test existant qui crée le ledger user :
```bash
pytest tests/test_api_loans.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/db/ alembic/
git commit -m "feat(db): table loan_account_link (lien prêt ↔ compte bancaire)"
```

---

### Task 13: API `/api/loans/candidates` + link/ignore

**Files:**
- Modify: `src/api/loans.py`
- Modify: `src/schemas/loans.py`
- Test: `tests/test_api_loans.py`

- [ ] **Step 1: Schémas Pydantic**

Dans `src/schemas/loans.py`, ajouter :

```python
class LoanCandidate(BaseModel):
    account_id: str
    label: str
    balance: float
    currency: str
    connector_type: str
    as_of: datetime | None = None


class LinkRequest(BaseModel):
    account_id: str
```

- [ ] **Step 2: Test failing — endpoint candidates retourne les liabilities non liées**

```python
def test_candidates_returns_unlinked_liability_accounts(client, auth_headers):
    """GET /api/loans/candidates retourne les comptes liability non liés non ignorés."""
    from src.normalizers.types import CanonicalAccount, CanonicalBalance
    from src.api import deps
    from datetime import datetime, timezone
    from decimal import Decimal

    deps.manager.live_data["user1:woob-1"] = {
        "accounts": [CanonicalAccount(
            id="woob:bp:abc999",
            connector_id="user1:woob-1",
            connector_type="woob_bank",
            label="Vcc - Pret Jeune Standard",
            kind="liability",
        )],
        "balances": [CanonicalBalance(
            account_id="woob:bp:abc999",
            total_value=Decimal("-4000.00"),
            cash=Decimal("-4000.00"),
            as_of=datetime.now(timezone.utc),
        )],
        "positions": [], "transactions": [],
    }
    resp = client.get("/api/loans/candidates", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["account_id"] == "woob:bp:abc999"
    assert data[0]["balance"] == -4000.0


def test_link_endpoint_persists_link(client, auth_headers):
    """POST /api/loans/{id}/link enregistre le lien et retire du candidates."""
    # Créer un loan
    resp = client.post("/api/loans", headers=auth_headers, json={
        "name": "Prêt Jeune", "loan_type": "conso",
        "initial_capital": 5000, "monthly_payment": 200,
        "total_months": 24, "start_date": "2026-01-01",
    })
    loan_id = resp.json()["id"]

    # Setup live_data avec un candidat
    # ... (similaire au test précédent)

    # Link
    resp = client.post(
        f"/api/loans/{loan_id}/link", headers=auth_headers,
        json={"account_id": "woob:bp:abc999"},
    )
    assert resp.status_code == 200

    # Le candidat ne doit plus apparaître
    resp = client.get("/api/loans/candidates", headers=auth_headers)
    assert resp.json() == []
```

- [ ] **Step 3: Implémenter dans `src/api/loans.py`**

Ajouter :

```python
from src.db.models import loan_account_link

@router.get("/candidates", response_model=list[LoanCandidate])
def list_candidates(user: AuthUser = Depends(get_current_user)):
    engine = deps.get_ledger(user.id)
    with engine.connect() as conn:
        link_rows = conn.execute(select(loan_account_link)).fetchall()
    links_by_id = {r.account_id: r for r in link_rows}

    out: list[LoanCandidate] = []
    all_data = deps.manager.get_user_live_data(user.id)
    for cid, data in all_data.items():
        balances_by_id = {b.account_id: b for b in data.get("balances", [])}
        for acc in data.get("accounts", []):
            if acc.kind != "liability":
                continue
            link = links_by_id.get(acc.id)
            if link and (link.loan_id is not None or link.ignored):
                continue
            bal = balances_by_id.get(acc.id)
            out.append(LoanCandidate(
                account_id=acc.id,
                label=acc.label,
                balance=float(bal.total_value) if bal else 0.0,
                currency=bal.currency if bal else acc.currency,
                connector_type=acc.connector_type,
                as_of=bal.as_of if bal else None,
            ))
    return out


@router.post("/{loan_id}/link", response_model=LoanResponse)
def link_account(loan_id: int, payload: LinkRequest, user: AuthUser = Depends(get_current_user)):
    engine = deps.get_ledger(user.id)
    with engine.begin() as conn:
        loan_row = conn.execute(select(loans).where(loans.c.id == loan_id)).fetchone()
        if not loan_row:
            raise HTTPException(404, "Prêt introuvable")
        # Upsert
        existing = conn.execute(
            select(loan_account_link).where(loan_account_link.c.account_id == payload.account_id)
        ).fetchone()
        if existing:
            conn.execute(
                update(loan_account_link).where(
                    loan_account_link.c.account_id == payload.account_id
                ).values(loan_id=loan_id, ignored=0)
            )
        else:
            conn.execute(insert(loan_account_link).values(
                account_id=payload.account_id, loan_id=loan_id, ignored=0,
            ))
    return _row_to_response_with_link(loan_row, _date.today(), user.id)


@router.delete("/{loan_id}/link", status_code=status.HTTP_204_NO_CONTENT)
def unlink_account(loan_id: int, user: AuthUser = Depends(get_current_user)):
    engine = deps.get_ledger(user.id)
    with engine.begin() as conn:
        conn.execute(
            update(loan_account_link).where(
                loan_account_link.c.loan_id == loan_id
            ).values(loan_id=None)
        )
    return None


@router.post("/candidates/{account_id}/ignore", status_code=status.HTTP_204_NO_CONTENT)
def ignore_candidate(account_id: str, user: AuthUser = Depends(get_current_user)):
    engine = deps.get_ledger(user.id)
    with engine.begin() as conn:
        existing = conn.execute(
            select(loan_account_link).where(loan_account_link.c.account_id == account_id)
        ).fetchone()
        if existing:
            conn.execute(
                update(loan_account_link).where(
                    loan_account_link.c.account_id == account_id
                ).values(ignored=1)
            )
        else:
            conn.execute(insert(loan_account_link).values(account_id=account_id, ignored=1))
    return None


@router.delete("/candidates/{account_id}/ignore", status_code=status.HTTP_204_NO_CONTENT)
def unignore_candidate(account_id: str, user: AuthUser = Depends(get_current_user)):
    engine = deps.get_ledger(user.id)
    with engine.begin() as conn:
        conn.execute(
            update(loan_account_link).where(
                loan_account_link.c.account_id == account_id
            ).values(ignored=0)
        )
    return None
```

(Le helper `_row_to_response_with_link` est défini en Task 15.)

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_api_loans.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/api/loans.py src/schemas/loans.py tests/test_api_loans.py
git commit -m "feat(loans): endpoints candidates + link/unlink + ignore"
```

---

### Task 14: API `POST /api/loans/from-account`

**Files:**
- Modify: `src/api/loans.py`
- Modify: `src/schemas/loans.py`
- Test: `tests/test_api_loans.py`

- [ ] **Step 1: Schéma**

```python
class FromAccountRequest(BaseModel):
    account_id: str
    name: str
    loan_type: Literal["immo", "conso", "auto", "other"] = "conso"
    initial_capital: float
    monthly_payment: float
    total_months: int
    start_date: date
```

- [ ] **Step 2: Test failing**

```python
def test_from_account_creates_loan_and_link(client, auth_headers):
    # Setup live_data avec liability...
    resp = client.post("/api/loans/from-account", headers=auth_headers, json={
        "account_id": "woob:bp:abc999",
        "name": "Prêt depuis banque",
        "loan_type": "conso",
        "initial_capital": 4000,
        "monthly_payment": 200,
        "total_months": 20,
        "start_date": "2026-01-01",
    })
    assert resp.status_code == 201
    loan_id = resp.json()["id"]
    # Le compte n'est plus candidat
    candidates = client.get("/api/loans/candidates", headers=auth_headers).json()
    assert all(c["account_id"] != "woob:bp:abc999" for c in candidates)
```

- [ ] **Step 3: Implémenter**

```python
@router.post("/from-account", response_model=LoanResponse, status_code=status.HTTP_201_CREATED)
def create_from_account(payload: FromAccountRequest, user: AuthUser = Depends(get_current_user)):
    engine = deps.get_ledger(user.id)
    with engine.begin() as conn:
        result = conn.execute(insert(loans).values(
            name=payload.name, loan_type=payload.loan_type,
            initial_capital=payload.initial_capital,
            monthly_payment=payload.monthly_payment,
            total_months=payload.total_months,
            start_date=payload.start_date,
        ))
        lid = result.inserted_primary_key[0]
        existing = conn.execute(
            select(loan_account_link).where(loan_account_link.c.account_id == payload.account_id)
        ).fetchone()
        if existing:
            conn.execute(
                update(loan_account_link).where(
                    loan_account_link.c.account_id == payload.account_id
                ).values(loan_id=lid, ignored=0)
            )
        else:
            conn.execute(insert(loan_account_link).values(
                account_id=payload.account_id, loan_id=lid, ignored=0,
            ))
        row = conn.execute(select(loans).where(loans.c.id == lid)).fetchone()
    return _row_to_response_with_link(row, _date.today(), user.id)
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_api_loans.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/api/loans.py src/schemas/loans.py tests/test_api_loans.py
git commit -m "feat(loans): POST /api/loans/from-account (création atomique loan + lien)"
```

---

### Task 15: `compute_loan_state` étendu avec `linked_balance` + `amount_source`

**Files:**
- Modify: `src/services/loan_calc.py`
- Modify: `src/api/loans.py` (helper `_row_to_response_with_link`)
- Modify: `src/schemas/loans.py` (`LoanResponse` étendu)
- Test: `tests/test_loan_calc.py`

- [ ] **Step 1: Étendre `LoanResponse`**

```python
class LoanResponse(BaseModel):
    # ... champs existants
    linked_account_id: str | None = None
    linked_label: str | None = None
    amount_source: Literal["calendar", "bank"] = "calendar"
```

- [ ] **Step 2: Test failing — `compute_loan_state` accepte linked_balance**

```python
from datetime import date, datetime, timezone, timedelta
from decimal import Decimal
from src.services.loan_calc import compute_loan_state


def test_compute_with_recent_bank_balance_uses_bank():
    loan = {
        "start_date": date(2026, 1, 1),
        "total_months": 24,
        "monthly_payment": 200.0,
        "initial_capital": 4000.0,
        "archived": 0,
    }
    state = compute_loan_state(
        loan, today=date(2026, 4, 30),
        linked_balance=Decimal("-3500.00"),
        balance_as_of=datetime.now(timezone.utc),
    )
    assert state["amount_source"] == "bank"
    assert state["amount_remaining"] == 3500.0
    # 3500 / 200 = 17.5, round = 18 (mais peut être 17 selon round half)
    assert state["months_remaining"] in (17, 18)


def test_compute_with_stale_bank_balance_falls_back_to_calendar():
    loan = {"start_date": date(2026, 1, 1), "total_months": 24,
            "monthly_payment": 200.0, "initial_capital": 4000.0, "archived": 0}
    stale = datetime.now(timezone.utc) - timedelta(days=30)
    state = compute_loan_state(
        loan, today=date(2026, 4, 30),
        linked_balance=Decimal("-3500.00"), balance_as_of=stale,
    )
    assert state["amount_source"] == "calendar"
```

- [ ] **Step 3: Modifier `src/services/loan_calc.py`**

```python
from datetime import date, datetime, timezone
from decimal import Decimal
from dateutil.relativedelta import relativedelta

BANK_BALANCE_FRESHNESS_DAYS = 7


def compute_loan_state(
    loan: dict,
    today: date,
    linked_balance: Decimal | None = None,
    balance_as_of: datetime | None = None,
) -> dict:
    start = loan["start_date"] if isinstance(loan["start_date"], date) else date.fromisoformat(loan["start_date"])
    end_date = start + relativedelta(months=loan["total_months"])
    months_paid_calendar = 0
    if today >= start:
        delta = relativedelta(today, start)
        months_paid_calendar = delta.years * 12 + delta.months
    months_paid_calendar = max(0, min(months_paid_calendar, loan["total_months"]))
    months_remaining_calendar = loan["total_months"] - months_paid_calendar
    monthly = float(loan["monthly_payment"])

    use_bank = (
        linked_balance is not None
        and balance_as_of is not None
        and (datetime.now(timezone.utc) - balance_as_of).days < BANK_BALANCE_FRESHNESS_DAYS
        and monthly > 0
    )

    if use_bank:
        amount_remaining = float(abs(linked_balance))
        months_remaining = int(round(amount_remaining / monthly))
        amount_source = "bank"
    else:
        amount_remaining = round(monthly * months_remaining_calendar, 2)
        months_remaining = months_remaining_calendar
        amount_source = "calendar"

    progress_pct = (
        (loan["total_months"] - months_remaining) / loan["total_months"] * 100
        if loan["total_months"] else 0
    )
    is_active = months_remaining > 0 and not loan.get("archived")

    return {
        "end_date": end_date,
        "months_paid": loan["total_months"] - months_remaining,
        "months_remaining": months_remaining,
        "amount_remaining": amount_remaining,
        "progress_pct": round(progress_pct, 1),
        "is_active": is_active,
        "amount_source": amount_source,
    }
```

- [ ] **Step 4: Helper `_row_to_response_with_link` dans `src/api/loans.py`**

```python
def _row_to_response_with_link(row, today: _date, user_id: str) -> LoanResponse:
    """Comme _row_to_response, mais lit le lien + le solde bancaire si dispo."""
    engine = deps.get_ledger(user_id)
    linked_account_id = None
    linked_balance = None
    balance_as_of = None
    linked_label = None
    with engine.connect() as conn:
        link = conn.execute(
            select(loan_account_link).where(loan_account_link.c.loan_id == row.id)
        ).fetchone()
    if link:
        linked_account_id = link.account_id
        # Cherche le solde live
        all_data = deps.manager.get_user_live_data(user_id)
        for _cid, data in all_data.items():
            for bal in data.get("balances", []):
                if bal.account_id == linked_account_id:
                    linked_balance = bal.total_value
                    balance_as_of = bal.as_of
                    break
            for acc in data.get("accounts", []):
                if acc.id == linked_account_id:
                    linked_label = acc.label
                    break

    state = compute_loan_state({
        "start_date": row.start_date, "total_months": row.total_months,
        "monthly_payment": row.monthly_payment,
        "initial_capital": row.initial_capital, "archived": row.archived,
    }, today, linked_balance=linked_balance, balance_as_of=balance_as_of)

    return LoanResponse(
        id=row.id, name=row.name, loan_type=row.loan_type,
        initial_capital=row.initial_capital, monthly_payment=row.monthly_payment,
        total_months=row.total_months, start_date=row.start_date,
        archived=bool(row.archived), created_at=row.created_at,
        end_date=state["end_date"],
        months_paid=state["months_paid"],
        months_remaining=state["months_remaining"],
        amount_remaining=state["amount_remaining"],
        progress_pct=state["progress_pct"], is_active=state["is_active"],
        linked_account_id=linked_account_id,
        linked_label=linked_label,
        amount_source=state["amount_source"],
    )
```

Remplacer les 4 appels de `_row_to_response(row, today)` par `_row_to_response_with_link(row, today, user.id)`.

- [ ] **Step 5: Run tests**

```bash
pytest tests/test_loan_calc.py tests/test_api_loans.py -v
```

- [ ] **Step 6: Commit**

```bash
git add src/services/loan_calc.py src/api/loans.py src/schemas/loans.py tests/
git commit -m "feat(loans): amount_source bank|calendar (solde bancaire prio si <7j)"
```

---

### Task 16: UI — page Prêts avec section Candidats

**Files:**
- Create: `frontend/src/components/LoanCandidates.tsx`
- Modify: `frontend/src/pages/Prets.tsx`
- Modify: `frontend/src/api/loans.ts`

- [ ] **Step 1: Étendre le client API**

Dans `frontend/src/api/loans.ts` :

```typescript
export interface LoanCandidate {
  account_id: string;
  label: string;
  balance: number;
  currency: string;
  connector_type: string;
  as_of: string | null;
}

export const loansApi = {
  // ... existant
  candidates: () => apiGet<LoanCandidate[]>('/api/loans/candidates'),
  link: (loanId: number, accountId: string) =>
    apiPost(`/api/loans/${loanId}/link`, { account_id: accountId }),
  unlink: (loanId: number) =>
    apiDelete(`/api/loans/${loanId}/link`),
  ignoreCandidate: (accountId: string) =>
    apiPost(`/api/loans/candidates/${accountId}/ignore`, {}),
  unignoreCandidate: (accountId: string) =>
    apiDelete(`/api/loans/candidates/${accountId}/ignore`),
  fromAccount: (data: {
    account_id: string; name: string; loan_type: string;
    initial_capital: number; monthly_payment: number;
    total_months: number; start_date: string;
  }) => apiPost('/api/loans/from-account', data),
};
```

- [ ] **Step 2: Créer `LoanCandidates.tsx`**

```tsx
import { useState } from 'react';
import { Card, Button } from '@heroui/react';
import { Link2, Plus, EyeOff } from 'lucide-react';
import type { LoanCandidate } from '../api/loans';
import { formatCurrency } from '../lib/format';

interface Props {
  candidates: LoanCandidate[];
  onLink: (candidate: LoanCandidate) => void;
  onCreate: (candidate: LoanCandidate) => void;
  onIgnore: (candidate: LoanCandidate) => void;
}

export function LoanCandidates({ candidates, onLink, onCreate, onIgnore }: Props) {
  if (candidates.length === 0) return null;
  return (
    <Card className="bg-mm-surface border border-mm-border p-4">
      <h2 className="text-base font-semibold mb-3">Candidats détectés</h2>
      <p className="text-xs text-mm-text-muted mb-3">
        Comptes de type prêt remontés par tes connecteurs bancaires.
      </p>
      <div className="flex flex-col gap-2">
        {candidates.map((c) => (
          <div key={c.account_id} className="flex items-center justify-between p-3 rounded-lg bg-mm-surface-elevated">
            <div className="flex flex-col">
              <span className="font-medium text-sm">{c.label}</span>
              <span className="text-xs text-mm-text-muted">
                {formatCurrency(c.balance, c.currency)} · {c.connector_type}
              </span>
            </div>
            <div className="flex gap-2">
              <Button size="sm" variant="flat" onPress={() => onLink(c)}>
                <Link2 size={14} /> Lier
              </Button>
              <Button size="sm" variant="flat" onPress={() => onCreate(c)}>
                <Plus size={14} /> Créer
              </Button>
              <Button size="sm" variant="light" onPress={() => onIgnore(c)}>
                <EyeOff size={14} /> Ignorer
              </Button>
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
}
```

- [ ] **Step 3: Intégrer dans `frontend/src/pages/Prets.tsx`**

En haut de la page, charger les candidats :

```tsx
const [candidates, setCandidates] = useState<LoanCandidate[]>([]);
useEffect(() => {
  loansApi.candidates().then(setCandidates);
}, [loans]);  // recharge quand la liste de loans change

const handleLinkCandidate = async (c: LoanCandidate) => {
  // Ouvrir une modale "Lier à un prêt existant" avec liste deroulante
  // Au submit : await loansApi.link(selectedLoanId, c.account_id);
  // Reload loans + candidates
};

const handleCreateFromCandidate = (c: LoanCandidate) => {
  // Ouvrir la modale création avec préfill : name=c.label, initial_capital=Math.abs(c.balance)
};

const handleIgnoreCandidate = async (c: LoanCandidate) => {
  await loansApi.ignoreCandidate(c.account_id);
  setCandidates((prev) => prev.filter((x) => x.account_id !== c.account_id));
};

return (
  <div className="flex flex-col gap-4">
    <LoanCandidates
      candidates={candidates}
      onLink={handleLinkCandidate}
      onCreate={handleCreateFromCandidate}
      onIgnore={handleIgnoreCandidate}
    />
    {/* liste existante des prêts */}
  </div>
);
```

Sur chaque card de prêt existant, afficher le badge si lié :

```tsx
{loan.linked_account_id && (
  <div className="text-xs text-mm-text-muted">
    Lié à : <span className="font-medium">{loan.linked_label}</span>
    {loan.amount_source === 'bank' ? ' · solde synchronisé' : ' · calcul calendaire'}
  </div>
)}
```

- [ ] **Step 4: Smoke test manuel**

```bash
cd frontend && bun run dev
```
- Aller sur `/prets`, vérifier qu'un candidat apparaît si Woob remonte un compte loan.
- Cliquer "Créer", vérifier que la modale est préremplie.
- Cliquer "Ignorer", vérifier qu'il disparaît et ne revient pas après refresh.
- Cliquer "Lier", choisir un prêt existant, vérifier le badge "Lié à : ..." sur la card.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/
git commit -m "feat(prets): UI candidats détectés (lier / créer / ignorer)"
```

---

## Self-Review

**Spec coverage check** :
- §1 schéma canonical → Task 1 ✓
- §2 stable IDs → embedded dans normalizers (T4 préfixe `tr:`, T9 `woob:{backend}:`, T10 `eb:`, T11 `ibkr:`) ✓
- §3 architecture (registry, manager wiring) → T2, T3, T5 ✓
- §4 règles par connecteur → T4 (TR), T9 (Woob), T10 (Banking), T11 (IBKR) ✓
- §5.1 table `loan_account_link` → T12 ✓
- §5.2 endpoints candidates / link / ignore / from-account → T13, T14 ✓
- §5.3 `compute_loan_state` étendu → T15 ✓
- §5.4 UI candidats → T16 ✓
- §6 refonte API → T6, T7 ✓
- §7 frontend types → T8 ✓
- §8 tests → distribués par task (chaque normalizer et chaque endpoint a son test) ✓

**Scope** : un seul plan car le module Prêts (auto-detect) dépend du canonical. Si tu veux pauser entre Phase 1 (TR fix) et Phase 2/3, c'est un point de coupe naturel : à la fin de T8 le PEA est fixé, la valo crypto/PE arrive, l'UI s'aligne — déployable.

**Type consistency** : `linked_account_id`, `amount_source`, `LoanCandidate`, `LinkRequest`, `FromAccountRequest` cohérents entre backend (Pydantic), frontend (TS), API (routes). `CanonicalAccount.id` toujours préfixé.
