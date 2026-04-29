# Persistance de session — Plan d'implémentation

> **For agentic workers:** Use superpowers:subagent-driven-development.

**Goal:** Stocker et restaurer la session active de chaque connecteur dans le vault SQLCipher, pour skip le 2FA et le full-login au restart.

**Architecture:** Extension de la table `credentials` (col `session` JSON), 3 méthodes vault, 2 méthodes optionnelles sur `ConnectorWorker`, hooks dans manager.

**Spec source:** `docs/superpowers/specs/2026-04-29-session-persistence-design.md`

**File map:**
- Modify: `src/vault.py` (ALTER TABLE lazy + 3 méthodes)
- Modify: `src/connectors/base.py` (méthodes optionnelles + run loop avec restore)
- Modify: `src/manager.py` (load session at spawn, store on session_save event, clear on stop)
- Modify: `src/connectors/trade_republic.py` (serialize/restore TR)
- Modify: `src/connectors/ibkr.py` (serialize/restore IBKR — soft, peut juste no-op si trop complexe)
- Modify: `src/connectors/woob_bank.py` (serialize/restore Woob storage)
- Modify: `src/api/banking.py` ou worker équivalent (serialize/restore tokens OAuth)
- Create: `tests/test_vault_session.py`
- Create: `tests/test_session_persistence.py` (intégration manager + worker mocké)

---

## Task 1 : Vault — colonne `session` + méthodes CRUD

**Files:** `src/vault.py`, `tests/test_vault_session.py`

- [ ] **Step 1 : Tests** (`tests/test_vault_session.py`)

```python
import pytest
from src.vault import Vault


@pytest.fixture
def vault(tmp_path):
    v = Vault(tmp_path / "vault.db")
    v.setup("pwd123")
    v.unlock("pwd123")
    v.store("c1", "trade_republic", "TR", {"username": "x"})
    return v


def test_store_and_retrieve_session(vault):
    vault.store_session("c1", {"token": "abc", "refresh": "def"})
    s = vault.retrieve_session("c1")
    assert s == {"token": "abc", "refresh": "def"}


def test_retrieve_session_none_for_unknown(vault):
    assert vault.retrieve_session("nonexistent") is None


def test_retrieve_session_none_when_not_set(vault):
    assert vault.retrieve_session("c1") is None


def test_overwrite_session(vault):
    vault.store_session("c1", {"token": "v1"})
    vault.store_session("c1", {"token": "v2"})
    assert vault.retrieve_session("c1") == {"token": "v2"}


def test_clear_session(vault):
    vault.store_session("c1", {"token": "abc"})
    vault.clear_session("c1")
    assert vault.retrieve_session("c1") is None


def test_session_isolated_per_connector(vault):
    vault.store("c2", "ibkr", "IBKR", {"u": "y"})
    vault.store_session("c1", {"a": 1})
    vault.store_session("c2", {"b": 2})
    assert vault.retrieve_session("c1") == {"a": 1}
    assert vault.retrieve_session("c2") == {"b": 2}


def test_delete_connector_wipes_session(vault):
    vault.store_session("c1", {"x": 1})
    vault.delete("c1")
    # Re-create same id, no session
    vault.store("c1", "trade_republic", "TR", {"username": "x"})
    assert vault.retrieve_session("c1") is None


def test_locked_vault_returns_none(vault, tmp_path):
    vault.lock()
    assert vault.retrieve_session("c1") is None
    vault.store_session("c1", {"a": 1})  # no-op silently
```

- [ ] **Step 2 : Run, fail expected**

```bash
cd /Users/charles/Desktop/mm-ledger && source .venv/bin/activate && pytest tests/test_vault_session.py -v
```

- [ ] **Step 3 : Implémenter dans `src/vault.py`**

Modifier `setup` pour créer la colonne `session` :
```python
def setup(self, password: str) -> None:
    self._path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlcipher3.connect(str(self._path), check_same_thread=False)
    conn.execute('PRAGMA key = "%s"' % password.replace('"', '""'))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS credentials (
            connector_id TEXT PRIMARY KEY,
            connector_type TEXT NOT NULL,
            label TEXT,
            data TEXT NOT NULL,
            session TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    conn.close()
```

Modifier `unlock` pour ALTER TABLE lazy si la colonne `session` n'existe pas (vaults pré-existants) :
```python
def unlock(self, password: str) -> bool:
    try:
        conn = sqlcipher3.connect(str(self._path), check_same_thread=False)
        conn.execute('PRAGMA key = "%s"' % password.replace('"', '""'))
        conn.execute("SELECT count(*) FROM credentials")
        # Lazy migration : ajout colonne session si absente
        cols = {r[1] for r in conn.execute("PRAGMA table_info(credentials)").fetchall()}
        if "session" not in cols:
            conn.execute("ALTER TABLE credentials ADD COLUMN session TEXT")
            conn.commit()
        self._conn = conn
        return True
    except Exception:
        return False
```

Ajouter les 3 méthodes :
```python
def store_session(self, connector_id: str, session: dict) -> None:
    if not self._conn:
        return
    self._conn.execute(
        "UPDATE credentials SET session = ?, updated_at = datetime('now') WHERE connector_id = ?",
        (json.dumps(session), connector_id),
    )
    self._conn.commit()


def retrieve_session(self, connector_id: str) -> dict | None:
    if not self._conn:
        return None
    row = self._conn.execute(
        "SELECT session FROM credentials WHERE connector_id = ?", (connector_id,)
    ).fetchone()
    if not row or row[0] is None:
        return None
    return json.loads(row[0])


def clear_session(self, connector_id: str) -> None:
    if not self._conn:
        return
    self._conn.execute(
        "UPDATE credentials SET session = NULL, updated_at = datetime('now') WHERE connector_id = ?",
        (connector_id,),
    )
    self._conn.commit()
```

- [ ] **Step 4 : Pass + commit**

```bash
pytest tests/test_vault_session.py -v
git add src/vault.py tests/test_vault_session.py
git commit -m "feat(vault): persist session blob par connecteur"
```

---

## Task 2 : `ConnectorWorker` base — méthodes optionnelles + run loop

**Files:** `src/connectors/base.py`

- [ ] **Step 1 : Modifier `src/connectors/base.py`**

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

    def fetch_history_data(self) -> dict:
        return {"transactions": [], "historical_prices": {}, "account_id": ""}

    # --- Persistance de session (override par connecteur) ---

    def serialize_session(self) -> dict | None:
        """Override pour exporter l'état d'auth courant. None = ne rien persister."""
        return None

    def restore_session(self, blob: dict) -> bool:
        """Override pour réinjecter un blob de session.
        Doit pinger un endpoint léger pour valider.
        Renvoie True si la session a été restaurée et est valide, False sinon."""
        return False

    def _emit_session_save(self):
        """Helper pour pousser un event de sauvegarde de session vers le manager."""
        blob = None
        try:
            blob = self.serialize_session()
        except Exception as e:
            self.event_queue.put({"type": "error", "message": f"serialize_session failed: {e}"})
            return
        if blob is not None:
            self.event_queue.put({"type": "session_save", "session": blob})

    def run(self):
        while True:
            cmd = self.cmd_queue.get()
            if cmd["type"] == "shutdown":
                self.disconnect()
                self.event_queue.put({"type": "status", "state": "disconnected"})
                break
            try:
                if cmd["type"] == "connect":
                    creds = cmd.get("credentials", {})
                    session_blob = cmd.get("session_blob")
                    restored = False
                    if session_blob:
                        try:
                            restored = self.restore_session(session_blob)
                        except Exception:
                            restored = False
                    if not restored:
                        self.connect(creds)
                    # Persist current session after successful connect (whether via restore or full login)
                    self._emit_session_save()
                    if not restored:
                        # Already emitted via worker's normal connect path? Some workers emit status themselves.
                        pass
                    continue
                if cmd["type"] == "save_session":
                    self._emit_session_save()
                    continue
                handler = {
                    "disconnect": self.disconnect,
                    "fetch_accounts": self.fetch_accounts,
                    "fetch_positions": self.fetch_positions,
                    "fetch_balances": self.fetch_balances,
                    "fetch_transactions": self.fetch_transactions,
                    "fetch_history_data": self.fetch_history_data,
                    "submit_2fa": lambda: self.submit_2fa(cmd["code"]),
                }[cmd["type"]]
                data = handler()
                if data is not None:
                    event_type = cmd["type"].replace("fetch_", "")
                    self.event_queue.put({"type": event_type, "data": data})
            except Exception as e:
                self.event_queue.put({"type": "error", "message": str(e)})
```

- [ ] **Step 2 : Smoke import**

```bash
python -c "from src.connectors.base import ConnectorWorker; print('OK')"
```

- [ ] **Step 3 : Commit**

```bash
git add src/connectors/base.py
git commit -m "feat(connectors): base — méthodes serialize/restore_session + cmd save_session"
```

---

## Task 3 : Manager — load + persist session

**Files:** `src/manager.py`

- [ ] **Step 1 : Modifier `src/manager.py`**

Repérer la méthode `spawn` et le polling des events. Ajouter :

1. Au `spawn`, lire la session depuis le vault et la passer au worker dans le `connect` cmd :

```python
def spawn(self, connector_id: str, connector_type: str, credentials: dict, session_blob: dict | None = None):
    # ... existing code ...
    cmd_q.put({"type": "connect", "credentials": credentials, "session_blob": session_blob})
```

2. Côté API (qui appelle `manager.spawn`) : modifier l'appelant pour passer `session_blob = vault.retrieve_session(connector_id)`. Si vault not unlocked → None (no restore).

3. Dans `collect_events()` (ou équivalent — la méthode qui drain les event_queues), gérer le nouveau type `session_save` :

```python
# Dans collect_events ou un autre point central
if event["type"] == "session_save":
    user_id, connector_id = composite_key.split(":", 1)
    blob = event.get("session")
    if blob:
        # Le manager n'a pas accès direct au vault. On émet un event interne consommable
        # par l'API layer, OU on stocke un callback session_persist dans le manager.
        self._pending_session_writes[composite_key] = blob
```

Approche pragmatique : le manager garde un dict `_pending_sessions` ; un point d'API (par ex. `connect` worker) draine ce dict et appelle `vault.store_session`. Ou plus simple : **callback** passé au manager au démarrage qui prend `(user_id, connector_id, blob)` et fait l'écriture.

Choix retenu : **callback**. Dans `ConnectorManager.__init__`, accepter un `session_persist: Callable[[str, str, dict | None], None]` (action="save" si blob non None, sinon "clear"). À l'event `session_save`, le manager appelle `self._session_persist(user_id, cid, blob)`. À `stop(connector_id)` : `self._session_persist(user_id, cid, None)` pour clear.

L'API layer (par ex. `src/api/connectors.py`) configure le callback :
```python
manager = ConnectorManager(session_persist=lambda uid, cid, blob: _persist(uid, cid, blob))

def _persist(user_id, connector_id, blob):
    vault = deps.get_vault(user_id)
    if blob is None:
        vault.clear_session(connector_id)
    else:
        vault.store_session(connector_id, blob)
```

- [ ] **Step 2 : Test integration** (`tests/test_session_persistence.py`)

Test scenario simple avec un faux worker qui implement serialize/restore et vérifie que la session est bien round-trippée :

```python
import pytest
from multiprocessing import Queue
from unittest.mock import MagicMock
from src.connectors.base import ConnectorWorker


class FakeConnector(ConnectorWorker):
    def __init__(self, cmd_q, event_q, config):
        super().__init__(cmd_q, event_q, config)
        self._token = None
        self.connect_called = 0

    def connect(self, credentials):
        self.connect_called += 1
        self._token = "fresh_token"
        self.event_queue.put({"type": "status", "state": "connected"})

    def disconnect(self): pass
    def fetch_accounts(self): return []
    def fetch_positions(self): return []
    def fetch_balances(self): return []
    def fetch_transactions(self): return []
    def submit_2fa(self, code): pass

    def serialize_session(self):
        return {"token": self._token} if self._token else None

    def restore_session(self, blob):
        if blob.get("token") == "valid_token":
            self._token = blob["token"]
            self.event_queue.put({"type": "status", "state": "connected"})
            return True
        return False


def test_connect_with_valid_session_skips_login():
    cmd_q = Queue()
    ev_q = Queue()
    w = FakeConnector(cmd_q, ev_q, {})
    cmd_q.put({"type": "connect", "credentials": {"u": "x"}, "session_blob": {"token": "valid_token"}})
    cmd_q.put({"type": "shutdown"})
    w.run()
    assert w.connect_called == 0
    # session_save émis avec le token valide
    events = []
    while not ev_q.empty():
        events.append(ev_q.get())
    save_events = [e for e in events if e["type"] == "session_save"]
    assert len(save_events) == 1
    assert save_events[0]["session"] == {"token": "valid_token"}


def test_connect_with_invalid_session_falls_back_to_login():
    cmd_q = Queue()
    ev_q = Queue()
    w = FakeConnector(cmd_q, ev_q, {})
    cmd_q.put({"type": "connect", "credentials": {"u": "x"}, "session_blob": {"token": "expired"}})
    cmd_q.put({"type": "shutdown"})
    w.run()
    assert w.connect_called == 1
    # session_save émis avec le nouveau token frais
    events = []
    while not ev_q.empty():
        events.append(ev_q.get())
    save_events = [e for e in events if e["type"] == "session_save"]
    assert len(save_events) == 1
    assert save_events[0]["session"] == {"token": "fresh_token"}


def test_connect_without_session_does_full_login():
    cmd_q = Queue()
    ev_q = Queue()
    w = FakeConnector(cmd_q, ev_q, {})
    cmd_q.put({"type": "connect", "credentials": {"u": "x"}})  # pas de session_blob
    cmd_q.put({"type": "shutdown"})
    w.run()
    assert w.connect_called == 1
```

- [ ] **Step 3 : Pass + commit**

```bash
pytest tests/test_session_persistence.py -v
git add src/manager.py src/api/connectors.py tests/test_session_persistence.py
git commit -m "feat(manager): hook session_save → vault + load au spawn"
```

---

## Task 4 : TR — serialize / restore session

**Files:** `src/connectors/trade_republic.py`

- [ ] Repérer `_session_token`, `_refresh_token` (et tout autre attribut d'auth) dans la classe TR.
- [ ] Implémenter :

```python
def serialize_session(self) -> dict | None:
    if not getattr(self, "_session_token", None):
        return None
    return {
        "session_token": self._session_token,
        "refresh_token": getattr(self, "_refresh_token", None),
        "device_id": getattr(self, "_device_id", None),
    }

def restore_session(self, blob: dict) -> bool:
    token = blob.get("session_token")
    if not token:
        return False
    self._session_token = token
    self._refresh_token = blob.get("refresh_token")
    self._device_id = blob.get("device_id")
    # Ping de validation : tente une commande WS légère
    try:
        import websockets.sync.client as ws_client
        with ws_client.connect("wss://api.traderepublic.com", close_timeout=5, open_timeout=5) as ws:
            self._ws_connect(ws)
            resp = self._ws_sub(ws, {"type": "accountInfo", "token": self._session_token})
            if not resp:
                return False
        self.event_queue.put({"type": "status", "state": "connected"})
        return True
    except Exception:
        return False
```

- [ ] Commit : `feat(tr): persist + restore session token`

---

## Task 5 : IBKR — serialize / restore session

**Files:** `src/connectors/ibkr.py`

L'IBKR n'utilise pas de token au sens classique : la connexion TWS est portée par le container `ib-gateway`. Si le container est encore up, on peut juste ré-établir le `IB().connect()` du process sans relancer le container.

- [ ] Implémenter :

```python
def serialize_session(self) -> dict | None:
    if not self._ib or not self._ib.isConnected():
        return None
    return {
        "host": self._host,
        "port": self._port,
        "client_id": self._client_id,
        "account_id": self._account_id,
    }

def restore_session(self, blob: dict) -> bool:
    """Tente de se reconnecter au container ib-gateway déjà lancé.
    Si le container est down (image non démarrée), retourne False et le full-flow
    de connect() relancera le container."""
    try:
        from ib_async import IB
        ib = IB()
        ib.connect(blob["host"], blob["port"], blob["client_id"], timeout=5)
        if not ib.isConnected():
            return False
        self._ib = ib
        self._host = blob["host"]
        self._port = blob["port"]
        self._client_id = blob["client_id"]
        self._account_id = blob.get("account_id")
        self.event_queue.put({"type": "status", "state": "connected"})
        return True
    except Exception:
        return False
```

- [ ] Commit : `feat(ibkr): restore connection sans relancer le container`

---

## Task 6 : woob_bank — serialize / restore Woob storage

**Files:** `src/connectors/woob_bank.py`

Woob a un `Storage` interne par backend. La session Woob (cookies, état 2FA) y vit.

- [ ] Implémenter :

```python
def serialize_session(self) -> dict | None:
    if not self._backend:
        return None
    storage = getattr(self._backend, "storage", None)
    if storage is None:
        return None
    # Woob storage expose dump/load (ou une équivalente — vérifier l'API)
    try:
        return {"woob_storage": dict(storage.values)}
    except Exception:
        return None

def restore_session(self, blob: dict) -> bool:
    storage_blob = blob.get("woob_storage")
    if not storage_blob:
        return False
    try:
        # Re-créer un backend avec la storage restaurée, puis ping
        # ... (détails dépendent de l'API Woob exacte ; voir code existant connect())
        # ping :
        self._backend.iter_accounts().__next__()  # ou similaire
        self.event_queue.put({"type": "status", "state": "connected"})
        return True
    except Exception:
        return False
```

(Implémentation à finaliser à l'impl en regardant la vraie API Woob — la storage est typiquement un objet exposant `.dump()` ou `.values`.)

- [ ] Commit : `feat(woob): persist + restore storage Woob`

---

## Task 7 : banking (Enable Banking) — serialize / restore tokens OAuth

**Files:** `src/api/banking.py` ou worker associé.

Vérifier s'il y a un worker banking ou si c'est juste des routes API. Si juste API : ajouter à la table credentials un champ équivalent (déjà via session). Si worker : implémenter comme les autres.

Enable Banking utilise des sessions par `asid` avec expiry. Sérialiser :

```python
def serialize_session(self) -> dict | None:
    if not self._asid:
        return None
    return {
        "asid": self._asid,
        "valid_until": self._valid_until,
        "access_token": self._access_token,  # si applicable
    }

def restore_session(self, blob: dict) -> bool:
    asid = blob.get("asid")
    valid_until = blob.get("valid_until")
    if not asid:
        return False
    # Check expiry
    if valid_until and _date.fromisoformat(valid_until) < _date.today():
        return False
    self._asid = asid
    self._access_token = blob.get("access_token")
    # Ping : GET /sessions/{asid} sur Enable Banking API
    try:
        # ... call API to verify session is still valid
        self.event_queue.put({"type": "status", "state": "connected"})
        return True
    except Exception:
        return False
```

- [ ] Commit : `feat(banking): persist + restore session Enable Banking`

---

## Task 8 : CLAUDE.md + vérif finale

- [ ] Note dans CLAUDE.md (Gotchas) :

> **Persistance de session (toutes connecteurs)** : à chaque connect réussi, le worker sérialise sa session (tokens TR, connexion IBKR, Woob storage, tokens banking) et le manager la stocke dans le vault SQLCipher (col `session` de la table `credentials`). Au restart, le vault est unlocked → le manager réinjecte la session dans le worker via `restore_session(blob)` → ping de validation → si OK, état `connected` direct, **pas de 2FA**. Si KO, fallback transparent sur le `connect(credentials)` complet. Spec : `docs/superpowers/specs/2026-04-29-session-persistence-design.md`. Méthodes overridables dans `ConnectorWorker.serialize_session()` / `restore_session()`.

- [ ] pytest global vert + tests d'intégration session.
- [ ] Commit : `docs: note persistance de session dans CLAUDE.md`.
