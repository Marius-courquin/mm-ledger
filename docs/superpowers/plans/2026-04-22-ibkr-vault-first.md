# IBKR vault-first Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rétablir un IBKR fonctionnel, creds entièrement gérés par le vault (zéro `.env`), container `ib-gateway` orchestré à la demande par l'app, et fixer au passage le bug cross-cutting du manager où les events `error` ne transitionnaient pas l'état du worker.

**Architecture:** L'app spawn `ib-gateway` via le SDK `docker` Python au moment du `connect`. Les credentials arrivent du vault SQLCipher dans l'env du container (jamais sur disque). En prod le container rejoint un network docker dédié (pas de port exposé sur l'hôte) ; en dev le port est publié sur `127.0.0.1:4001`. Worker identifié par un `worker_key` composite (`{user_id}:{connector_id}`), sanitisé en nom de container. Hardening : digest pinné, `no-new-privileges`, limites CPU/RAM, `READ_ONLY_API=yes`, audit log sans creds.

**Tech Stack:** Python 3.12, FastAPI, multiprocessing, `docker>=7` (Python SDK), `ib_async`, SQLCipher, React 19, TypeScript.

**Spec :** `docs/superpowers/specs/2026-04-22-ibkr-vault-first-design.md`

---

## Task 1 : Manager — event `error` transitionne l'état du worker

**Files:**
- Modify: `src/manager.py:75-82`
- Test: `tests/test_manager.py` (ajout)

- [ ] **Step 1 : Écrire le test qui échoue**

Ajouter à la fin de `tests/test_manager.py` :

```python
def test_error_event_transitions_state_to_error():
    mgr = ConnectorManager()

    class FailingWorker(ConnectorWorker):
        def connect(self, credentials: dict):
            self.event_queue.put({"type": "error", "message": "boom"})

        def disconnect(self): pass
        def fetch_accounts(self): return []
        def fetch_positions(self): return []
        def fetch_balances(self): return []
        def fetch_transactions(self): return []
        def submit_2fa(self, code: str): pass

    mgr.register_worker_class("failing", FailingWorker)
    mgr.spawn("err_1", "failing", {})
    time.sleep(0.5)
    status = mgr.get_status("err_1")
    assert status["state"] == "error"
    assert status["detail"] == "boom"
    mgr.stop("err_1")
```

- [ ] **Step 2 : Vérifier que le test échoue**

```
pytest tests/test_manager.py::test_error_event_transitions_state_to_error -v
```

Expected : FAIL — `status["state"] == "connecting"` (état initial jamais transitionné).

- [ ] **Step 3 : Fix `src/manager.py::collect_events`**

Dans `src/manager.py`, remplacer le bloc de traitement d'events (lignes ~73-82) par :

```python
if evt_type == "status":
    handle.state = event.get("state", handle.state)
    handle.detail = event.get("detail")
elif evt_type == "error":
    handle.state = "error"
    handle.detail = event.get("message")
elif evt_type in ("accounts", "balances", "positions", "transactions"):
    # Cache live data
    if cid not in self.live_data:
        self.live_data[cid] = {"accounts": [], "balances": [], "positions": [], "transactions": []}
    self.live_data[cid][evt_type] = event.get("data", [])
```

- [ ] **Step 4 : Vérifier que le test passe (et les autres aussi)**

```
pytest tests/test_manager.py -v
```

Expected : tous PASS.

- [ ] **Step 5 : Commit**

```
git add src/manager.py tests/test_manager.py
git commit -m "fix(manager): events 'error' transitionnent l'état du worker

Bug transverse — un worker émettant un event error restait bloqué en
'connecting' côté UI. collect_events() traite maintenant les events
error en passant à state='error' avec detail=message."
```

---

## Task 2 : Manager — passer `worker_key` au worker via `config`

**Files:**
- Modify: `src/manager.py::_run_worker`, `src/manager.py::ConnectorManager.spawn`
- Test: `tests/test_manager.py` (ajout)

- [ ] **Step 1 : Écrire le test qui échoue**

Ajouter à `tests/test_manager.py` :

```python
def test_worker_receives_worker_key_in_config():
    mgr = ConnectorManager()

    class KeyCapturingWorker(ConnectorWorker):
        def connect(self, credentials: dict):
            key = self.config.get("worker_key", "MISSING")
            self.event_queue.put({"type": "status", "state": "connected", "detail": key})

        def disconnect(self): pass
        def fetch_accounts(self): return []
        def fetch_positions(self): return []
        def fetch_balances(self): return []
        def fetch_transactions(self): return []
        def submit_2fa(self, code: str): pass

    mgr.register_worker_class("keycap", KeyCapturingWorker)
    mgr.spawn("user42:myconn", "keycap", {})
    time.sleep(0.5)
    status = mgr.get_status("user42:myconn")
    assert status["state"] == "connected"
    assert status["detail"] == "user42:myconn"
    mgr.stop("user42:myconn")
```

- [ ] **Step 2 : Vérifier que le test échoue**

```
pytest tests/test_manager.py::test_worker_receives_worker_key_in_config -v
```

Expected : FAIL — `detail` vaut `"MISSING"` (config vide).

- [ ] **Step 3 : Modifier `_run_worker` et `spawn` dans `src/manager.py`**

```python
def _run_worker(cls, cmd_q, event_q, config):
    """Module-level target so it can be pickled by the spawn start method."""
    worker = cls(cmd_q, event_q, config)
    worker.run()
```

Et dans `ConnectorManager.spawn`, remplacer la création du process :

```python
proc = Process(
    target=_run_worker,
    args=(cls, cmd_q, event_q, {"worker_key": connector_id}),
    daemon=True,
)
```

- [ ] **Step 4 : Vérifier que tous les tests passent**

```
pytest tests/test_manager.py -v
```

Expected : tous PASS.

- [ ] **Step 5 : Commit**

```
git add src/manager.py tests/test_manager.py
git commit -m "feat(manager): injecter worker_key dans la config du worker

Le worker reçoit sa clé composite (user_id:connector_id) via
config['worker_key']. Nécessaire pour que IBKR puisse nommer son
container docker de manière unique par user."
```

---

## Task 3 : API — CONNECTOR_TYPES IBKR passe en `credential_fields`

**Files:**
- Modify: `src/api/connectors.py:22-30`
- Test: `tests/test_api_connectors.py:67-73` (modifier)

- [ ] **Step 1 : Modifier le test existant `test_get_connector_types`**

Dans `tests/test_api_connectors.py`, remplacer `test_get_connector_types` par :

```python
def test_get_connector_types_includes_ibkr_vault_fields():
    response = client.get("/api/connectors/types")
    assert response.status_code == 200
    types = response.json()
    ibkr = next((t for t in types if t["type"] == "ibkr"), None)
    assert ibkr is not None

    names = {f["name"] for f in ibkr["credential_fields"]}
    assert names == {"username", "password", "trading_mode"}

    pwd = next(f for f in ibkr["credential_fields"] if f["name"] == "password")
    assert pwd["type"] == "password"

    tm = next(f for f in ibkr["credential_fields"] if f["name"] == "trading_mode")
    assert tm["type"] == "select"
    assert {o["value"] for o in tm["options"]} == {"live", "paper"}

    assert ibkr["config_fields"] == []
```

- [ ] **Step 2 : Vérifier que le test échoue**

```
pytest tests/test_api_connectors.py::test_get_connector_types_includes_ibkr_vault_fields -v
```

Expected : FAIL — `credential_fields` actuellement vide.

- [ ] **Step 3 : Modifier le schéma IBKR dans `src/api/connectors.py`**

Remplacer le bloc IBKR (lignes 22-30) par :

```python
{
    "type": "ibkr", "label": "Interactive Brokers",
    "credential_fields": [
        {"name": "username", "type": "text", "required": True},
        {"name": "password", "type": "password", "required": True},
        {
            "name": "trading_mode", "type": "select", "required": True,
            "options": [
                {"value": "live", "label": "Live"},
                {"value": "paper", "label": "Paper"},
            ],
            "default": "live",
        },
    ],
    "config_fields": [],
    "supports_2fa": False, "supports_streaming": True,
},
```

- [ ] **Step 4 : Vérifier que les tests passent**

```
pytest tests/test_api_connectors.py -v
```

Expected : tous PASS.

- [ ] **Step 5 : Commit**

```
git add src/api/connectors.py tests/test_api_connectors.py
git commit -m "feat(api): creds IBKR en credential_fields (vault)

IBKR passe de config_fields (host/port) à credential_fields
(username, password, trading_mode). Les creds iront désormais
dans le vault au lieu de l'env du container ib-gateway."
```

---

## Task 4 : Frontend — typer `starting_gateway`, supporter les champs `select`, afficher le détail d'erreur

**Files:**
- Modify: `frontend/src/lib/types.ts:10`, `frontend/src/lib/types.ts` (CredentialField)
- Modify: `frontend/src/components/ConnectorForm.tsx`
- Modify: `frontend/src/pages/Accounts.tsx:15-21` + rendu de la carte

- [ ] **Step 1 : Ajouter `starting_gateway` à WorkerState**

Dans `frontend/src/lib/types.ts`, modifier ligne 10 :

```typescript
export type WorkerState = 'disconnected' | 'connecting' | 'starting_gateway' | 'connected' | 'waiting_2fa' | 'error';
```

Et étendre `CredentialField` (chercher la déf) pour inclure le type `select` :

```typescript
export interface CredentialField {
  name: string;
  type: 'text' | 'password' | 'number' | 'select';
  required: boolean;
  placeholder?: string;
  default?: string | number;
  options?: Array<{ value: string; label: string }>;
}
```

Et ajouter aussi `ConnectorType = 'banking'` si ce n'est pas déjà là (sanity check — commit `de9372b` l'a peut-être introduit).

- [ ] **Step 2 : Étendre `statusConfig` dans `Accounts.tsx`**

Dans `frontend/src/pages/Accounts.tsx`, remplacer le bloc `statusConfig` (lignes 15-21) :

```typescript
const statusConfig: Record<WorkerState, { color: string; label: string }> = {
  connected: { color: 'bg-green-500', label: 'Connecté' },
  connecting: { color: 'bg-yellow-500', label: 'Connexion...' },
  starting_gateway: { color: 'bg-yellow-500', label: 'Démarrage gateway...' },
  waiting_2fa: { color: 'bg-yellow-500', label: 'En attente 2FA' },
  error: { color: 'bg-red-500', label: 'Erreur' },
  disconnected: { color: 'bg-gray-500', label: 'Déconnecté' },
};
```

- [ ] **Step 3 : Afficher le `worker.detail` sous la carte quand state = error**

Toujours dans `Accounts.tsx`, dans le rendu de la carte (entre le bloc "Middle: account count" et "Bottom: actions"), ajouter :

```tsx
{workerState === 'error' && connector.worker?.detail && (
  <div className="text-xs text-red-400 bg-red-500/10 border border-red-500/20 rounded-md px-2 py-1.5">
    {connector.worker.detail}
  </div>
)}
```

- [ ] **Step 4 : Supporter le type `select` dans ConnectorForm**

Lire `frontend/src/components/ConnectorForm.tsx` pour trouver le switch de rendu sur `field.type`. Ajouter une branche :

```tsx
{field.type === 'select' && field.options && (
  <select
    id={field.name}
    name={field.name}
    required={field.required}
    defaultValue={String(field.default ?? field.options[0].value)}
    className="w-full rounded-md bg-mm-surface border border-mm-border px-3 py-2 text-sm text-mm-text"
  >
    {field.options.map(opt => (
      <option key={opt.value} value={opt.value}>{opt.label}</option>
    ))}
  </select>
)}
```

(Adapter aux classes Tailwind / HeroUI existantes dans le fichier — garder le style cohérent avec les autres inputs du même fichier.)

- [ ] **Step 5 : Vérifier le build TS**

```
cd frontend && bun run build
```

Expected : build OK, zéro erreur TypeScript.

- [ ] **Step 6 : Commit**

```
git add frontend/src/lib/types.ts frontend/src/pages/Accounts.tsx frontend/src/components/ConnectorForm.tsx
git commit -m "feat(front): état 'starting_gateway', champs select, détail d'erreur

- WorkerState inclut 'starting_gateway' (affiché en jaune)
- CredentialField accepte type: 'select' avec options
- La carte connecteur affiche worker.detail en rouge quand state='error'"
```

---

## Task 5 : Dépendances Python + résolution du digest d'image

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1 : Ajouter `docker` aux deps**

Dans `pyproject.toml`, ajouter `"docker>=7"` à la liste `dependencies` (par ex. après `"ib_async"`).

- [ ] **Step 2 : Installer**

```
source .venv/bin/activate && pip install -e ".[dev]"
```

Expected : `Successfully installed docker-7.X...`

- [ ] **Step 3 : Résoudre le digest de `ghcr.io/gnzsnz/ib-gateway`**

```
docker buildx imagetools inspect ghcr.io/gnzsnz/ib-gateway:latest-stable
```

Expected : sortie listant `MediaType: application/vnd.docker.distribution.manifest.list.v2+json` (= manifest multi-arch) avec des entrées `linux/amd64` ET `linux/arm64`. Noter le digest top-level (`Digest: sha256:...`).

Si la commande échoue ou qu'il n'y a pas d'arm64 : essayer `:stable` ou consulter les tags disponibles (`gh api /users/gnzsnz/packages/container/ib-gateway/versions` — ou `docker search` / registry UI). **Ne pas** avancer tant qu'un digest multi-arch n'est pas identifié.

- [ ] **Step 4 : Noter le digest pour le prochain task**

Conserver la valeur `sha256:<DIGEST>` — elle sera collée dans la constante `IBKR_GATEWAY_IMAGE` à la Task 6.

- [ ] **Step 5 : Commit**

```
git add pyproject.toml
git commit -m "build: ajouter docker>=7 pour orchestrer ib-gateway"
```

---

## Task 6 : IBKR worker — constantes, helpers, sanitisation de clé

**Files:**
- Modify: `src/connectors/ibkr.py` (réécriture partielle)
- Test: `tests/test_connector_ibkr.py` (nouveau)

- [ ] **Step 1 : Créer `tests/test_connector_ibkr.py` avec les tests helpers**

```python
from multiprocessing import Queue
from unittest.mock import patch

from src.connectors.ibkr import IBKRWorker


def _make_worker(worker_key: str = "user1:myibkr") -> IBKRWorker:
    return IBKRWorker(Queue(), Queue(), {"worker_key": worker_key})


def test_safe_key_sanitises_colons_and_special_chars():
    w = _make_worker("User42:My_Conn!")
    assert w._safe_key() == "user42-my_conn-"


def test_safe_key_truncates_to_50_chars():
    w = _make_worker("a" * 80)
    assert len(w._safe_key()) == 50


def test_dev_mode_true_when_no_dockerenv():
    w = _make_worker()
    with patch("os.path.exists", return_value=False):
        assert w._dev_mode() is True


def test_dev_mode_false_when_dockerenv_exists():
    w = _make_worker()
    with patch("os.path.exists", return_value=True):
        assert w._dev_mode() is False


def test_gateway_endpoint_dev_returns_localhost():
    w = _make_worker()
    with patch.object(IBKRWorker, "_dev_mode", return_value=True):
        assert w._gateway_endpoint() == ("127.0.0.1", 4001)


def test_gateway_endpoint_prod_returns_container_name():
    w = _make_worker("user1:ib")
    with patch.object(IBKRWorker, "_dev_mode", return_value=False):
        host, port = w._gateway_endpoint()
        assert host == "mm-ledger-ibkr-user1-ib"
        assert port == 4001
```

- [ ] **Step 2 : Vérifier que les tests échouent**

```
pytest tests/test_connector_ibkr.py -v
```

Expected : FAIL (méthodes `_safe_key`, `_dev_mode`, `_gateway_endpoint` inexistantes).

- [ ] **Step 3 : Réécrire `src/connectors/ibkr.py` avec les constantes et helpers**

Remplacer intégralement `src/connectors/ibkr.py` par :

```python
import logging
import os
import re

from src.connectors.base import ConnectorWorker

log = logging.getLogger(__name__)

# Pinné par digest pour prévenir une substitution silencieuse (supply chain).
# Digest multi-arch (manifest list) — doit lister amd64 ET arm64.
# Upgrade = action manuelle après audit du changelog amont.
IBKR_GATEWAY_IMAGE = "ghcr.io/gnzsnz/ib-gateway@sha256:<DIGEST_FROM_TASK_5>"
IBKR_NETWORK_NAME = "mm-ledger-net"
IBKR_GATEWAY_PORT = 4001
IBKR_GATEWAY_START_TIMEOUT = 90  # seconds


class IBKRWorker(ConnectorWorker):
    def __init__(self, cmd_queue, event_queue, config):
        super().__init__(cmd_queue, event_queue, config)
        self._ib = None
        self._container = None
        self._docker = None

    # ── helpers ──────────────────────────────────────────────────────────

    def _safe_key(self) -> str:
        # docker container names: [a-zA-Z0-9][a-zA-Z0-9_.-]*, max 63 chars
        raw = self.config.get("worker_key", "default").lower()
        return re.sub(r"[^a-z0-9_.-]", "-", raw)[:50]

    @property
    def _container_name(self) -> str:
        return f"mm-ledger-ibkr-{self._safe_key()}"

    def _dev_mode(self) -> bool:
        # App runs inside docker if /.dockerenv exists.
        return not os.path.exists("/.dockerenv")

    def _gateway_endpoint(self) -> tuple[str, int]:
        if self._dev_mode():
            return ("127.0.0.1", IBKR_GATEWAY_PORT)
        return (self._container_name, IBKR_GATEWAY_PORT)

    # ── contract methods (stubs, implémentés aux tasks suivants) ────────

    def connect(self, credentials: dict) -> None:
        raise NotImplementedError  # Task 7

    def disconnect(self) -> None:
        raise NotImplementedError  # Task 9

    def fetch_accounts(self) -> list[dict]:
        if not self._ib:
            return []
        return [{"id": a, "name": a, "type": "margin"} for a in self._ib.managedAccounts()]

    def fetch_positions(self) -> list[dict]:
        if not self._ib:
            return []
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
            for p in self._ib.positions()
        ]

    def fetch_balances(self) -> list[dict]:
        if not self._ib:
            return []
        out = []
        for acc in self._ib.managedAccounts():
            values = self._ib.accountValues(acc)
            net_liq = next((v.value for v in values if v.tag == "NetLiquidation"), 0)
            cash = next((v.value for v in values if v.tag == "TotalCashBalance"), 0)
            currency = next((v.currency for v in values if v.tag == "NetLiquidation"), "EUR")
            out.append({
                "account_id": acc,
                "cash": float(cash),
                "total_value": float(net_liq),
                "positions_value": float(net_liq) - float(cash),
                "currency": currency,
            })
        return out

    def fetch_transactions(self) -> list[dict]:
        return []

    def submit_2fa(self, code: str) -> None:
        pass
```

Note : le digest `<DIGEST_FROM_TASK_5>` est une chaîne littérale pour l'instant (les tests mockent docker, ils n'appellent pas l'image). On fige la vraie valeur avant le déploiement, pas avant d'écrire le code. **Après Task 5 on connaît le digest** → le coller ici tel quel.

- [ ] **Step 4 : Vérifier que les tests passent**

```
pytest tests/test_connector_ibkr.py -v
```

Expected : tous PASS.

- [ ] **Step 5 : Commit**

```
git add src/connectors/ibkr.py tests/test_connector_ibkr.py
git commit -m "refactor(ibkr): helpers (safe_key, dev_mode, endpoint) + constantes

Prépare le worker à orchestrer ib-gateway : nom de container unique
sanitisé, détection dev vs prod pour choisir l'endpoint, image pinnée
par digest. connect/disconnect encore stubbés (NotImplementedError)."
```

---

## Task 7 : IBKR worker — `connect()` avec spawn container + hardening + poll

**Files:**
- Modify: `src/connectors/ibkr.py::connect`
- Test: `tests/test_connector_ibkr.py` (ajout)

- [ ] **Step 1 : Écrire les tests du connect happy path + hardening**

Ajouter à `tests/test_connector_ibkr.py` :

```python
from unittest.mock import MagicMock, patch
import socket


def _creds() -> dict:
    return {"username": "charlie", "password": "s3cret", "trading_mode": "live"}


def _patch_connect_dependencies():
    """Return context patching docker, ib_async, socket, time.sleep.

    Yields a dict with 'docker_client', 'container', 'ib'."""
    from contextlib import contextmanager

    @contextmanager
    def _ctx():
        with patch("src.connectors.ibkr.docker") as mock_docker, \
             patch("src.connectors.ibkr.IB") as mock_ib_cls, \
             patch("src.connectors.ibkr.socket.create_connection") as mock_sock, \
             patch("src.connectors.ibkr.time.sleep"):
            client = MagicMock()
            container = MagicMock()
            client.containers.run.return_value = container
            client.containers.get.side_effect = _docker_errors_not_found()
            mock_docker.from_env.return_value = client
            mock_sock.return_value.__enter__.return_value = MagicMock()
            ib = MagicMock()
            mock_ib_cls.return_value = ib
            yield {"docker_client": client, "container": container, "ib": ib, "mock_docker": mock_docker}
    return _ctx()


def _docker_errors_not_found():
    # We need a real docker.errors.NotFound to raise from .get()
    import docker
    return docker.errors.NotFound("not found")


def test_connect_happy_path_emits_connected():
    w = _make_worker("u1:ib")
    with _patch_connect_dependencies() as ctx:
        w.connect(_creds())
    events = []
    while not w.event_queue.empty():
        events.append(w.event_queue.get())
    states = [e.get("state") for e in events if e.get("type") == "status"]
    assert "starting_gateway" in states
    assert "connected" in states


def test_connect_passes_hardening_flags_to_container():
    w = _make_worker("u1:ib")
    with _patch_connect_dependencies() as ctx:
        w.connect(_creds())
    kwargs = ctx["docker_client"].containers.run.call_args.kwargs
    assert kwargs["security_opt"] == ["no-new-privileges:true"]
    assert kwargs["mem_limit"] == "2g"
    assert kwargs["nano_cpus"] == 2_000_000_000
    assert kwargs["auto_remove"] is True
    assert kwargs["detach"] is True
    assert kwargs["name"] == "mm-ledger-ibkr-u1-ib"
    # Image digest pinned
    assert kwargs["image"].startswith("ghcr.io/gnzsnz/ib-gateway@sha256:")
    # Env contains creds (expected — they are passed here, not on disk)
    assert kwargs["environment"]["TWS_USERID"] == "charlie"
    assert kwargs["environment"]["TWS_PASSWORD"] == "s3cret"
    assert kwargs["environment"]["TRADING_MODE"] == "live"
    assert kwargs["environment"]["READ_ONLY_API"] == "yes"


def test_connect_dev_mode_publishes_port_on_localhost():
    w = _make_worker("u1:ib")
    with patch.object(IBKRWorker, "_dev_mode", return_value=True), \
         _patch_connect_dependencies() as ctx:
        w.connect(_creds())
    kwargs = ctx["docker_client"].containers.run.call_args.kwargs
    assert kwargs.get("ports") == {"4001/tcp": ("127.0.0.1", 4001)}


def test_connect_prod_mode_no_port_published():
    w = _make_worker("u1:ib")
    with patch.object(IBKRWorker, "_dev_mode", return_value=False), \
         _patch_connect_dependencies() as ctx:
        w.connect(_creds())
    kwargs = ctx["docker_client"].containers.run.call_args.kwargs
    assert "ports" not in kwargs or not kwargs["ports"]


def test_connect_calls_ib_connect_with_correct_endpoint():
    w = _make_worker("u1:ib")
    with patch.object(IBKRWorker, "_dev_mode", return_value=True), \
         _patch_connect_dependencies() as ctx:
        w.connect(_creds())
    ctx["ib"].connect.assert_called_once_with("127.0.0.1", 4001, clientId=1)
```

- [ ] **Step 2 : Vérifier que les tests échouent**

```
pytest tests/test_connector_ibkr.py -v
```

Expected : FAIL — `connect` lève `NotImplementedError`.

- [ ] **Step 3 : Implémenter `connect()` dans `src/connectors/ibkr.py`**

Ajouter en haut du fichier (à côté des imports) :

```python
import socket
import time

import docker
import docker.errors
from ib_async import IB
```

Remplacer le corps de `connect()` par :

```python
def connect(self, credentials: dict) -> None:
    self._docker = docker.from_env()

    # 1. Nettoyage d'un éventuel container orphelin
    self._remove_existing_container()

    # 2. Spawn ib-gateway (hardened)
    run_kwargs = dict(
        image=IBKR_GATEWAY_IMAGE,
        name=self._container_name,
        environment={
            "TWS_USERID": credentials["username"],
            "TWS_PASSWORD": credentials["password"],
            "TRADING_MODE": credentials["trading_mode"],
            "READ_ONLY_API": "yes",
            "TWOFA_TIMEOUT_ACTION": "restart",
        },
        detach=True,
        auto_remove=True,
        labels={"mm-ledger": "ibkr-gateway"},
        security_opt=["no-new-privileges:true"],
        mem_limit="2g",
        nano_cpus=2_000_000_000,
        network=IBKR_NETWORK_NAME,
    )
    if self._dev_mode():
        run_kwargs["ports"] = {"4001/tcp": ("127.0.0.1", IBKR_GATEWAY_PORT)}

    self._container = self._docker.containers.run(**run_kwargs)

    # 3. Poll jusqu'à ce que le port réponde
    self.event_queue.put({"type": "status", "state": "starting_gateway"})
    gateway_host, gateway_port = self._gateway_endpoint()
    deadline = time.time() + IBKR_GATEWAY_START_TIMEOUT
    while time.time() < deadline:
        try:
            with socket.create_connection((gateway_host, gateway_port), timeout=2):
                break
        except OSError:
            time.sleep(2)
    else:
        self._stop_container()
        raise TimeoutError(
            f"ib-gateway n'a pas démarré dans les {IBKR_GATEWAY_START_TIMEOUT}s. "
            f"Consulter 'docker logs {self._container_name}'."
        )

    # 4. Connect ib_async
    self._ib = IB()
    self._ib.connect(gateway_host, gateway_port, clientId=1)
    self.event_queue.put({"type": "status", "state": "connected"})


def _remove_existing_container(self) -> None:
    try:
        old = self._docker.containers.get(self._container_name)
        old.stop(timeout=5)
        old.remove(force=True)
    except docker.errors.NotFound:
        pass


def _stop_container(self) -> None:
    if self._container is not None:
        try:
            self._container.stop(timeout=10)
        except docker.errors.APIError:
            pass
        self._container = None
```

- [ ] **Step 4 : Vérifier que les tests de connect passent**

```
pytest tests/test_connector_ibkr.py -v
```

Expected : tous PASS.

- [ ] **Step 5 : Commit**

```
git add src/connectors/ibkr.py tests/test_connector_ibkr.py
git commit -m "feat(ibkr): connect() orchestre ib-gateway avec hardening

Spawn du container via docker SDK avec :
- image pinnée par digest (supply chain)
- security_opt no-new-privileges
- mem_limit 2g, nano_cpus 2e9
- auto_remove + cleanup orphelin
- publication localhost only en dev, réseau interne en prod
Poll TCP jusqu'au readiness puis ib_async.IB().connect()."
```

---

## Task 8 : IBKR worker — cleanup d'orphelin + gestion timeout

**Files:**
- Modify: `tests/test_connector_ibkr.py`

- [ ] **Step 1 : Tests pour orphelin et timeout**

Ajouter à `tests/test_connector_ibkr.py` :

```python
def test_connect_removes_orphan_container_before_spawn():
    w = _make_worker("u1:ib")
    with patch("src.connectors.ibkr.docker") as mock_docker, \
         patch("src.connectors.ibkr.IB"), \
         patch("src.connectors.ibkr.socket.create_connection"), \
         patch("src.connectors.ibkr.time.sleep"):
        client = MagicMock()
        orphan = MagicMock()
        client.containers.get.return_value = orphan
        client.containers.run.return_value = MagicMock()
        mock_docker.from_env.return_value = client
        w.connect(_creds())
        orphan.stop.assert_called_once()
        orphan.remove.assert_called_once_with(force=True)


def test_connect_timeout_emits_error_without_creds():
    w = _make_worker("u1:ib")
    with patch("src.connectors.ibkr.docker") as mock_docker, \
         patch("src.connectors.ibkr.IB"), \
         patch("src.connectors.ibkr.socket.create_connection", side_effect=OSError("refused")), \
         patch("src.connectors.ibkr.time.sleep"), \
         patch("src.connectors.ibkr.time.time", side_effect=[0, 1000]):  # deadline dépassée
        client = MagicMock()
        client.containers.get.side_effect = _docker_errors_not_found()
        client.containers.run.return_value = MagicMock()
        mock_docker.from_env.return_value = client

        # connect() raise TimeoutError → le worker l'attrape via base.py run()
        # Ici on appelle connect() directement, donc on s'attend à TimeoutError
        import pytest as _pt
        with _pt.raises(TimeoutError) as excinfo:
            w.connect(_creds())
        msg = str(excinfo.value)
        assert "ib-gateway n'a pas démarré" in msg
        # Anti-leak: aucun credential dans le message d'erreur
        assert "charlie" not in msg
        assert "s3cret" not in msg
```

- [ ] **Step 2 : Vérifier que les tests passent** (le code actuel les satisfait déjà)

```
pytest tests/test_connector_ibkr.py -v
```

Expected : tous PASS. Si le test de timeout échoue à cause du mock `time.time`, ajuster le mock (side_effect peut nécessiter plus de valeurs : un call initial pour deadline, puis un check dans la boucle).

- [ ] **Step 3 : Si besoin, ajuster le test (timing mock)**

Si le test timeout échoue : remplacer `side_effect=[0, 1000]` par une approche qui retourne `0` au premier appel (init de `deadline`) puis `1000` aux appels suivants. Alternative plus robuste : `time.time` renvoie un itérateur infini commençant par 0 puis incrémentant rapidement.

```python
counter = [0]
def fake_time():
    counter[0] += 100
    return counter[0]
with patch("src.connectors.ibkr.time.time", side_effect=fake_time):
    ...
```

- [ ] **Step 4 : Commit**

```
git add tests/test_connector_ibkr.py
git commit -m "test(ibkr): orphelin cleanup + timeout sans leak de creds"
```

---

## Task 9 : IBKR worker — `disconnect()` + audit log

**Files:**
- Modify: `src/connectors/ibkr.py::disconnect`
- Modify: `src/connectors/ibkr.py::connect` (ajout log)
- Test: `tests/test_connector_ibkr.py`

- [ ] **Step 1 : Tests disconnect + audit log**

Ajouter :

```python
def test_disconnect_stops_ib_and_container():
    w = _make_worker("u1:ib")
    with _patch_connect_dependencies() as ctx:
        w.connect(_creds())
    w.disconnect()
    ctx["ib"].disconnect.assert_called_once()
    ctx["container"].stop.assert_called_once()


def test_disconnect_idempotent_when_never_connected():
    w = _make_worker("u1:ib")
    # Pas de connect avant
    w.disconnect()  # Ne doit pas lever


def test_connect_logs_audit_event_without_creds(caplog):
    import logging as _log
    w = _make_worker("u1:ib")
    with _patch_connect_dependencies() as _ctx:
        with caplog.at_level(_log.INFO, logger="src.connectors.ibkr"):
            w.connect(_creds())
    audit_lines = [r.getMessage() for r in caplog.records if "IBKR" in r.getMessage()]
    assert any("action=connect" in line for line in audit_lines)
    # Anti-leak
    for line in audit_lines:
        assert "charlie" not in line
        assert "s3cret" not in line


def test_disconnect_logs_audit_event(caplog):
    import logging as _log
    w = _make_worker("u1:ib")
    with _patch_connect_dependencies() as _ctx:
        w.connect(_creds())
    with caplog.at_level(_log.INFO, logger="src.connectors.ibkr"):
        w.disconnect()
    audit_lines = [r.getMessage() for r in caplog.records if "IBKR" in r.getMessage()]
    assert any("action=disconnect" in line for line in audit_lines)
```

- [ ] **Step 2 : Vérifier l'échec**

```
pytest tests/test_connector_ibkr.py::test_disconnect_stops_ib_and_container tests/test_connector_ibkr.py::test_connect_logs_audit_event_without_creds -v
```

Expected : FAIL (`disconnect` raise `NotImplementedError`, pas de log).

- [ ] **Step 3 : Implémenter `disconnect()` et les logs**

Dans `src/connectors/ibkr.py`, remplacer `disconnect()` par :

```python
def disconnect(self) -> None:
    try:
        if self._ib is not None and self._ib.isConnected():
            self._ib.disconnect()
    except Exception:
        pass
    self._ib = None
    self._stop_container()
    log.info("IBKR: connector=%s action=disconnect result=ok", self._safe_key())
```

Et ajouter des `log.info` autour du `connect()` réussi. Au tout début de `connect()` (avant le spawn) :

```python
log.info("IBKR: connector=%s action=connect result=start", self._safe_key())
```

Juste avant l'`event_queue.put({"type": "status", "state": "connected"})` :

```python
log.info("IBKR: connector=%s action=connect result=ok", self._safe_key())
```

Aucun credential (ni username ni password) n'apparaît dans les logs.

- [ ] **Step 4 : Vérifier que les tests passent**

```
pytest tests/test_connector_ibkr.py -v
```

Expected : tous PASS.

- [ ] **Step 5 : Commit**

```
git add src/connectors/ibkr.py tests/test_connector_ibkr.py
git commit -m "feat(ibkr): disconnect() + audit log (sans creds)

disconnect() ferme ib_async puis stoppe le container.
Logs structurés connector=X action=connect|disconnect result=ok.
Aucun credential dans les messages (testé)."
```

---

## Task 10 : IBKR worker — test anti-leak sur IB().connect() échoué

**Files:**
- Modify: `tests/test_connector_ibkr.py`

- [ ] **Step 1 : Test que bad creds n'apparaissent pas dans les messages d'erreur**

```python
def test_connect_bad_creds_error_does_not_leak():
    w = _make_worker("u1:ib")
    with patch("src.connectors.ibkr.docker") as mock_docker, \
         patch("src.connectors.ibkr.IB") as mock_ib_cls, \
         patch("src.connectors.ibkr.socket.create_connection"), \
         patch("src.connectors.ibkr.time.sleep"):
        client = MagicMock()
        client.containers.get.side_effect = _docker_errors_not_found()
        client.containers.run.return_value = MagicMock()
        mock_docker.from_env.return_value = client
        ib = MagicMock()
        ib.connect.side_effect = ConnectionError("auth failed")
        mock_ib_cls.return_value = ib

        import pytest as _pt
        with _pt.raises(ConnectionError) as excinfo:
            w.connect(_creds())
        msg = str(excinfo.value)
        assert "charlie" not in msg
        assert "s3cret" not in msg
```

- [ ] **Step 2 : Vérifier que le test passe** (comportement déjà correct — `ConnectionError` d'ib_async ne contient pas les creds)

```
pytest tests/test_connector_ibkr.py::test_connect_bad_creds_error_does_not_leak -v
```

Expected : PASS. Si FAIL (leak), corriger en enveloppant `IB().connect()` et en ré-raisant une exception sanitisée.

- [ ] **Step 3 : Commit**

```
git add tests/test_connector_ibkr.py
git commit -m "test(ibkr): régression anti-leak sur connect bad creds"
```

---

## Task 11 : docker-compose — network dédié, suppression service ib-gateway, socket mount

**Files:**
- Modify: `docker-compose.yml`

- [ ] **Step 1 : Modifier `docker-compose.yml`**

Appliquer ces changements :

1. **Retirer le bloc `ib-gateway`** (lignes 65-78) intégralement.
2. **Retirer `ib-gateway-data`** de la section `volumes:` (ligne 83).
3. **Ajouter une section `networks:`** en bas du fichier :

```yaml
networks:
  mm-ledger-net:
    name: mm-ledger-net
    driver: bridge
```

4. **Étendre le service `app`** pour :
   - Rejoindre `mm-ledger-net`
   - Monter le docker socket

```yaml
app:
  image: ghcr.io/marius-courquin/mm-ledger:latest
  ports:
    - "8000:8000"
  volumes:
    - data:/app/data
    - /var/run/docker.sock:/var/run/docker.sock
  networks:
    - mm-ledger-net
  restart: unless-stopped
  healthcheck:
    test: ["CMD", "python3", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/auth/status')"]
    interval: 30s
    timeout: 5s
    retries: 3
    start_period: 10s
```

- [ ] **Step 2 : Valider la syntaxe compose**

```
docker compose config
```

Expected : sortie YAML valide listant `app`, `watchtower`, `wg-easy`, `duckdns` (pas `ib-gateway`) et la section `networks`.

- [ ] **Step 3 : Commit**

```
git add docker-compose.yml
git commit -m "chore(compose): suppression service ib-gateway + network dédié

- ib-gateway n'est plus un service statique (orchestré à la volée par l'app)
- app rejoint mm-ledger-net pour parler au container ib-gateway en prod
- app monte /var/run/docker.sock pour piloter le docker daemon
- Volume ib-gateway-data retiré (état IBC recréé à chaque connect)"
```

---

## Task 12 : Validation end-to-end manuelle

**Files:** (aucun — tests runtime)

- [ ] **Step 1 : Lancer le backend en dev**

```
./start.sh
```

Expected : démarre sur `:8000` sans erreur d'import.

- [ ] **Step 2 : Lancer le front en dev**

Dans un autre terminal :

```
cd frontend && bun run dev
```

Expected : Vite démarre sur `:3000`.

- [ ] **Step 3 : Tester la UX IBKR**

1. Ouvrir `http://localhost:3000`, se connecter, déverrouiller le vault.
2. Ajouter un connecteur IBKR → le formulaire doit montrer 3 champs (username, password, trading_mode avec live/paper).
3. Saisir des creds IBKR de paper (ou live), cliquer « Se connecter ».
4. La carte doit passer par `starting_gateway` (jaune, "Démarrage gateway...") pendant ~30-90s puis `connected` (vert).
5. Aller voir le portfolio / dashboard → balances IBKR présents.

**En cas d'erreur** (creds invalides, gateway timeout, etc.) :
- La carte doit passer en `error` (rouge, badge "Erreur")
- Sous la carte, le `detail` doit apparaître en message rouge (ex. "ib-gateway n'a pas démarré dans les 90s.")
- Pas de "stuck in connecting" possible.

- [ ] **Step 4 : Tester la robustesse du cleanup**

1. Connecter IBKR → attendre que le container tourne (`docker ps | grep mm-ledger-ibkr`).
2. `Ctrl+C` sur uvicorn.
3. Vérifier que le container s'arrête (`docker ps | grep mm-ledger-ibkr` → vide après 10-15s).
4. Relancer, reconnecter → pas de conflit de nom.

- [ ] **Step 5 : Documenter les résultats**

Si un cas échoue, noter dans un commit follow-up ou ouvrir un TODO dans le spec. Pas de commit à cette étape si tout marche (validation only).

---

## Task 13 : README + CLAUDE.md — documenter la trust boundary et le nouveau flow

**Files:**
- Modify: `README.md`
- Modify: `CLAUDE.md` (déjà à jour sur la règle vault-first, compléter la section IBKR)

- [ ] **Step 1 : Ajouter une section IBKR dans `README.md`**

Après la section « Premier lancement », insérer :

```markdown
## IBKR — flux de connexion

Le connecteur IBKR n'a **plus besoin** de remplir `.env` avec `IBKR_USERNAME` / `IBKR_PASSWORD`.
Les credentials sont stockés dans le vault chiffré de l'utilisateur (SQLCipher, déverrouillé au login).

Flow :
1. Déverrouiller le vault.
2. Créer un connecteur IBKR → saisir username / password / trading_mode (live ou paper).
3. Cliquer « Se connecter » — l'app spawn automatiquement le container `ib-gateway` avec les creds injectés en env, attend 60-90s le démarrage, puis se connecte via `ib_async`.
4. Au disconnect / shutdown, le container est stoppé et supprimé (auto_remove).

Pré-requis : le docker daemon doit être accessible depuis l'app (mount `/var/run/docker.sock`).
C'est déjà le cas dans `docker-compose.yml`.

### Trust boundary

L'app monte `/var/run/docker.sock` pour orchestrer `ib-gateway`. Cela donne à l'app
des droits équivalents à root sur l'hôte. Ce pattern était déjà utilisé par
`watchtower`. Si vous exposez l'app sur un réseau non-maîtrisé, considérez :
- un reverse proxy avec auth forte devant `:8000`,
- un VPN (profile `vpn` de `docker-compose.yml` avec WireGuard),
- restreindre les sources autorisées à se connecter.
```

- [ ] **Step 2 : Mettre à jour la table des connecteurs dans `CLAUDE.md`**

Remplacer la ligne IBKR de la table connecteurs (ligne ~86) par :

```markdown
| `ibkr` | `ib_async` + `docker` SDK | OK | App spawn `ib-gateway` à la volée avec creds du vault, port binding `127.0.0.1` en dev, réseau interne en prod, digest pinné |
```

Et l'entrée Gotchas IBKR (ligne ~101) par :

```markdown
- **IBKR** : l'app orchestre le container `ib-gateway` via le SDK docker au moment du `connect`. Creds (username/password/trading_mode) dans le vault chiffré — jamais en `.env`. Démarrage 60-90s (état intermédiaire `starting_gateway`). Voir `docs/superpowers/specs/2026-04-22-ibkr-vault-first-design.md`.
```

- [ ] **Step 3 : Commit**

```
git add README.md CLAUDE.md
git commit -m "docs: IBKR vault-first — README + CLAUDE.md mis à jour

Nouveau flow documenté : credentials dans le vault, container
ib-gateway orchestré par l'app. Trust boundary docker.sock
explicitée dans README."
```

---

## Self-review (à lire avant d'exécuter)

- **Couverture spec** : les 8 sections du design sont couvertes — vault schema (T3), worker (T6/T7/T9), manager fix (T1/T2), compose (T11), deps (T5), front (T4), `.env` (T11 retire résiduel + T13 README), sécurité hardening (T7 + T9 + T10).
- **Tests anti-leak** : T8 (timeout) + T9 (audit log) + T10 (bad creds) — chacun avec assertion explicite sur l'absence de `charlie` / `s3cret`.
- **Digest pinning** : T5 résout, T6 le colle dans la constante. À re-valider avant prod.
- **Risques d'exécution** :
  - Task 7 : `patch("src.connectors.ibkr.docker")` suppose `import docker` au module top — confirmé dans T7 Step 3.
  - Task 8 : mock `time.time` peut être délicat ; workaround fourni.
  - Task 12 : dépend de l'existence d'un compte IBKR et d'un docker daemon local ; pas bloquant pour les autres tasks.
  - Task 11 : modifie `docker-compose.yml` qui tourne en prod via watchtower auto-deploy. À ne merger que quand T1-T10 sont verts en CI, sinon risque de déployer un service cassé.
- **Ordre d'exécution** : les tasks 1-10 sont indépendantes de docker-compose (T11). T12 nécessite T1-T11 merged. T13 peut être fait en parallèle de T12.
