# Python Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the mm-ledger Python backend (FastAPI + multiprocessing workers + SQLite/SQLCipher) as defined in the architecture spec.

**Architecture:** Single FastAPI process orchestrating isolated connector workers via multiprocessing queues. SQLCipher vault for credentials, SQLite for data. Docker deployment with IB Gateway as separate container.

**Tech Stack:** Python 3.12, FastAPI, uvicorn, SQLAlchemy 2, SQLCipher, APScheduler 3.x, websockets, ib_async, woob, pytesseract

**Spec:** `docs/superpowers/specs/2026-03-24-python-backend-architecture-design.md`
**API Reference:** `docs/api-reference.md`

---

## File Structure

```
mm-ledger/
├── pyproject.toml
├── Dockerfile
├── docker-compose.yml
├── alembic.ini
├── alembic/
│   ├── env.py
│   └── versions/
│       └── 001_initial_schema.py
├── src/
│   ├── __init__.py
│   ├── main.py                      # FastAPI app + lifespan
│   ├── config.py                    # Settings from env
│   ├── vault.py                     # SQLCipher vault
│   ├── manager.py                   # ConnectorManager
│   ├── scheduler.py                 # APScheduler setup
│   ├── db/
│   │   ├── __init__.py
│   │   ├── engine.py                # SQLite engine + WAL
│   │   └── models.py               # SQLAlchemy models
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── vault.py                 # Pydantic: vault requests/responses
│   │   ├── connector.py            # Pydantic: connector CRUD + status
│   │   ├── account.py              # Pydantic: account, balance
│   │   ├── portfolio.py            # Pydantic: position, portfolio
│   │   └── snapshot.py             # Pydantic: snapshot, transaction, perf
│   ├── api/
│   │   ├── __init__.py
│   │   ├── router.py               # Mount all sub-routers
│   │   ├── vault_routes.py         # /api/vault/*
│   │   ├── connectors.py           # /api/connectors/*
│   │   ├── accounts.py             # /api/accounts/*
│   │   ├── portfolio.py            # /api/portfolio/*
│   │   ├── snapshots.py            # /api/snapshots/*
│   │   ├── transactions.py         # /api/transactions/*
│   │   ├── performance.py          # /api/performance/*
│   │   ├── events.py               # /api/events (SSE)
│   │   ├── health.py               # /api/health + /api/scheduler/status
│   │   └── deps.py                 # Shared dependencies (vault, manager, db)
│   └── connectors/
│       ├── __init__.py
│       ├── base.py                  # ConnectorWorker ABC
│       ├── trade_republic.py       # TR worker
│       ├── ibkr.py                 # IBKR worker
│       └── woob_bank.py            # Woob worker
├── tests/
│   ├── conftest.py                  # Fixtures: test db, vault, manager
│   ├── test_vault.py
│   ├── test_db.py
│   ├── test_manager.py
│   ├── test_api_vault.py
│   ├── test_api_connectors.py
│   ├── test_api_data.py
│   └── test_scheduler.py
└── data/                            # Created at runtime, gitignored
```

---

## Task 1: Project scaffolding + dependencies

**Files:**
- Create: `pyproject.toml`
- Create: `src/__init__.py`
- Create: `src/config.py`
- Create: `.gitignore` (update)
- Create: `tests/__init__.py`

- [ ] **Step 1: Create pyproject.toml**

```toml
[project]
name = "mm-ledger"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]",
    "pydantic>=2",
    "sqlalchemy>=2",
    "alembic",
    "sqlcipher3",
    "websockets>=11",
    "requests",
    "selenium",
    "ib_async",
    "woob",
    "pytesseract",
    "Pillow",
    "apscheduler>=3.10,<4",
    "pandas",
    "sse-starlette",
]

[project.optional-dependencies]
dev = [
    "pytest",
    "pytest-asyncio",
    "httpx",
]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.backends._legacy:_Backend"

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 2: Create src/config.py**

```python
from pathlib import Path

DATA_DIR = Path("data")
LEDGER_DB = DATA_DIR / "ledger.db"
VAULT_DB = DATA_DIR / "vault.db"
API_HOST = "0.0.0.0"
API_PORT = 8000
```

- [ ] **Step 3: Create src/__init__.py and tests/__init__.py**

Empty files.

- [ ] **Step 4: Update .gitignore**

Append:
```
data/
__pycache__/
*.pyc
.venv/
```

- [ ] **Step 5: Install dependencies**

Run: `pip install -e ".[dev]"`
Expected: all deps install without errors.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml src/__init__.py src/config.py tests/__init__.py .gitignore
git commit -m "feat: project scaffolding and dependencies"
```

---

## Task 2: SQLite database + models

**Files:**
- Create: `src/db/__init__.py`
- Create: `src/db/engine.py`
- Create: `src/db/models.py`
- Create: `alembic.ini`
- Create: `alembic/env.py`
- Create: `alembic/versions/001_initial_schema.py`
- Create: `tests/test_db.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_db.py
import os
import tempfile
from pathlib import Path

from sqlalchemy import inspect

from src.db.engine import create_engine_and_tables
from src.db.models import connectors, accounts, balance_snapshots, transactions, performance


def test_tables_created():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.db"
        engine = create_engine_and_tables(db_path)
        inspector = inspect(engine)
        table_names = inspector.get_table_names()
        assert "connectors" in table_names
        assert "accounts" in table_names
        assert "balance_snapshots" in table_names
        assert "transactions" in table_names
        assert "performance" in table_names
        engine.dispose()


def test_wal_mode_enabled():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.db"
        engine = create_engine_and_tables(db_path)
        with engine.connect() as conn:
            result = conn.exec_driver_sql("PRAGMA journal_mode")
            mode = result.scalar()
            assert mode == "wal"
        engine.dispose()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_db.py -v`
Expected: FAIL — imports fail.

- [ ] **Step 3: Write src/db/engine.py**

```python
from pathlib import Path

from sqlalchemy import create_engine, event
from src.db.models import metadata


def create_engine_and_tables(db_path: Path):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{db_path}", echo=False)

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    metadata.create_all(engine)
    return engine
```

- [ ] **Step 4: Write src/db/models.py**

```python
from sqlalchemy import (
    MetaData, Table, Column, Integer, Text, Real, JSON,
    ForeignKey, UniqueConstraint, Index
)

metadata = MetaData()

connectors = Table(
    "connectors", metadata,
    Column("id", Text, primary_key=True),
    Column("type", Text, nullable=False),
    Column("label", Text),
    Column("config", JSON),
    Column("created_at", Text, server_default="(datetime('now'))"),
)

accounts = Table(
    "accounts", metadata,
    Column("id", Text, primary_key=True),
    Column("connector_id", Text, ForeignKey("connectors.id"), nullable=False),
    Column("name", Text),
    Column("type", Text),
    Column("currency", Text, server_default="'EUR'"),
    Column("created_at", Text, server_default="(datetime('now'))"),
)

balance_snapshots = Table(
    "balance_snapshots", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("account_id", Text, ForeignKey("accounts.id"), nullable=False),
    Column("date", Text, nullable=False),
    Column("cash", Real),
    Column("positions_value", Real),
    Column("total_value", Real),
    Column("currency", Text, server_default="'EUR'"),
    Column("positions", JSON),
    Column("created_at", Text, server_default="(datetime('now'))"),
    UniqueConstraint("account_id", "date"),
)

transactions = Table(
    "transactions", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("account_id", Text, ForeignKey("accounts.id"), nullable=False),
    Column("date", Text, nullable=False),
    Column("type", Text),
    Column("label", Text),
    Column("amount", Real),
    Column("currency", Text, server_default="'EUR'"),
    Column("instrument", Text),
    Column("quantity", Real),
    Column("price", Real),
    Column("raw", JSON),
    Column("created_at", Text, server_default="(datetime('now'))"),
)

performance = Table(
    "performance", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("connector_id", Text, ForeignKey("connectors.id"), nullable=False),
    Column("period_start", Text, nullable=False),
    Column("period_end", Text, nullable=False),
    Column("total_value", Real),
    Column("total_invested", Real),
    Column("pnl", Real),
    Column("pnl_pct", Real),
    Column("breakdown", JSON),
    UniqueConstraint("connector_id", "period_start"),
)

Index("idx_snapshots_account_date", balance_snapshots.c.account_id, balance_snapshots.c.date)
Index("idx_transactions_account_date", transactions.c.account_id, transactions.c.date)
Index("idx_performance_connector_period", performance.c.connector_id, performance.c.period_start)
```

- [ ] **Step 5: Create src/db/__init__.py**

Empty file.

- [ ] **Step 6: Run tests**

Run: `pytest tests/test_db.py -v`
Expected: 2 PASSED.

- [ ] **Step 7: Commit**

```bash
git add src/db/ tests/test_db.py alembic.ini alembic/
git commit -m "feat: SQLite database engine and models with WAL mode"
```

---

## Task 3: SQLCipher vault

**Files:**
- Create: `src/vault.py`
- Create: `tests/test_vault.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_vault.py
import tempfile
from pathlib import Path

from src.vault import Vault


def test_setup_and_unlock():
    with tempfile.TemporaryDirectory() as tmp:
        v = Vault(Path(tmp) / "vault.db")
        assert v.status == "uninitialized"
        v.setup("testpass")
        assert v.status == "locked"
        assert v.unlock("testpass")
        assert v.status == "unlocked"


def test_wrong_password():
    with tempfile.TemporaryDirectory() as tmp:
        v = Vault(Path(tmp) / "vault.db")
        v.setup("correct")
        assert not v.unlock("wrong")
        assert v.status == "locked"


def test_store_and_retrieve():
    with tempfile.TemporaryDirectory() as tmp:
        v = Vault(Path(tmp) / "vault.db")
        v.setup("pass")
        v.unlock("pass")
        v.store("tr_1", "trade_republic", "My TR", {"phone": "+33612345678", "pin": "1234"})
        creds = v.retrieve("tr_1")
        assert creds["phone"] == "+33612345678"
        assert creds["pin"] == "1234"


def test_delete():
    with tempfile.TemporaryDirectory() as tmp:
        v = Vault(Path(tmp) / "vault.db")
        v.setup("pass")
        v.unlock("pass")
        v.store("tr_1", "trade_republic", "TR", {"phone": "+33"})
        v.delete("tr_1")
        assert v.retrieve("tr_1") is None


def test_list_connectors():
    with tempfile.TemporaryDirectory() as tmp:
        v = Vault(Path(tmp) / "vault.db")
        v.setup("pass")
        v.unlock("pass")
        v.store("tr_1", "trade_republic", "TR", {"phone": "+33"})
        v.store("bp_1", "woob_bank", "BP", {"login": "x"})
        items = v.list_connectors()
        assert len(items) == 2
        # credentials must NOT be in the list
        assert "phone" not in str(items)


def test_lock():
    with tempfile.TemporaryDirectory() as tmp:
        v = Vault(Path(tmp) / "vault.db")
        v.setup("pass")
        v.unlock("pass")
        v.store("tr_1", "trade_republic", "TR", {"phone": "+33"})
        v.lock()
        assert v.status == "locked"
        assert v.retrieve("tr_1") is None  # locked, can't read


def test_change_password():
    with tempfile.TemporaryDirectory() as tmp:
        v = Vault(Path(tmp) / "vault.db")
        v.setup("old")
        v.unlock("old")
        v.store("tr_1", "trade_republic", "TR", {"phone": "+33"})
        v.change_password("old", "new")
        v.lock()
        assert not v.unlock("old")
        assert v.unlock("new")
        assert v.retrieve("tr_1")["phone"] == "+33"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_vault.py -v`
Expected: FAIL — import error.

- [ ] **Step 3: Write src/vault.py**

```python
import json
from pathlib import Path

import sqlcipher3


class Vault:
    def __init__(self, path: Path):
        self._path = path
        self._conn = None

    @property
    def status(self) -> str:
        if self._conn is not None:
            return "unlocked"
        if self._path.exists():
            return "locked"
        return "uninitialized"

    def setup(self, password: str) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlcipher3.connect(str(self._path))
        conn.execute(f"PRAGMA key = '{password}'")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS credentials (
                connector_id TEXT PRIMARY KEY,
                connector_type TEXT NOT NULL,
                label TEXT,
                data TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.commit()
        conn.close()

    def unlock(self, password: str) -> bool:
        try:
            conn = sqlcipher3.connect(str(self._path))
            conn.execute(f"PRAGMA key = '{password}'")
            conn.execute("SELECT count(*) FROM credentials")
            self._conn = conn
            return True
        except Exception:
            return False

    def lock(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def store(self, connector_id: str, connector_type: str, label: str, credentials: dict) -> None:
        if not self._conn:
            return
        self._conn.execute(
            """INSERT INTO credentials (connector_id, connector_type, label, data)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(connector_id) DO UPDATE SET
                 connector_type=excluded.connector_type,
                 label=excluded.label,
                 data=excluded.data,
                 updated_at=datetime('now')""",
            (connector_id, connector_type, label, json.dumps(credentials)),
        )
        self._conn.commit()

    def retrieve(self, connector_id: str) -> dict | None:
        if not self._conn:
            return None
        row = self._conn.execute(
            "SELECT data FROM credentials WHERE connector_id = ?", (connector_id,)
        ).fetchone()
        return json.loads(row[0]) if row else None

    def delete(self, connector_id: str) -> None:
        if not self._conn:
            return
        self._conn.execute("DELETE FROM credentials WHERE connector_id = ?", (connector_id,))
        self._conn.commit()

    def list_connectors(self) -> list[dict]:
        if not self._conn:
            return []
        rows = self._conn.execute(
            "SELECT connector_id, connector_type, label FROM credentials"
        ).fetchall()
        return [{"id": r[0], "type": r[1], "label": r[2]} for r in rows]

    def change_password(self, old_password: str, new_password: str) -> bool:
        if not self._conn:
            return False
        self._conn.execute(f"PRAGMA rekey = '{new_password}'")
        return True
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_vault.py -v`
Expected: 7 PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/vault.py tests/test_vault.py
git commit -m "feat: SQLCipher vault for encrypted credential storage"
```

---

## Task 4: Pydantic schemas

**Files:**
- Create: `src/schemas/__init__.py`
- Create: `src/schemas/vault.py`
- Create: `src/schemas/connector.py`
- Create: `src/schemas/account.py`
- Create: `src/schemas/portfolio.py`
- Create: `src/schemas/snapshot.py`

- [ ] **Step 1: Create all schema files**

`src/schemas/vault.py`:
```python
from pydantic import BaseModel, Field


class PasswordRequest(BaseModel):
    password: str = Field(..., min_length=1, repr=False)

class ChangePasswordRequest(BaseModel):
    old_password: str = Field(..., min_length=1, repr=False)
    new_password: str = Field(..., min_length=1, repr=False)

class VaultStatusResponse(BaseModel):
    state: str  # uninitialized | locked | unlocked

class VaultActionResponse(BaseModel):
    status: str
```

`src/schemas/connector.py`:
```python
from pydantic import BaseModel, Field


class ConnectorCreate(BaseModel):
    id: str
    type: str
    label: str
    credentials: dict = Field(default_factory=dict, repr=False)
    config: dict = Field(default_factory=dict)

class ConnectorUpdate(BaseModel):
    label: str | None = None
    credentials: dict | None = Field(default=None, repr=False)
    config: dict | None = None

class WorkerInfo(BaseModel):
    state: str = "disconnected"
    pid: int | None = None
    uptime_seconds: float | None = None
    last_error: str | None = None
    last_fetch: str | None = None
    accounts_count: int | None = None
    accounts: list[str] | None = None
    detail: str | None = None

class ConnectorResponse(BaseModel):
    id: str
    type: str
    label: str
    config: dict = Field(default_factory=dict)
    worker: WorkerInfo | None = None

class TwoFARequest(BaseModel):
    code: str = Field(..., min_length=1)
```

`src/schemas/account.py`:
```python
from pydantic import BaseModel


class AccountResponse(BaseModel):
    id: str
    connector_id: str
    name: str | None = None
    type: str | None = None
    currency: str = "EUR"

class BalanceResponse(BaseModel):
    account_id: str
    cash: float | None = None
    positions_value: float | None = None
    total_value: float | None = None
    currency: str = "EUR"
    updated_at: str | None = None
```

`src/schemas/portfolio.py`:
```python
from pydantic import BaseModel


class PositionResponse(BaseModel):
    connector_id: str
    account_id: str
    instrument: str | None = None
    name: str | None = None
    symbol: str | None = None
    category: str | None = None
    quantity: float = 0
    avg_price: float = 0
    current_price: float = 0
    value: float = 0
    pnl: float = 0
    pnl_pct: float = 0
    currency: str = "EUR"

class PortfolioResponse(BaseModel):
    total_value: float = 0
    total_invested: float = 0
    total_pnl: float = 0
    total_pnl_pct: float = 0
    currency: str = "EUR"
    positions: list[PositionResponse] = []
```

`src/schemas/snapshot.py`:
```python
from pydantic import BaseModel


class SnapshotResponse(BaseModel):
    account_id: str
    date: str
    cash: float | None = None
    positions_value: float | None = None
    total_value: float | None = None
    currency: str = "EUR"
    positions: list[dict] | None = None

class TransactionResponse(BaseModel):
    id: int
    account_id: str
    date: str
    type: str | None = None
    label: str | None = None
    amount: float | None = None
    currency: str = "EUR"
    instrument: str | None = None
    quantity: float | None = None
    price: float | None = None

class PerformanceResponse(BaseModel):
    connector_id: str
    period_start: str
    period_end: str
    total_value: float | None = None
    total_invested: float | None = None
    pnl: float | None = None
    pnl_pct: float | None = None
    breakdown: dict | None = None

class TriggerResponse(BaseModel):
    triggered: list[str] | str
    skipped: list[str] | None = None
    reason_skipped: dict | None = None
```

- [ ] **Step 2: Create src/schemas/__init__.py**

Empty file.

- [ ] **Step 3: Verify imports**

Run: `python -c "from src.schemas.vault import *; from src.schemas.connector import *; from src.schemas.account import *; from src.schemas.portfolio import *; from src.schemas.snapshot import *; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add src/schemas/
git commit -m "feat: Pydantic schemas for all API request/response types"
```

---

## Task 5: ConnectorWorker base class + ConnectorManager

**Files:**
- Create: `src/connectors/__init__.py`
- Create: `src/connectors/base.py`
- Create: `src/manager.py`
- Create: `tests/test_manager.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_manager.py
import time
from multiprocessing import Queue

from src.connectors.base import ConnectorWorker
from src.manager import ConnectorManager


class FakeWorker(ConnectorWorker):
    def connect(self, credentials: dict):
        self.event_queue.put({"type": "status", "state": "connected"})

    def disconnect(self):
        pass

    def fetch_accounts(self) -> list[dict]:
        return [{"id": "acc_1", "name": "Test"}]

    def fetch_positions(self) -> list[dict]:
        return []

    def fetch_balances(self) -> list[dict]:
        return [{"account_id": "acc_1", "cash": 100.0}]

    def fetch_transactions(self) -> list[dict]:
        return []

    def submit_2fa(self, code: str):
        pass


def test_spawn_and_stop():
    mgr = ConnectorManager()
    mgr.register_worker_class("fake", FakeWorker)
    mgr.spawn("test_1", "fake", {"token": "abc"})
    time.sleep(0.5)
    status = mgr.get_status("test_1")
    assert status["state"] == "connected"
    mgr.stop("test_1")
    time.sleep(0.3)
    status = mgr.get_status("test_1")
    assert status["state"] == "disconnected"


def test_send_command_and_collect():
    mgr = ConnectorManager()
    mgr.register_worker_class("fake", FakeWorker)
    mgr.spawn("test_1", "fake", {"token": "abc"})
    time.sleep(0.5)
    mgr.send_command("test_1", {"type": "fetch_accounts"})
    time.sleep(0.5)
    events = mgr.collect_events()
    account_events = [e for e in events if e.get("type") == "accounts"]
    assert len(account_events) >= 1
    assert account_events[0]["data"][0]["id"] == "acc_1"
    mgr.stop("test_1")


def test_health_check():
    mgr = ConnectorManager()
    mgr.register_worker_class("fake", FakeWorker)
    mgr.spawn("test_1", "fake", {})
    time.sleep(0.5)
    health = mgr.health_check()
    assert "test_1" in health
    assert health["test_1"] == "connected"
    mgr.stop_all()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_manager.py -v`
Expected: FAIL.

- [ ] **Step 3: Write src/connectors/base.py**

```python
from abc import ABC, abstractmethod
from multiprocessing import Queue


class ConnectorWorker(ABC):
    def __init__(self, cmd_queue: Queue, event_queue: Queue, config: dict):
        self.cmd_queue = cmd_queue
        self.event_queue = event_queue
        self.config = config

    @abstractmethod
    def connect(self, credentials: dict) -> None: ...

    @abstractmethod
    def disconnect(self) -> None: ...

    @abstractmethod
    def fetch_accounts(self) -> list[dict]: ...

    @abstractmethod
    def fetch_positions(self) -> list[dict]: ...

    @abstractmethod
    def fetch_balances(self) -> list[dict]: ...

    @abstractmethod
    def fetch_transactions(self) -> list[dict]: ...

    @abstractmethod
    def submit_2fa(self, code: str) -> None: ...

    def run(self):
        while True:
            cmd = self.cmd_queue.get()
            if cmd["type"] == "shutdown":
                self.disconnect()
                self.event_queue.put({"type": "status", "state": "disconnected"})
                break
            try:
                handler = {
                    "connect": lambda: self.connect(cmd.get("credentials", {})),
                    "disconnect": self.disconnect,
                    "fetch_accounts": self.fetch_accounts,
                    "fetch_positions": self.fetch_positions,
                    "fetch_balances": self.fetch_balances,
                    "fetch_transactions": self.fetch_transactions,
                    "submit_2fa": lambda: self.submit_2fa(cmd["code"]),
                }[cmd["type"]]
                data = handler()
                if data is not None:
                    event_type = cmd["type"].replace("fetch_", "")
                    self.event_queue.put({"type": event_type, "data": data})
            except Exception as e:
                self.event_queue.put({"type": "error", "message": str(e)})
```

- [ ] **Step 4: Write src/manager.py**

```python
import time
from dataclasses import dataclass, field
from multiprocessing import Process, Queue


@dataclass
class WorkerHandle:
    process: Process
    cmd_queue: Queue
    event_queue: Queue
    state: str = "connecting"
    detail: str | None = None
    started_at: float = field(default_factory=time.time)


class ConnectorManager:
    def __init__(self):
        self._workers: dict[str, WorkerHandle] = {}
        self._worker_classes: dict[str, type] = {}

    def register_worker_class(self, connector_type: str, cls: type):
        self._worker_classes[connector_type] = cls

    def spawn(self, connector_id: str, connector_type: str, credentials: dict):
        if connector_id in self._workers:
            self.stop(connector_id)

        cmd_q = Queue()
        event_q = Queue()
        cls = self._worker_classes[connector_type]

        def target():
            worker = cls(cmd_q, event_q, {})
            worker.run()

        proc = Process(target=target, daemon=True)
        proc.start()
        handle = WorkerHandle(process=proc, cmd_queue=cmd_q, event_queue=event_q)
        self._workers[connector_id] = handle
        cmd_q.put({"type": "connect", "credentials": credentials})

    def stop(self, connector_id: str):
        handle = self._workers.get(connector_id)
        if not handle:
            return
        handle.cmd_queue.put({"type": "shutdown"})
        handle.process.join(timeout=5)
        if handle.process.is_alive():
            handle.process.terminate()
        handle.state = "disconnected"

    def stop_all(self):
        for cid in list(self._workers):
            self.stop(cid)

    def send_command(self, connector_id: str, cmd: dict):
        handle = self._workers.get(connector_id)
        if handle and handle.process.is_alive():
            handle.cmd_queue.put(cmd)

    def collect_events(self) -> list[dict]:
        events = []
        for handle in self._workers.values():
            while not handle.event_queue.empty():
                try:
                    event = handle.event_queue.get_nowait()
                    if event.get("type") == "status":
                        handle.state = event.get("state", handle.state)
                        handle.detail = event.get("detail")
                    events.append(event)
                except Exception:
                    break
        return events

    def get_status(self, connector_id: str) -> dict:
        handle = self._workers.get(connector_id)
        if not handle:
            return {"state": "disconnected"}
        self.collect_events()  # drain to update state
        return {
            "state": handle.state,
            "pid": handle.process.pid if handle.process.is_alive() else None,
            "uptime_seconds": time.time() - handle.started_at if handle.process.is_alive() else None,
            "detail": handle.detail,
        }

    def health_check(self) -> dict[str, str]:
        self.collect_events()
        return {cid: h.state for cid, h in self._workers.items()}
```

- [ ] **Step 5: Create src/connectors/__init__.py**

Empty file.

- [ ] **Step 6: Run tests**

Run: `pytest tests/test_manager.py -v`
Expected: 3 PASSED.

- [ ] **Step 7: Commit**

```bash
git add src/connectors/ src/manager.py tests/test_manager.py
git commit -m "feat: ConnectorWorker base class and ConnectorManager"
```

---

## Task 6: FastAPI app + vault routes

**Files:**
- Create: `src/main.py`
- Create: `src/api/__init__.py`
- Create: `src/api/deps.py`
- Create: `src/api/router.py`
- Create: `src/api/vault_routes.py`
- Create: `tests/conftest.py`
- Create: `tests/test_api_vault.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/conftest.py
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.main import create_app


@pytest.fixture
def tmp_data(tmp_path):
    return tmp_path


@pytest.fixture
def client(tmp_data):
    app = create_app(data_dir=tmp_data)
    with TestClient(app) as c:
        yield c
```

```python
# tests/test_api_vault.py

def test_vault_status_uninitialized(client):
    r = client.get("/api/vault/status")
    assert r.status_code == 200
    assert r.json()["state"] == "uninitialized"


def test_vault_setup(client):
    r = client.post("/api/vault/setup", json={"password": "test"})
    assert r.status_code == 201
    r = client.get("/api/vault/status")
    assert r.json()["state"] == "locked"


def test_vault_setup_duplicate(client):
    client.post("/api/vault/setup", json={"password": "test"})
    r = client.post("/api/vault/setup", json={"password": "test2"})
    assert r.status_code == 409


def test_vault_unlock(client):
    client.post("/api/vault/setup", json={"password": "test"})
    r = client.post("/api/vault/unlock", json={"password": "test"})
    assert r.status_code == 200
    assert r.json()["status"] == "unlocked"


def test_vault_unlock_wrong_password(client):
    client.post("/api/vault/setup", json={"password": "test"})
    r = client.post("/api/vault/unlock", json={"password": "wrong"})
    assert r.status_code == 401


def test_vault_lock(client):
    client.post("/api/vault/setup", json={"password": "test"})
    client.post("/api/vault/unlock", json={"password": "test"})
    r = client.post("/api/vault/lock")
    assert r.status_code == 200
    r = client.get("/api/vault/status")
    assert r.json()["state"] == "locked"


def test_vault_change_password(client):
    client.post("/api/vault/setup", json={"password": "old"})
    client.post("/api/vault/unlock", json={"password": "old"})
    r = client.post("/api/vault/change-password", json={"old_password": "old", "new_password": "new"})
    assert r.status_code == 200
    client.post("/api/vault/lock")
    r = client.post("/api/vault/unlock", json={"password": "new"})
    assert r.status_code == 200
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_api_vault.py -v`
Expected: FAIL.

- [ ] **Step 3: Write src/api/deps.py**

```python
from src.vault import Vault
from src.manager import ConnectorManager

vault: Vault | None = None
manager: ConnectorManager | None = None
db_engine = None
```

- [ ] **Step 4: Write src/api/vault_routes.py**

```python
from fastapi import APIRouter, HTTPException

from src.api import deps
from src.schemas.vault import PasswordRequest, ChangePasswordRequest, VaultStatusResponse, VaultActionResponse

router = APIRouter(prefix="/api/vault", tags=["vault"])


@router.get("/status", response_model=VaultStatusResponse)
def vault_status():
    return {"state": deps.vault.status}


@router.post("/setup", response_model=VaultActionResponse, status_code=201)
def vault_setup(req: PasswordRequest):
    if deps.vault.status != "uninitialized":
        raise HTTPException(409, "Vault already initialized. Use POST /api/vault/unlock.")
    deps.vault.setup(req.password)
    return {"status": "created"}


@router.post("/unlock", response_model=VaultActionResponse)
def vault_unlock(req: PasswordRequest):
    if deps.vault.unlock(req.password):
        return {"status": "unlocked"}
    raise HTTPException(401, "Wrong password.")


@router.post("/lock", response_model=VaultActionResponse)
def vault_lock():
    deps.vault.lock()
    return {"status": "locked"}


@router.post("/change-password", response_model=VaultActionResponse)
def vault_change_password(req: ChangePasswordRequest):
    if deps.vault.status != "unlocked":
        raise HTTPException(423, "Vault is locked.")
    if not deps.vault.change_password(req.old_password, req.new_password):
        raise HTTPException(401, "Wrong old password.")
    return {"status": "changed"}
```

- [ ] **Step 5: Write src/api/router.py**

```python
from fastapi import APIRouter
from src.api.vault_routes import router as vault_router

api_router = APIRouter()
api_router.include_router(vault_router)
```

- [ ] **Step 6: Write src/main.py**

```python
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from src.api import deps
from src.api.router import api_router
from src.config import DATA_DIR, VAULT_DB, LEDGER_DB
from src.db.engine import create_engine_and_tables
from src.manager import ConnectorManager
from src.vault import Vault


def create_app(data_dir: Path | None = None) -> FastAPI:
    data = data_dir or DATA_DIR

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        deps.vault = Vault(data / "vault.db")
        deps.db_engine = create_engine_and_tables(data / "ledger.db")
        deps.manager = ConnectorManager()
        yield
        deps.manager.stop_all()
        deps.vault.lock()
        if deps.db_engine:
            deps.db_engine.dispose()

    app = FastAPI(lifespan=lifespan)
    app.include_router(api_router)
    return app


app = create_app()
```

- [ ] **Step 7: Create src/api/__init__.py**

Empty file.

- [ ] **Step 8: Run tests**

Run: `pytest tests/test_api_vault.py -v`
Expected: 7 PASSED.

- [ ] **Step 9: Commit**

```bash
git add src/main.py src/api/ tests/conftest.py tests/test_api_vault.py
git commit -m "feat: FastAPI app with vault routes (setup/unlock/lock/change-password)"
```

---

## Task 7: Connector CRUD + worker lifecycle routes

**Files:**
- Create: `src/api/connectors.py`
- Modify: `src/api/router.py`
- Create: `tests/test_api_connectors.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_api_connectors.py

def _setup_vault(client):
    client.post("/api/vault/setup", json={"password": "test"})
    client.post("/api/vault/unlock", json={"password": "test"})


def test_create_connector(client):
    _setup_vault(client)
    r = client.post("/api/connectors", json={
        "id": "tr_1", "type": "trade_republic", "label": "TR",
        "credentials": {"phone": "+33", "pin": "1234"}, "config": {}
    })
    assert r.status_code == 201
    assert r.json()["id"] == "tr_1"


def test_create_connector_vault_locked(client):
    r = client.post("/api/connectors", json={
        "id": "tr_1", "type": "trade_republic", "label": "TR",
        "credentials": {}, "config": {}
    })
    assert r.status_code == 423


def test_list_connectors(client):
    _setup_vault(client)
    client.post("/api/connectors", json={
        "id": "tr_1", "type": "trade_republic", "label": "TR",
        "credentials": {"phone": "+33"}, "config": {}
    })
    r = client.get("/api/connectors")
    assert r.status_code == 200
    assert len(r.json()) == 1
    assert r.json()[0]["id"] == "tr_1"
    assert "credentials" not in str(r.json())


def test_update_connector(client):
    _setup_vault(client)
    client.post("/api/connectors", json={
        "id": "tr_1", "type": "trade_republic", "label": "TR",
        "credentials": {"phone": "+33"}, "config": {}
    })
    r = client.put("/api/connectors/tr_1", json={"label": "TR Updated"})
    assert r.status_code == 200
    assert r.json()["label"] == "TR Updated"


def test_delete_connector(client):
    _setup_vault(client)
    client.post("/api/connectors", json={
        "id": "tr_1", "type": "trade_republic", "label": "TR",
        "credentials": {"phone": "+33"}, "config": {}
    })
    r = client.delete("/api/connectors/tr_1")
    assert r.status_code == 204
    r = client.get("/api/connectors")
    assert len(r.json()) == 0


def test_get_connector_types(client):
    r = client.get("/api/connectors/types")
    assert r.status_code == 200
    types = {t["type"] for t in r.json()}
    assert "trade_republic" in types
    assert "ibkr" in types
    assert "woob_bank" in types
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_api_connectors.py -v`

- [ ] **Step 3: Write src/api/connectors.py**

```python
from fastapi import APIRouter, HTTPException
from sqlalchemy import insert, select, update, delete

from src.api import deps
from src.db.models import connectors
from src.schemas.connector import (
    ConnectorCreate, ConnectorUpdate, ConnectorResponse, WorkerInfo, TwoFARequest,
)

router = APIRouter(prefix="/api/connectors", tags=["connectors"])

CONNECTOR_TYPES = [
    {
        "type": "trade_republic", "label": "Trade Republic",
        "credential_fields": [
            {"name": "phone", "type": "text", "required": True, "placeholder": "+33612345678"},
            {"name": "pin", "type": "password", "required": True, "placeholder": "1234"},
        ],
        "config_fields": [], "supports_2fa": True, "supports_streaming": True,
    },
    {
        "type": "ibkr", "label": "Interactive Brokers",
        "credential_fields": [],
        "config_fields": [
            {"name": "host", "type": "text", "required": True, "default": "127.0.0.1"},
            {"name": "port", "type": "number", "required": True, "default": 4001},
        ],
        "supports_2fa": False, "supports_streaming": True,
    },
    {
        "type": "woob_bank", "label": "Banque (Woob)",
        "credential_fields": [
            {"name": "login", "type": "text", "required": True},
            {"name": "password", "type": "password", "required": True},
            {"name": "bank_module", "type": "text", "required": True, "default": "banquepopulaire"},
            {"name": "region", "type": "text", "required": False, "placeholder": "10207"},
        ],
        "config_fields": [], "supports_2fa": True, "supports_streaming": False,
    },
]


def _require_vault():
    if deps.vault.status != "unlocked":
        raise HTTPException(423, "Vault is locked. POST /api/vault/unlock first.")


@router.get("/types")
def get_connector_types():
    return CONNECTOR_TYPES


@router.get("", response_model=list[ConnectorResponse])
def list_connectors():
    with deps.db_engine.connect() as conn:
        rows = conn.execute(select(connectors)).fetchall()
    result = []
    for row in rows:
        worker_status = deps.manager.get_status(row.id)
        result.append(ConnectorResponse(
            id=row.id, type=row.type, label=row.label, config=row.config or {},
            worker=WorkerInfo(**worker_status),
        ))
    return result


@router.post("", response_model=ConnectorResponse, status_code=201)
def create_connector(req: ConnectorCreate):
    _require_vault()
    with deps.db_engine.begin() as conn:
        conn.execute(insert(connectors).values(
            id=req.id, type=req.type, label=req.label, config=req.config,
        ))
    deps.vault.store(req.id, req.type, req.label, req.credentials)
    return ConnectorResponse(id=req.id, type=req.type, label=req.label, config=req.config)


@router.put("/{connector_id}", response_model=ConnectorResponse)
def update_connector(connector_id: str, req: ConnectorUpdate):
    _require_vault()
    updates = {}
    if req.label is not None:
        updates["label"] = req.label
    if req.config is not None:
        updates["config"] = req.config
    if updates:
        with deps.db_engine.begin() as conn:
            conn.execute(update(connectors).where(connectors.c.id == connector_id).values(**updates))
    if req.credentials is not None:
        existing = deps.vault.retrieve(connector_id)
        if existing is None:
            raise HTTPException(404, "Connector not found in vault.")
        # Re-read to get current type/label
        with deps.db_engine.connect() as conn:
            row = conn.execute(select(connectors).where(connectors.c.id == connector_id)).fetchone()
        if not row:
            raise HTTPException(404, "Connector not found.")
        deps.vault.store(connector_id, row.type, req.label or row.label, req.credentials)
    with deps.db_engine.connect() as conn:
        row = conn.execute(select(connectors).where(connectors.c.id == connector_id)).fetchone()
    if not row:
        raise HTTPException(404, "Connector not found.")
    return ConnectorResponse(id=row.id, type=row.type, label=row.label, config=row.config or {})


@router.delete("/{connector_id}", status_code=204)
def delete_connector(connector_id: str):
    deps.manager.stop(connector_id)
    deps.vault.delete(connector_id)
    with deps.db_engine.begin() as conn:
        conn.execute(delete(connectors).where(connectors.c.id == connector_id))


@router.get("/{connector_id}/status")
def get_connector_status(connector_id: str):
    return {"id": connector_id, **deps.manager.get_status(connector_id)}


@router.post("/{connector_id}/connect", status_code=202)
def connect_connector(connector_id: str):
    _require_vault()
    creds = deps.vault.retrieve(connector_id)
    if creds is None:
        raise HTTPException(404, "Connector not found.")
    with deps.db_engine.connect() as conn:
        row = conn.execute(select(connectors).where(connectors.c.id == connector_id)).fetchone()
    if not row:
        raise HTTPException(404, "Connector not found.")
    deps.manager.spawn(connector_id, row.type, creds)
    return {"status": "connecting"}


@router.post("/{connector_id}/disconnect")
def disconnect_connector(connector_id: str):
    deps.manager.stop(connector_id)
    return {"status": "disconnected"}


@router.post("/{connector_id}/restart", status_code=202)
def restart_connector(connector_id: str):
    _require_vault()
    deps.manager.stop(connector_id)
    creds = deps.vault.retrieve(connector_id)
    if creds is None:
        raise HTTPException(404, "Connector not found.")
    with deps.db_engine.connect() as conn:
        row = conn.execute(select(connectors).where(connectors.c.id == connector_id)).fetchone()
    deps.manager.spawn(connector_id, row.type, creds)
    return {"status": "connecting"}


@router.post("/{connector_id}/2fa")
def submit_2fa(connector_id: str, req: TwoFARequest):
    status = deps.manager.get_status(connector_id)
    if status["state"] != "waiting_2fa":
        raise HTTPException(409, f"Worker is not in waiting_2fa state. Current state: {status['state']}")
    deps.manager.send_command(connector_id, {"type": "submit_2fa", "code": req.code})
    return {"status": "submitted"}
```

- [ ] **Step 4: Update src/api/router.py to include connector routes**

```python
from fastapi import APIRouter
from src.api.vault_routes import router as vault_router
from src.api.connectors import router as connectors_router

api_router = APIRouter()
api_router.include_router(vault_router)
api_router.include_router(connectors_router)
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_api_connectors.py -v`
Expected: 6 PASSED.

- [ ] **Step 6: Commit**

```bash
git add src/api/connectors.py src/api/router.py tests/test_api_connectors.py
git commit -m "feat: connector CRUD, worker lifecycle, and 2FA routes"
```

---

## Task 8: Data routes (accounts, portfolio, snapshots, transactions, performance)

**Files:**
- Create: `src/api/accounts.py`
- Create: `src/api/portfolio.py`
- Create: `src/api/snapshots.py`
- Create: `src/api/transactions.py`
- Create: `src/api/performance.py`
- Modify: `src/api/router.py`
- Create: `tests/test_api_data.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_api_data.py
from sqlalchemy import insert
from src.db.models import connectors, accounts, balance_snapshots, transactions, performance
from src.api import deps


def _seed(client):
    client.post("/api/vault/setup", json={"password": "test"})
    client.post("/api/vault/unlock", json={"password": "test"})
    with deps.db_engine.begin() as conn:
        conn.execute(insert(connectors).values(id="tr_1", type="trade_republic", label="TR"))
        conn.execute(insert(accounts).values(id="tr_CTO", connector_id="tr_1", name="CTO", type="cto"))
        conn.execute(insert(balance_snapshots).values(
            account_id="tr_CTO", date="2026-03-23", cash=100, positions_value=900, total_value=1000,
            positions=[{"symbol": "IWDA", "qty": 10, "price": 90, "value": 900}],
        ))
        conn.execute(insert(transactions).values(
            account_id="tr_CTO", date="2026-03-20", type="buy",
            label="IWDA", amount=-900, instrument="IE00B4L5Y983", quantity=10, price=90,
        ))
        conn.execute(insert(performance).values(
            connector_id="tr_1", period_start="2026-03-17", period_end="2026-03-23",
            total_value=1000, total_invested=900, pnl=100, pnl_pct=11.11,
        ))


def test_list_accounts(client):
    _seed(client)
    r = client.get("/api/accounts")
    assert r.status_code == 200
    assert len(r.json()) == 1
    assert r.json()[0]["id"] == "tr_CTO"


def test_get_snapshots(client):
    _seed(client)
    r = client.get("/api/snapshots?from=2026-03-01&to=2026-03-31")
    assert r.status_code == 200
    assert len(r.json()) == 1
    assert r.json()[0]["total_value"] == 1000


def test_get_transactions(client):
    _seed(client)
    r = client.get("/api/transactions?from=2026-03-01&to=2026-03-31")
    assert r.status_code == 200
    assert len(r.json()) == 1
    assert r.json()[0]["type"] == "buy"


def test_get_performance(client):
    _seed(client)
    r = client.get("/api/performance?from=2026-03-01&to=2026-03-31")
    assert r.status_code == 200
    assert len(r.json()) == 1
    assert r.json()[0]["pnl"] == 100
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_api_data.py -v`

- [ ] **Step 3: Write all data route files**

`src/api/accounts.py`:
```python
from fastapi import APIRouter
from sqlalchemy import select

from src.api import deps
from src.db.models import accounts
from src.schemas.account import AccountResponse

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


@router.get("", response_model=list[AccountResponse])
def list_accounts(connector_id: str | None = None):
    stmt = select(accounts)
    if connector_id:
        stmt = stmt.where(accounts.c.connector_id == connector_id)
    with deps.db_engine.connect() as conn:
        rows = conn.execute(stmt).fetchall()
    return [AccountResponse(id=r.id, connector_id=r.connector_id, name=r.name, type=r.type, currency=r.currency) for r in rows]


@router.get("/{account_id}/balance")
def get_balance(account_id: str):
    # Return latest snapshot as current balance
    from src.db.models import balance_snapshots
    stmt = select(balance_snapshots).where(
        balance_snapshots.c.account_id == account_id
    ).order_by(balance_snapshots.c.date.desc()).limit(1)
    with deps.db_engine.connect() as conn:
        row = conn.execute(stmt).fetchone()
    if not row:
        return {"account_id": account_id, "cash": None, "positions_value": None, "total_value": None}
    return {
        "account_id": account_id, "cash": row.cash,
        "positions_value": row.positions_value, "total_value": row.total_value,
        "currency": row.currency, "updated_at": row.created_at,
    }
```

`src/api/snapshots.py`:
```python
from datetime import date, timedelta

from fastapi import APIRouter, Response
from sqlalchemy import select, func

from src.api import deps
from src.db.models import balance_snapshots

router = APIRouter(prefix="/api/snapshots", tags=["snapshots"])


@router.get("")
def list_snapshots(
    response: Response,
    account_id: str | None = None,
    limit: int = 100, offset: int = 0,
    **kwargs,
):
    # Accept from/to as query params via request
    from fastapi import Request
    # Simpler: use default params
    frm = kwargs.get("from") or (date.today() - timedelta(days=30)).isoformat()
    to = kwargs.get("to") or date.today().isoformat()

    stmt = select(balance_snapshots).where(
        balance_snapshots.c.date >= frm,
        balance_snapshots.c.date <= to,
    )
    count_stmt = select(func.count()).select_from(balance_snapshots).where(
        balance_snapshots.c.date >= frm,
        balance_snapshots.c.date <= to,
    )
    if account_id:
        stmt = stmt.where(balance_snapshots.c.account_id == account_id)
        count_stmt = count_stmt.where(balance_snapshots.c.account_id == account_id)

    stmt = stmt.order_by(balance_snapshots.c.date).limit(limit).offset(offset)

    with deps.db_engine.connect() as conn:
        total = conn.execute(count_stmt).scalar()
        rows = conn.execute(stmt).fetchall()

    response.headers["X-Total-Count"] = str(total)
    return [
        {
            "account_id": r.account_id, "date": r.date,
            "cash": r.cash, "positions_value": r.positions_value,
            "total_value": r.total_value, "currency": r.currency,
            "positions": r.positions,
        }
        for r in rows
    ]
```

`src/api/transactions.py`:
```python
from datetime import date, timedelta

from fastapi import APIRouter, Query, Response
from sqlalchemy import select, func

from src.api import deps
from src.db.models import transactions

router = APIRouter(prefix="/api/transactions", tags=["transactions"])


@router.get("")
def list_transactions(
    response: Response,
    account_id: str | None = None,
    type: str | None = None,
    limit: int = 100, offset: int = 0,
    frm: str = Query(None, alias="from"),
    to: str = None,
):
    frm = frm or (date.today() - timedelta(days=30)).isoformat()
    to = to or date.today().isoformat()

    filters = [transactions.c.date >= frm, transactions.c.date <= to]
    if account_id:
        filters.append(transactions.c.account_id == account_id)
    if type:
        filters.append(transactions.c.type == type)

    stmt = select(transactions).where(*filters).order_by(transactions.c.date.desc()).limit(limit).offset(offset)
    count_stmt = select(func.count()).select_from(transactions).where(*filters)

    with deps.db_engine.connect() as conn:
        total = conn.execute(count_stmt).scalar()
        rows = conn.execute(stmt).fetchall()

    response.headers["X-Total-Count"] = str(total)
    return [
        {
            "id": r.id, "account_id": r.account_id, "date": r.date,
            "type": r.type, "label": r.label, "amount": r.amount,
            "currency": r.currency, "instrument": r.instrument,
            "quantity": r.quantity, "price": r.price,
        }
        for r in rows
    ]
```

`src/api/performance.py`:
```python
from datetime import date, timedelta

from fastapi import APIRouter, Query, Response
from sqlalchemy import select, func

from src.api import deps
from src.db.models import performance

router = APIRouter(prefix="/api/performance", tags=["performance"])


@router.get("")
def list_performance(
    response: Response,
    connector_id: str | None = None,
    limit: int = 100, offset: int = 0,
    frm: str = Query(None, alias="from"),
    to: str = None,
):
    frm = frm or (date.today() - timedelta(days=30)).isoformat()
    to = to or date.today().isoformat()

    filters = [performance.c.period_start >= frm, performance.c.period_start <= to]
    if connector_id:
        filters.append(performance.c.connector_id == connector_id)

    stmt = select(performance).where(*filters).order_by(performance.c.period_start).limit(limit).offset(offset)
    count_stmt = select(func.count()).select_from(performance).where(*filters)

    with deps.db_engine.connect() as conn:
        total = conn.execute(count_stmt).scalar()
        rows = conn.execute(stmt).fetchall()

    response.headers["X-Total-Count"] = str(total)
    return [
        {
            "connector_id": r.connector_id,
            "period_start": r.period_start, "period_end": r.period_end,
            "total_value": r.total_value, "total_invested": r.total_invested,
            "pnl": r.pnl, "pnl_pct": r.pnl_pct, "breakdown": r.breakdown,
        }
        for r in rows
    ]
```

`src/api/portfolio.py`:
```python
from fastapi import APIRouter

from src.schemas.portfolio import PortfolioResponse

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


@router.get("", response_model=PortfolioResponse)
def get_portfolio(connector_id: str | None = None):
    # Portfolio is computed from live worker data
    # For now return empty — will be populated when connectors push data
    return PortfolioResponse()


@router.get("/{connector_id}", response_model=PortfolioResponse)
def get_portfolio_by_connector(connector_id: str):
    return PortfolioResponse()
```

- [ ] **Step 4: Fix snapshots route — use Query alias for `from`**

Replace the snapshots route to use proper Query params:

```python
# src/api/snapshots.py
from datetime import date, timedelta

from fastapi import APIRouter, Query, Response
from sqlalchemy import select, func

from src.api import deps
from src.db.models import balance_snapshots

router = APIRouter(prefix="/api/snapshots", tags=["snapshots"])


@router.get("")
def list_snapshots(
    response: Response,
    account_id: str | None = None,
    limit: int = 100, offset: int = 0,
    frm: str = Query(None, alias="from"),
    to: str = None,
):
    frm = frm or (date.today() - timedelta(days=30)).isoformat()
    to = to or date.today().isoformat()

    filters = [balance_snapshots.c.date >= frm, balance_snapshots.c.date <= to]
    if account_id:
        filters.append(balance_snapshots.c.account_id == account_id)

    stmt = select(balance_snapshots).where(*filters).order_by(balance_snapshots.c.date).limit(limit).offset(offset)
    count_stmt = select(func.count()).select_from(balance_snapshots).where(*filters)

    with deps.db_engine.connect() as conn:
        total = conn.execute(count_stmt).scalar()
        rows = conn.execute(stmt).fetchall()

    response.headers["X-Total-Count"] = str(total)
    return [
        {
            "account_id": r.account_id, "date": r.date,
            "cash": r.cash, "positions_value": r.positions_value,
            "total_value": r.total_value, "currency": r.currency,
            "positions": r.positions,
        }
        for r in rows
    ]
```

- [ ] **Step 5: Update src/api/router.py**

```python
from fastapi import APIRouter
from src.api.vault_routes import router as vault_router
from src.api.connectors import router as connectors_router
from src.api.accounts import router as accounts_router
from src.api.portfolio import router as portfolio_router
from src.api.snapshots import router as snapshots_router
from src.api.transactions import router as transactions_router
from src.api.performance import router as performance_router

api_router = APIRouter()
api_router.include_router(vault_router)
api_router.include_router(connectors_router)
api_router.include_router(accounts_router)
api_router.include_router(portfolio_router)
api_router.include_router(snapshots_router)
api_router.include_router(transactions_router)
api_router.include_router(performance_router)
```

- [ ] **Step 6: Run tests**

Run: `pytest tests/test_api_data.py -v`
Expected: 4 PASSED.

- [ ] **Step 7: Commit**

```bash
git add src/api/accounts.py src/api/portfolio.py src/api/snapshots.py src/api/transactions.py src/api/performance.py src/api/router.py tests/test_api_data.py
git commit -m "feat: data routes (accounts, portfolio, snapshots, transactions, performance)"
```

---

## Task 9: SSE events + health endpoints

**Files:**
- Create: `src/api/events.py`
- Create: `src/api/health.py`
- Modify: `src/api/router.py`

- [ ] **Step 1: Write src/api/events.py**

```python
import asyncio
import json

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from src.api import deps

router = APIRouter(tags=["events"])


async def event_generator():
    while True:
        events = deps.manager.collect_events()
        for event in events:
            event_type = event.get("type", "error")
            if event_type == "status":
                event_type = "worker_status"
            yield {"event": event_type, "data": json.dumps(event)}
        await asyncio.sleep(0.1)


@router.get("/api/events")
async def sse_events():
    return EventSourceResponse(event_generator())
```

- [ ] **Step 2: Write src/api/health.py**

```python
import time

from fastapi import APIRouter

from src.api import deps

router = APIRouter(tags=["system"])

_start_time = time.time()


@router.get("/api/health")
def health():
    workers = deps.manager.health_check() if deps.manager else {}
    db_ok = "ok"
    try:
        with deps.db_engine.connect() as conn:
            conn.exec_driver_sql("SELECT 1")
    except Exception:
        db_ok = "error"
    return {
        "status": "ok" if db_ok == "ok" else "degraded",
        "vault": deps.vault.status if deps.vault else "uninitialized",
        "scheduler": "running",
        "workers": workers,
        "db": db_ok,
        "uptime_seconds": int(time.time() - _start_time),
    }


@router.get("/api/scheduler/status")
def scheduler_status():
    return {"jobs": []}  # Will be populated in Task 10
```

- [ ] **Step 3: Update src/api/router.py — add events + health**

Add imports and include_router for events and health.

- [ ] **Step 4: Verify health endpoint works**

Run: `pytest -k "test_" tests/ -v` (run all existing tests to make sure nothing broke)
Expected: all PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/api/events.py src/api/health.py src/api/router.py
git commit -m "feat: SSE event stream and health/scheduler endpoints"
```

---

## Task 10: APScheduler integration

**Files:**
- Create: `src/scheduler.py`
- Modify: `src/main.py`
- Create: `tests/test_scheduler.py`

- [ ] **Step 1: Write src/scheduler.py**

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import insert

from src.api import deps
from src.db.models import balance_snapshots

scheduler = AsyncIOScheduler()

_last_results: dict[str, str] = {}


def get_job_status():
    jobs = []
    for job in scheduler.get_jobs():
        jobs.append({
            "id": job.id,
            "schedule": str(job.trigger),
            "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
            "last_run": None,
            "last_result": _last_results.get(job.id),
        })
    return jobs


async def daily_snapshot():
    """Fetch balances from all connected workers, upsert into balance_snapshots."""
    from datetime import date
    today = date.today().isoformat()
    health = deps.manager.health_check()

    for cid, state in health.items():
        if state != "connected":
            continue
        try:
            deps.manager.send_command(cid, {"type": "fetch_balances"})
            # Give worker time to respond
            import asyncio
            await asyncio.sleep(2)
            events = deps.manager.collect_events()
            for event in events:
                if event.get("type") == "balances":
                    for bal in event.get("data", []):
                        with deps.db_engine.begin() as conn:
                            conn.execute(
                                insert(balance_snapshots).prefix_with("OR REPLACE").values(
                                    account_id=bal["account_id"],
                                    date=today,
                                    cash=bal.get("cash"),
                                    positions_value=bal.get("positions_value"),
                                    total_value=bal.get("total_value"),
                                    currency=bal.get("currency", "EUR"),
                                    positions=bal.get("positions"),
                                )
                            )
            _last_results["daily_snapshot"] = "ok"
        except Exception as e:
            _last_results["daily_snapshot"] = f"error: {e}"


def setup_scheduler():
    scheduler.add_job(daily_snapshot, "cron", hour=23, minute=0, id="daily_snapshot")
    scheduler.start()
```

- [ ] **Step 2: Update src/main.py lifespan to start scheduler**

Add to the lifespan `yield` block:
```python
from src.scheduler import setup_scheduler
setup_scheduler()
```
And stop it in cleanup:
```python
from src.scheduler import scheduler
scheduler.shutdown()
```

- [ ] **Step 3: Update src/api/health.py to return real scheduler status**

```python
from src.scheduler import get_job_status, scheduler

@router.get("/api/scheduler/status")
def scheduler_status():
    return {"jobs": get_job_status()}
```

- [ ] **Step 4: Run all tests**

Run: `pytest tests/ -v`
Expected: all PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/scheduler.py src/main.py src/api/health.py
git commit -m "feat: APScheduler with daily snapshot cron job"
```

---

## Task 11: Docker setup

**Files:**
- Create: `Dockerfile`
- Create: `docker-compose.yml`

- [ ] **Step 1: Write Dockerfile**

```dockerfile
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libsqlcipher-dev \
    chromium \
    chromium-driver \
    tesseract-ocr \
    gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml .
RUN pip install --no-cache-dir .
COPY src/ src/
COPY alembic/ alembic/
COPY alembic.ini .

EXPOSE 8000
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: Write docker-compose.yml**

```yaml
services:
  api:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - data:/app/data
    restart: unless-stopped

  ib-gateway:
    image: ghcr.io/gnzsnz/ib-gateway:latest
    network_mode: host
    environment:
      TWS_USERID: ${IBKR_USERNAME:-}
      TWS_PASSWORD: ${IBKR_PASSWORD:-}
      TRADING_MODE: live
      READ_ONLY_API: "yes"
      TWOFA_TIMEOUT_ACTION: restart
    volumes:
      - ib-gateway-data:/opt/ibc/config
    restart: unless-stopped

volumes:
  data:
  ib-gateway-data:
```

- [ ] **Step 3: Test Docker build**

Run: `docker build -t mm-ledger .`
Expected: builds without error.

- [ ] **Step 4: Commit**

```bash
git add Dockerfile docker-compose.yml
git commit -m "feat: Docker setup (API + IB Gateway)"
```

---

## Task 12: Woob bank connector worker

**Files:**
- Create: `src/connectors/woob_bank.py`
- Create: `src/patches/woob_banquepopulaire/README.md`

- [ ] **Step 1: Write src/connectors/woob_bank.py**

```python
import shutil
from pathlib import Path

from src.connectors.base import ConnectorWorker


class WoobWorker(ConnectorWorker):
    def __init__(self, cmd_queue, event_queue, config):
        super().__init__(cmd_queue, event_queue, config)
        self._backend = None
        self._woob = None

    def _apply_patches(self):
        """Copy vendorized patches to woob modules directory."""
        patches_dir = Path(__file__).parent.parent / "patches" / "woob_banquepopulaire"
        if not patches_dir.exists():
            return
        target = Path.home() / ".local/share/woob/modules/3.7/woob_modules/banquepopulaire"
        target.mkdir(parents=True, exist_ok=True)
        for f in patches_dir.glob("*.py"):
            shutil.copy2(f, target / f.name)

    def connect(self, credentials: dict):
        from woob.core import Woob
        from woob.exceptions import AppValidation, SentOTPQuestion

        self._apply_patches()
        self._woob = Woob()
        module = credentials.get("bank_module", "banquepopulaire")
        params = {
            "login": credentials["login"],
            "password": credentials["password"],
            "request_information": "interactive",
        }
        if credentials.get("region"):
            params["cdetab"] = credentials["region"]

        self._woob.load_backend(module, "bank", params=params)
        self._backend = self._woob["bank"]

        try:
            accs = list(self._backend.iter_accounts())
            self.event_queue.put({"type": "status", "state": "connected"})
            self.event_queue.put({
                "type": "accounts",
                "data": [{"id": a.id, "name": a.label, "balance": float(a.balance), "currency": a.currency_text, "type": str(a.type)} for a in accs],
            })
        except SentOTPQuestion as e:
            self.event_queue.put({"type": "status", "state": "waiting_2fa", "detail": str(e.message)})
        except AppValidation as e:
            self.event_queue.put({"type": "status", "state": "waiting_2fa", "detail": str(e.message)})

    def disconnect(self):
        self._backend = None
        self._woob = None

    def fetch_accounts(self) -> list[dict]:
        if not self._backend:
            return []
        accs = list(self._backend.iter_accounts())
        return [{"id": a.id, "name": a.label, "balance": float(a.balance), "currency": a.currency_text, "type": str(a.type)} for a in accs]

    def fetch_positions(self) -> list[dict]:
        return []  # Traditional banks don't have positions

    def fetch_balances(self) -> list[dict]:
        if not self._backend:
            return []
        accs = list(self._backend.iter_accounts())
        return [{"account_id": a.id, "cash": float(a.balance), "total_value": float(a.balance), "currency": a.currency_text} for a in accs]

    def fetch_transactions(self) -> list[dict]:
        if not self._backend:
            return []
        result = []
        for acc in self._backend.iter_accounts():
            for tr in self._backend.iter_history(acc):
                result.append({
                    "account_id": acc.id, "date": tr.date.isoformat(),
                    "label": tr.label, "amount": float(tr.amount), "type": str(tr.type),
                })
        return result

    def submit_2fa(self, code: str):
        if not self._backend:
            return
        try:
            self._backend.config["code_sms"].set(code)
        except Exception:
            self._backend.config["resume"].set("ok")
        try:
            accs = list(self._backend.iter_accounts())
            self.event_queue.put({"type": "status", "state": "connected"})
            self.event_queue.put({
                "type": "accounts",
                "data": [{"id": a.id, "name": a.label, "balance": float(a.balance)} for a in accs],
            })
        except Exception as e:
            self.event_queue.put({"type": "error", "message": str(e)})
```

- [ ] **Step 2: Register worker in manager setup (src/main.py)**

Add to lifespan before yield:
```python
from src.connectors.woob_bank import WoobWorker
deps.manager.register_worker_class("woob_bank", WoobWorker)
```

- [ ] **Step 3: Commit**

```bash
git add src/connectors/woob_bank.py src/main.py
git commit -m "feat: Woob bank connector worker with patch application"
```

---

## Task 13: Trade Republic connector worker

**Files:**
- Create: `src/connectors/trade_republic.py`
- Modify: `src/main.py` (register worker)

- [ ] **Step 1: Write src/connectors/trade_republic.py**

Based on `trade_republic_scraper` patterns: Selenium for WAF bypass, websockets for data.

```python
import asyncio
import hashlib
import base64
import json

import requests
from src.connectors.base import ConnectorWorker


class TradeRepublicWorker(ConnectorWorker):
    def __init__(self, cmd_queue, event_queue, config):
        super().__init__(cmd_queue, event_queue, config)
        self._session_token = None
        self._phone = None
        self._pin = None

    def connect(self, credentials: dict):
        self._phone = credentials["phone"]
        self._pin = credentials["pin"]
        self.event_queue.put({"type": "status", "state": "connecting"})

        try:
            waf_token = self._get_waf_token()
            process_id = self._login(waf_token)
            if process_id:
                self.event_queue.put({
                    "type": "status", "state": "waiting_2fa",
                    "detail": "Enter the code from the Trade Republic app",
                })
                self._pending_process_id = process_id
            else:
                self.event_queue.put({"type": "status", "state": "connected"})
        except Exception as e:
            self.event_queue.put({"type": "error", "message": str(e)})

    def _get_waf_token(self) -> str:
        """Use Selenium to get AWS WAF token from TR login page."""
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        import time

        options = Options()
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        driver = webdriver.Chrome(options=options)
        try:
            driver.get("https://app.traderepublic.com/login")
            time.sleep(5)
            cookies = driver.get_cookies()
            for cookie in cookies:
                if cookie["name"] == "aws-waf-token":
                    return cookie["value"]
            # Fallback: try JS API
            token = driver.execute_script("return window.AwsWafIntegration?.getToken()")
            return token or ""
        finally:
            driver.quit()

    def _login(self, waf_token: str) -> str | None:
        """POST login, return processId if 2FA needed."""
        device_id = base64.b64encode(
            hashlib.sha512(f"mm-ledger-{self._phone}".encode()).digest()
        ).decode()
        headers = {
            "x-aws-waf-token": waf_token,
            "Content-Type": "application/json",
        }
        resp = requests.post(
            "https://api.traderepublic.com/api/v1/auth/web/login",
            json={"phoneNumber": self._phone, "pin": self._pin},
            headers=headers,
        )
        data = resp.json()
        if "processId" in data:
            return data["processId"]
        if "sessionToken" in data:
            self._session_token = data["sessionToken"]
            return None
        raise Exception(f"Unexpected login response: {data}")

    def disconnect(self):
        self._session_token = None

    def submit_2fa(self, code: str):
        try:
            resp = requests.post(
                f"https://api.traderepublic.com/api/v1/auth/web/login/{self._pending_process_id}/{code}",
            )
            data = resp.json()
            self._session_token = data.get("sessionToken")
            self.event_queue.put({"type": "status", "state": "connected"})
        except Exception as e:
            self.event_queue.put({"type": "error", "message": str(e)})

    def fetch_accounts(self) -> list[dict]:
        return self._ws_subscribe("accountPairs")

    def fetch_positions(self) -> list[dict]:
        return self._ws_subscribe("compactPortfolioByType")

    def fetch_balances(self) -> list[dict]:
        return self._ws_subscribe("cash")

    def fetch_transactions(self) -> list[dict]:
        return self._ws_subscribe("transactions")

    def _ws_subscribe(self, subscription: str) -> list[dict]:
        """Open WS, subscribe, get one response, close."""
        import websockets.sync.client as ws_client

        with ws_client.connect("wss://api.traderepublic.com") as ws:
            ws.send(json.dumps({
                "action": "subscribe",
                "token": self._session_token,
                "type": subscription,
            }))
            response = ws.recv()
            return json.loads(response) if isinstance(response, str) else []
```

- [ ] **Step 2: Register in src/main.py**

```python
from src.connectors.trade_republic import TradeRepublicWorker
deps.manager.register_worker_class("trade_republic", TradeRepublicWorker)
```

- [ ] **Step 3: Commit**

```bash
git add src/connectors/trade_republic.py src/main.py
git commit -m "feat: Trade Republic connector (Selenium WAF bypass + WebSocket)"
```

---

## Task 14: IBKR connector worker

**Files:**
- Create: `src/connectors/ibkr.py`
- Modify: `src/main.py` (register worker)

- [ ] **Step 1: Write src/connectors/ibkr.py**

```python
from src.connectors.base import ConnectorWorker


class IBKRWorker(ConnectorWorker):
    def __init__(self, cmd_queue, event_queue, config):
        super().__init__(cmd_queue, event_queue, config)
        self._ib = None

    def connect(self, credentials: dict):
        from ib_async import IB

        self._ib = IB()
        host = credentials.get("host", "127.0.0.1")
        port = int(credentials.get("port", 4001))
        try:
            self._ib.connect(host, port, clientId=1)
            self.event_queue.put({"type": "status", "state": "connected"})
        except Exception as e:
            self.event_queue.put({"type": "error", "message": str(e)})

    def disconnect(self):
        if self._ib and self._ib.isConnected():
            self._ib.disconnect()
        self._ib = None

    def fetch_accounts(self) -> list[dict]:
        if not self._ib:
            return []
        accounts = self._ib.managedAccounts()
        return [{"id": acc, "name": acc, "type": "margin"} for acc in accounts]

    def fetch_positions(self) -> list[dict]:
        if not self._ib:
            return []
        positions = self._ib.positions()
        return [
            {
                "account_id": p.account,
                "instrument": str(p.contract.conId),
                "symbol": p.contract.symbol,
                "category": p.contract.secType.lower(),
                "quantity": float(p.position),
                "avg_price": float(p.avgCost),
                "currency": p.contract.currency,
            }
            for p in positions
        ]

    def fetch_balances(self) -> list[dict]:
        if not self._ib:
            return []
        summaries = []
        for acc in self._ib.managedAccounts():
            values = self._ib.accountValues(acc)
            net_liq = next((v.value for v in values if v.tag == "NetLiquidation"), 0)
            cash = next((v.value for v in values if v.tag == "TotalCashBalance"), 0)
            currency = next((v.currency for v in values if v.tag == "NetLiquidation"), "EUR")
            summaries.append({
                "account_id": acc,
                "cash": float(cash),
                "total_value": float(net_liq),
                "positions_value": float(net_liq) - float(cash),
                "currency": currency,
            })
        return summaries

    def fetch_transactions(self) -> list[dict]:
        return []  # IB API doesn't easily expose transaction history

    def submit_2fa(self, code: str):
        pass  # 2FA handled by IB Gateway container
```

- [ ] **Step 2: Register in src/main.py**

```python
from src.connectors.ibkr import IBKRWorker
deps.manager.register_worker_class("ibkr", IBKRWorker)
```

- [ ] **Step 3: Commit**

```bash
git add src/connectors/ibkr.py src/main.py
git commit -m "feat: IBKR connector worker via ib_async"
```

---

## Task 15: Final integration + run all tests

- [ ] **Step 1: Run the full test suite**

Run: `pytest tests/ -v`
Expected: all PASSED.

- [ ] **Step 2: Test the server starts**

Run: `cd /Users/charles/Desktop/mm-ledger && python -c "from src.main import app; print('App created OK')"`
Expected: `App created OK`

- [ ] **Step 3: Commit any remaining fixes**

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "feat: complete Python backend — FastAPI + workers + SQLite + Docker"
```
