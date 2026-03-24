# mm-ledger — Python Backend Architecture

> Spec validée le 2026-03-24. Backend Python full-stack, agnostique du frontend.

## Vue d'ensemble

Migration du backend JS/TS (Bun) vers Python. Un seul container Docker expose une API REST (FastAPI) qui orchestre 3 types de connecteurs financiers (Trade Republic, Interactive Brokers, Banques FR) via des worker processes isolés. Les données sont persistées en SQLite, les credentials dans un vault SQLCipher déverrouillé par master password au démarrage.

```
┌─────────────────────────────────────────────────────────────┐
│                    Docker Compose                            │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │                 api (container)                         │  │
│  │                                                        │  │
│  │  FastAPI (uvicorn)                                     │  │
│  │  ├── /api/connectors/*    ← CRUD + lifecycle workers   │  │
│  │  ├── /api/accounts/*      ← balances courantes         │  │
│  │  ├── /api/portfolio/*     ← positions                  │  │
│  │  ├── /api/snapshots/*     ← historique quotidien       │  │
│  │  ├── /api/transactions/*  ← mouvements                 │  │
│  │  ├── /api/performance/*   ← P&L                        │  │
│  │  ├── /api/vault/*         ← unlock/lock/setup          │  │
│  │  ├── /api/scheduler/*     ← status crons               │  │
│  │  └── /api/health          ← healthcheck                │  │
│  │                                                        │  │
│  │  ConnectorManager                                      │  │
│  │  ├── TradeRepublicWorker  (subprocess, WebSocket)      │  │
│  │  ├── IBKRWorker           (subprocess, TCP → Gateway)  │  │
│  │  └── WoobWorker           (subprocess, sync)           │  │
│  │                                                        │  │
│  │  APScheduler (cron 23h00 snapshot, lundi perf)         │  │
│  │                                                        │  │
│  │  Vault (SQLCipher) ──── data/vault.db                  │  │
│  │  DB    (SQLite)    ──── data/ledger.db                 │  │
│  └──────────────────────┬─────────────────────────────────┘  │
│                         │ volume: data                        │
│  ┌──────────────────────┴─────────────────────────────────┐  │
│  │           ib-gateway (container)                        │  │
│  │           TCP :4001 (live) / :4002 (paper)              │  │
│  └─────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
         ▲
         │ WireGuard VPN
         │
    Frontend (n'importe quel client)
```

---

## Structure du projet

```
mm-ledger/
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
├── alembic/
│   ├── alembic.ini
│   └── versions/
├── src/
│   ├── main.py                  # Entrypoint FastAPI (uvicorn)
│   ├── config.py                # Settings (env vars, paths)
│   ├── api/
│   │   ├── router.py            # Montage des sous-routers
│   │   ├── connectors.py        # CRUD connecteurs + status workers
│   │   ├── accounts.py          # Comptes, balances
│   │   ├── portfolio.py         # Positions, performance
│   │   ├── snapshots.py         # Historique, snapshots manuels
│   │   ├── transactions.py      # Mouvements
│   │   ├── vault_routes.py      # Setup / unlock / lock
│   │   ├── scheduler_routes.py  # Status des crons
│   │   └── auth.py              # 2FA relay
│   ├── connectors/
│   │   ├── base.py              # ConnectorWorker (classe abstraite)
│   │   ├── trade_republic.py    # Worker TR (websocket + WAF bypass)
│   │   ├── ibkr.py              # Worker IBKR (ib_insync)
│   │   └── woob_bank.py         # Worker Woob (banques FR)
│   ├── patches/
│   │   └── woob_banquepopulaire/
│   │       ├── README.md            # Doc des patches (quoi, pourquoi, quand supprimer)
│   │       ├── browser.py           # Patch OAuth: fallback xld-keys.json
│   │       └── pages.py             # Patch clavier virtuel: OCR pytesseract
│   ├── manager.py               # ConnectorManager (spawn/stop/restart)
│   ├── scheduler.py             # APScheduler config
│   ├── vault.py                 # SQLCipher vault
│   ├── db/
│   │   ├── engine.py            # SQLite engine + session factory
│   │   ├── models.py            # SQLAlchemy models
│   │   └── queries.py           # Requêtes courantes
│   └── schemas/
│       ├── connector.py         # Pydantic schemas connecteurs
│       ├── account.py           # Pydantic schemas comptes
│       ├── position.py          # Pydantic schemas positions
│       └── snapshot.py          # Pydantic schemas snapshots
├── tests/
└── data/
    ├── ledger.db                # SQLite données
    └── vault.db                 # SQLCipher credentials
```

---

## Connector Workers & Communication

### Classe abstraite

Chaque connecteur tourne dans son propre `multiprocessing.Process`. Communication via `multiprocessing.Queue`.

**Intégration async :** les `multiprocessing.Queue` sont bloquantes. Le `ConnectorManager` utilise un `asyncio.Task` de fond qui drain les event_queues via `get_nowait()` (polling 100ms) et pousse les events dans une `asyncio.Queue` consommable par les route handlers FastAPI sans bloquer l'event loop.

```python
class ConnectorWorker(ABC):
    """Tourne dans son propre process."""

    def __init__(self, cmd_queue: Queue, event_queue: Queue, config: dict):
        self.cmd_queue = cmd_queue    # API → Worker (commandes)
        self.event_queue = event_queue # Worker → API (events/data)

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
        """Boucle principale : écoute cmd_queue, dispatch vers les méthodes abstraites.
        Chaque méthode retourne des données brutes. run() wrappe dans l'enveloppe event."""
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
                # Les méthodes connect/disconnect/submit_2fa retournent None → event status
                # Les méthodes fetch_* retournent des données → event typé avec data
                if data is not None:
                    event_type = cmd["type"].replace("fetch_", "")  # "fetch_accounts" → "accounts"
                    self.event_queue.put({"type": event_type, "data": data})
            except Exception as e:
                self.event_queue.put({"type": "error", "message": str(e)})
```

### Protocole de messages

**Commandes (API → Worker) :**

```json
{"type": "connect", "credentials": {"phone": "...", "pin": "..."}}
{"type": "disconnect"}
{"type": "fetch_accounts"}
{"type": "fetch_positions"}
{"type": "fetch_balances"}
{"type": "fetch_transactions"}
{"type": "submit_2fa", "code": "123456"}
{"type": "shutdown"}
```

**Events (Worker → API) :**

```json
{"type": "status", "state": "connected", "detail": "..."}
{"type": "status", "state": "waiting_2fa", "detail": "Confirmez sur Secur'Pass"}
{"type": "accounts", "data": [...]}
{"type": "positions", "data": [...]}
{"type": "balances", "data": [...]}
{"type": "transactions", "data": [...]}
{"type": "error", "message": "..."}
```

States possibles : `disconnected` | `connecting` | `connected` | `waiting_2fa` | `error`

### ConnectorManager

```python
class ConnectorManager:
    workers: dict[str, WorkerHandle]  # connector_id → {process, cmd_q, event_q, state}

    def spawn(self, connector_id: str, connector_type: str, credentials: dict): ...
    def stop(self, connector_id: str): ...
    def restart(self, connector_id: str): ...
    def send_command(self, connector_id: str, cmd: dict): ...
    def collect_events(self) -> list[Event]: ...
    def health_check(self) -> dict[str, str]: ...
```

### Spécificités par connecteur

| Worker | Comportement |
|---|---|
| **TradeRepublicWorker** | Event loop asyncio interne. WebSocket persistant. WAF bypass via Selenium/Chromium headless. Push updates de prix en continu. |
| **IBKRWorker** | Connexion TCP à IB Gateway (container séparé). `ib_async` avec sa propre event loop. Souscrit aux updates positions/balances en continu. |
| **WoobWorker** | Connexion ponctuelle (pas de stream). Charge le backend Woob, gère la 2FA. Appels synchrones. Se déconnecte après fetch. Applique les patches vendorisés au démarrage. |

### Patches Woob Banque Populaire

Le module upstream `banquepopulaire` (Woob 3.7) est cassé. Deux patches sont nécessaires, vendorisés dans `src/patches/woob_banquepopulaire/` :

**Patch 1 — OAuth client IDs (`browser.py`)** : BP a changé sa page de login. Les client IDs OAuth ne sont plus dans les chunks JS mais dans `xld-keys.json`. Le patch ajoute un fallback qui fetch ce JSON.

**Patch 2 — Clavier virtuel (`pages.py`)** : Le site génère des images de chiffres légèrement différentes à chaque session (anti-scraping). Les hashes MD5 ne matchent plus. Le patch remplace le hash matching par de l'OCR via pytesseract (tesseract-ocr).

**Mécanisme d'application :** Le `WoobWorker` copie les fichiers patchés dans le dossier modules Woob (`~/.local/share/woob/modules/`) au démarrage, avant de charger le backend. Cela survit aux `woob update` puisqu'on ré-applique à chaque start.

**Quand supprimer :** Quand Woob upstream intègre les fixes (surveiller le GitLab Woob). Le README dans le dossier patches documente les issues upstream à suivre.

### Watchdog

Le `ConnectorManager` vérifie toutes les 30s si les worker processes sont vivants (`process.is_alive()`). Si un worker crash (OOM, exception non catchée) :
1. Son état passe à `error` avec le detail du crash
2. Pas de restart automatique — le frontend/user décide via `POST /api/connectors/{id}/restart`
3. L'event est loggé

Pour les déconnexions réseau (WS TR qui drop, TCP IBKR timeout), c'est le worker lui-même qui gère la reconnexion interne et push un event `{"type": "status", "state": "connecting"}`.

### 2FA

Quand un worker a besoin d'un code 2FA :
1. Worker push `{"type": "status", "state": "waiting_2fa", "detail": "..."}` dans event_queue
2. L'API expose cet état via `GET /api/connectors/{id}/status`
3. Le frontend affiche le prompt
4. L'utilisateur soumet le code
5. `POST /api/connectors/{id}/2fa` envoie `{"type": "submit_2fa", "code": "..."}` dans la cmd_queue

---

## Base de données

### `vault.db` — Credentials (SQLCipher, AES-256)

Déverrouillé au démarrage par master password.

```sql
CREATE TABLE credentials (
    connector_id TEXT PRIMARY KEY,
    connector_type TEXT NOT NULL,     -- 'trade_republic', 'ibkr', 'woob_bank'
    label TEXT,
    data JSON NOT NULL,               -- JSON plaintext (login, password, region, etc.) — le chiffrement est géré par SQLCipher au niveau page, pas applicatif
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);
```

### `ledger.db` — Données (SQLite)

```sql
CREATE TABLE connectors (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    label TEXT,
    config JSON,                      -- config non-sensible (region, host, port...)
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE accounts (
    id TEXT PRIMARY KEY,              -- ex: 'tr_CTO_EUR', 'bp_00012345'
    connector_id TEXT REFERENCES connectors(id),
    name TEXT,
    type TEXT,                        -- 'cto', 'pea', 'checking', 'savings', 'margin'
    currency TEXT DEFAULT 'EUR',
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE balance_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id TEXT REFERENCES accounts(id),
    date TEXT NOT NULL,                -- 'YYYY-MM-DD'
    cash REAL,
    positions_value REAL,
    total_value REAL,
    currency TEXT DEFAULT 'EUR',
    positions JSON,                    -- [{symbol, qty, price, value}, ...]
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(account_id, date)
);

CREATE TABLE transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id TEXT REFERENCES accounts(id),
    date TEXT NOT NULL,
    type TEXT,                         -- 'buy', 'sell', 'dividend', 'fee', 'transfer', 'interest'
    label TEXT,
    amount REAL,
    currency TEXT DEFAULT 'EUR',
    instrument TEXT,                    -- ISIN ou symbol
    quantity REAL,
    price REAL,
    raw JSON,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE performance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    connector_id TEXT REFERENCES connectors(id),
    period_start TEXT NOT NULL,
    period_end TEXT NOT NULL,
    total_value REAL,
    total_invested REAL,
    pnl REAL,
    pnl_pct REAL,
    breakdown JSON,
    UNIQUE(connector_id, period_start)
);

-- Index
CREATE INDEX idx_snapshots_account_date ON balance_snapshots(account_id, date);
CREATE INDEX idx_transactions_account_date ON transactions(account_id, date);
CREATE INDEX idx_performance_connector_period ON performance(connector_id, period_start);

-- Activer WAL pour les écritures concurrentes (scheduler + API)
PRAGMA journal_mode=WAL;
```

Migrations gérées par Alembic. WAL mode activé à l'initialisation de l'engine SQLAlchemy pour éviter les `SQLITE_BUSY` lors d'écritures concurrentes (snapshot scheduler + trigger API manuel simultanés).

---

## Vault & Sécurité

### Déverrouillage

```
Container start
      │
      ▼
Premier lancement ?
  └─ POST /api/vault/setup {password: "..."}  → crée vault.db chiffré
      │
Lancement suivant ?
  └─ POST /api/vault/unlock {password: "..."}  → déverrouille en RAM
```

Le master password n'est jamais stocké sur disque. Le transit est sécurisé par le VPN WireGuard.

### Module vault.py

```python
class Vault:
    def __init__(self, path: str):
        self._conn = None

    def unlock(self, master_password: str) -> bool: ...
    def lock(self) -> None: ...
    def store(self, connector_id: str, connector_type: str, label: str, credentials: dict) -> None: ...
    def retrieve(self, connector_id: str) -> dict | None: ...
    def delete(self, connector_id: str) -> None: ...
    def list_connectors(self) -> list[dict]: ...

    @property
    def is_unlocked(self) -> bool: ...
```

### Règles de sécurité

| Règle | Implémentation |
|---|---|
| Credentials jamais dans les logs | Pydantic `repr=False` sur champs sensibles |
| Credentials jamais dans les réponses API | Retourne `{id, type, label, status}` uniquement |
| Master password jamais sur disque | Saisie via frontend, RAM uniquement |
| Vault lockable à chaud | `POST /api/vault/lock` |
| Sessions en RAM uniquement | Tokens WS/TCP meurent avec les workers |
| CORS restreint | Origines autorisées explicitement |
| Rate limiting 2FA | Max 5 tentatives / 5 min par connecteur |
| Rate limiting vault unlock | Backoff exponentiel : 1s, 2s, 4s, 8s... après 3 échecs. Reset après succès |
| Scope single-user | Pas d'auth API — accès contrôlé par VPN uniquement. Multi-user nécessiterait des tokens/sessions |
| IBKR credentials (trade-off) | Les credentials IBKR sont passés en env vars au container IB Gateway (imposé par l'image Docker). Ils apparaissent dans `docker inspect`. C'est un compromis accepté — le container IB Gateway ne supporte pas d'autre mécanisme. Le vault stocke uniquement `{host, port}` pour le connecteur API |

---

## Scheduler

APScheduler intégré au lifespan FastAPI.

| Job | Schedule | Action |
|---|---|---|
| `daily_snapshot` | Tous les jours 23h00 | Fetch balances + positions → UPSERT balance_snapshots |
| `weekly_performance` | Lundi 00h05 | Calcule P&L semaine → INSERT performance |

Logique :
- Pour chaque worker connecté : `fetch_balances` + `fetch_positions` (timeout 60s)
- Connecteur déconnecté → skip + warning, pas de crash
- UPSERT via `INSERT ... ON CONFLICT DO UPDATE`

Déclenchable aussi via API (`POST /api/snapshots/trigger`).

---

## Docker

### docker-compose.yml

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

### Dockerfile

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

EXPOSE 8000
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Dépendances (pyproject.toml)

```toml
[project]
name = "mm-ledger"
requires-python = ">=3.12"
dependencies = [
    "fastapi",
    "uvicorn[standard]",
    "pydantic>=2",
    "sqlalchemy>=2",
    "alembic",
    "sqlcipher3",
    "websockets",
    "requests",
    "selenium",
    "ib_async",                    # Interactive Brokers (fork maintenu de ib_insync)
    "woob",
    "pytesseract",                 # OCR pour clavier virtuel BP
    "Pillow",                      # Preprocessing images clavier virtuel
    "apscheduler>=3.10,<4",        # APScheduler 4.x a une API incompatible
    "pandas",
]
```

---

## Référence API — Documentation Frontend

> **Pagination :** les endpoints qui retournent des listes (`/api/transactions`, `/api/snapshots`, `/api/performance`) supportent `?limit=50&offset=0` (défaut : limit=100). La réponse inclut un header `X-Total-Count`.
>
> **Dates optionnelles :** `from` et `to` sont optionnels. Sans `from`, défaut = 30 jours en arrière. Sans `to`, défaut = aujourd'hui.
>
> **Live updates :** `GET /api/events` (SSE) pour recevoir les events en streaming sans polling. Voir section dédiée.

### Vault

#### `POST /api/vault/setup`

Premier lancement. Crée le vault chiffré.

**Request:**
```json
{"password": "my_master_password"}
```

**Response 201:**
```json
{"status": "created"}
```

**Response 409:** vault déjà existant.

---

#### `GET /api/vault/status`

Etat du vault. Permet au frontend de savoir quel écran afficher au démarrage.

**Response 200:**
```json
{"state": "uninitialized"}
```

States possibles : `uninitialized` (premier lancement, afficher setup) | `locked` (afficher unlock) | `unlocked` (accès normal).

---

#### `POST /api/vault/unlock`

Déverrouille le vault pour la session.

**Request:**
```json
{"password": "my_master_password"}
```

**Response 200:**
```json
{"status": "unlocked"}
```

**Response 401:** mauvais password.
**Response 429:** trop de tentatives (backoff exponentiel après 3 échecs).

---

#### `POST /api/vault/change-password`

Change le master password du vault. Le vault doit être unlocked.

**Request:**
```json
{"old_password": "ancien", "new_password": "nouveau"}
```

**Response 200:**
```json
{"status": "changed"}
```

**Response 401:** ancien password incorrect.
**Response 423:** vault locked.

---

#### `POST /api/vault/lock`

Verrouille le vault. Les workers connectés continuent, mais aucun nouveau `connect` n'est possible.

**Response 200:**
```json
{"status": "locked"}
```

---

### Connecteurs

#### `GET /api/connectors/types`

Liste les types de connecteurs supportés et leurs champs credentials. Utile pour construire dynamiquement les formulaires frontend.

**Response 200:**
```json
[
  {
    "type": "trade_republic",
    "label": "Trade Republic",
    "credential_fields": [
      {"name": "phone", "type": "text", "required": true, "placeholder": "+33612345678"},
      {"name": "pin", "type": "password", "required": true, "placeholder": "1234"}
    ],
    "config_fields": [],
    "supports_2fa": true,
    "supports_streaming": true
  },
  {
    "type": "ibkr",
    "label": "Interactive Brokers",
    "credential_fields": [],
    "config_fields": [
      {"name": "host", "type": "text", "required": true, "default": "127.0.0.1"},
      {"name": "port", "type": "number", "required": true, "default": 4001}
    ],
    "supports_2fa": false,
    "supports_streaming": true
  },
  {
    "type": "woob_bank",
    "label": "Banque (Woob)",
    "credential_fields": [
      {"name": "login", "type": "text", "required": true},
      {"name": "password", "type": "password", "required": true},
      {"name": "bank_module", "type": "text", "required": true, "default": "banquepopulaire"},
      {"name": "region", "type": "text", "required": false, "placeholder": "10207"}
    ],
    "config_fields": [],
    "supports_2fa": true,
    "supports_streaming": false
  }
]
```

---

#### `GET /api/connectors`

Liste tous les connecteurs avec l'état de leur worker.

**Response 200:**
```json
[
  {
    "id": "tr_charles",
    "type": "trade_republic",
    "label": "TR Charles",
    "config": {},
    "worker": {
      "state": "connected",
      "pid": 12345,
      "uptime_seconds": 3600,
      "last_error": null,
      "accounts_count": 2
    }
  },
  {
    "id": "bp_rives",
    "type": "woob_bank",
    "label": "BP Rives de Paris",
    "config": {"region": "10207"},
    "worker": {
      "state": "waiting_2fa",
      "detail": "Confirmez sur Secur'Pass"
    }
  },
  {
    "id": "ibkr_main",
    "type": "ibkr",
    "label": "IBKR Principal",
    "config": {"host": "127.0.0.1", "port": 4001},
    "worker": {
      "state": "disconnected"
    }
  }
]
```

---

#### `POST /api/connectors`

Enregistre un nouveau connecteur. Stocke les credentials dans le vault.

**Request:**
```json
{
  "id": "tr_charles",
  "type": "trade_republic",
  "label": "TR Charles",
  "credentials": {
    "phone": "+33612345678",
    "pin": "1234"
  },
  "config": {}
}
```

**Response 201:**
```json
{
  "id": "tr_charles",
  "type": "trade_republic",
  "label": "TR Charles"
}
```

**Response 423:** vault locked.

Types supportés et champs credentials :

| type | credentials |
|---|---|
| `trade_republic` | `{phone, pin}` |
| `ibkr` | `{host, port}` (auth gérée par le container IB Gateway) |
| `woob_bank` | `{login, password, bank_module, region}` |

---

#### `PUT /api/connectors/{id}`

Met à jour config et/ou credentials.

**Request:**
```json
{
  "label": "TR Charles CTO+PEA",
  "credentials": {"phone": "+33612345678", "pin": "5678"}
}
```

**Response 200:**
```json
{"id": "tr_charles", "type": "trade_republic", "label": "TR Charles CTO+PEA"}
```

---

#### `DELETE /api/connectors/{id}`

Supprime le connecteur, ses credentials du vault, et stop le worker si actif.

**Response 204:** (no content)

---

#### `GET /api/connectors/{id}/status`

Etat détaillé d'un worker.

**Response 200:**
```json
{
  "id": "tr_charles",
  "state": "connected",
  "pid": 12345,
  "uptime_seconds": 7200,
  "last_error": null,
  "last_fetch": "2026-03-24T22:00:00Z",
  "accounts_count": 2,
  "accounts": ["CTO_EUR", "PEA_EUR"]
}
```

---

#### `POST /api/connectors/{id}/connect`

Spawn le worker et lance la connexion. Les credentials sont lus depuis le vault.

**Response 202:**
```json
{"status": "connecting"}
```

**Response 423:** vault locked.
**Response 404:** connecteur inconnu.

---

#### `POST /api/connectors/{id}/disconnect`

Stop le worker.

**Response 200:**
```json
{"status": "disconnected"}
```

---

#### `POST /api/connectors/{id}/restart`

Stop + spawn.

**Response 202:**
```json
{"status": "connecting"}
```

---

#### `POST /api/connectors/{id}/2fa`

Soumet un code 2FA au worker en attente.

**Request:**
```json
{"code": "123456"}
```

**Response 200:**
```json
{"status": "submitted"}
```

**Response 409:** worker pas en état `waiting_2fa`.
**Response 429:** rate limit (max 5 tentatives / 5 min).

---

### Comptes & Balances

#### `GET /api/accounts`

Tous les comptes de tous les connecteurs.

**Query params:** `?connector_id=tr_charles` (optionnel, filtre)

**Response 200:**
```json
[
  {
    "id": "tr_CTO_EUR",
    "connector_id": "tr_charles",
    "name": "Compte-Titres Ordinaire",
    "type": "cto",
    "currency": "EUR"
  },
  {
    "id": "tr_PEA_EUR",
    "connector_id": "tr_charles",
    "name": "Plan Epargne Actions",
    "type": "pea",
    "currency": "EUR"
  },
  {
    "id": "bp_00012345",
    "connector_id": "bp_rives",
    "name": "Compte Courant",
    "type": "checking",
    "currency": "EUR"
  }
]
```

---

#### `GET /api/accounts/{id}/balance`

Balance courante d'un compte. Retourne la dernière valeur cachée en mémoire (mise à jour en continu par les workers streaming TR/IBKR, ou au dernier fetch pour Woob). Le champ `updated_at` indique la fraîcheur — le frontend peut afficher "il y a X min" pour signaler des données potentiellement stales.

**Response 200:**
```json
{
  "account_id": "tr_CTO_EUR",
  "cash": 1234.56,
  "positions_value": 15678.90,
  "total_value": 16913.46,
  "currency": "EUR",
  "updated_at": "2026-03-24T14:30:00Z"
}
```

---

### Portfolio

#### `GET /api/portfolio`

Toutes les positions agrégées (tous connecteurs).

**Query params:** `?connector_id=tr_charles` (optionnel)

Les champs `total_invested`, `total_pnl`, `total_pnl_pct` sont **calculés à la volée** à partir des positions (quantity * avg_price pour invested, current_price - avg_price pour P&L). Ils ne sont pas stockés en DB.

**Response 200:**
```json
{
  "total_value": 45000.00,
  "total_invested": 38000.00,
  "total_pnl": 7000.00,
  "total_pnl_pct": 18.42,
  "currency": "EUR",
  "positions": [
    {
      "connector_id": "tr_charles",
      "account_id": "tr_CTO_EUR",
      "instrument": "IE00B4L5Y983",
      "name": "iShares Core MSCI World",
      "symbol": "IWDA",
      "category": "etf",
      "quantity": 50.0,
      "avg_price": 76.50,
      "current_price": 82.30,
      "value": 4115.00,
      "pnl": 290.00,
      "pnl_pct": 7.58,
      "currency": "EUR"
    }
  ]
}
```

---

#### `GET /api/portfolio/{connector_id}`

Positions d'un connecteur spécifique. Même format que ci-dessus.

---

### Snapshots

#### `GET /api/snapshots`

Historique des snapshots quotidiens.

**Query params:**
- `from` (optionnel, défaut : -30 jours) : date début `YYYY-MM-DD`
- `to` (optionnel, défaut : aujourd'hui) : date fin `YYYY-MM-DD`
- `account_id` (optionnel) : filtre par compte
- `limit` (optionnel, défaut : 100) : nombre max de résultats
- `offset` (optionnel, défaut : 0) : décalage pour pagination

**Response 200:**
```json
[
  {
    "account_id": "tr_CTO_EUR",
    "date": "2026-03-23",
    "cash": 1200.00,
    "positions_value": 15500.00,
    "total_value": 16700.00,
    "currency": "EUR",
    "positions": [
      {"symbol": "IWDA", "qty": 50, "price": 81.90, "value": 4095.00}
    ]
  },
  {
    "account_id": "tr_CTO_EUR",
    "date": "2026-03-24",
    "cash": 1234.56,
    "positions_value": 15678.90,
    "total_value": 16913.46,
    "currency": "EUR",
    "positions": [
      {"symbol": "IWDA", "qty": 50, "price": 82.30, "value": 4115.00}
    ]
  }
]
```

---

#### `POST /api/snapshots/trigger`

Déclenche un snapshot immédiat pour tous les connecteurs connectés.

**Response 202:**
```json
{
  "triggered": ["tr_charles", "bp_rives"],
  "skipped": ["ibkr_main"],
  "reason_skipped": {"ibkr_main": "disconnected"}
}
```

---

#### `POST /api/snapshots/trigger/{connector_id}`

Snapshot d'un seul connecteur.

**Response 202:**
```json
{"triggered": "tr_charles"}
```

**Response 409:** worker pas connecté.

---

### Transactions

#### `GET /api/transactions`

Liste des mouvements.

**Query params:**
- `from` (optionnel, défaut : -30 jours) : `YYYY-MM-DD`
- `to` (optionnel, défaut : aujourd'hui) : `YYYY-MM-DD`
- `account_id` (optionnel)
- `type` (optionnel) : `buy`, `sell`, `dividend`, `fee`, `transfer`, `interest`
- `limit` (optionnel, défaut : 100)
- `offset` (optionnel, défaut : 0)

**Response 200:**
```json
[
  {
    "id": 1,
    "account_id": "tr_CTO_EUR",
    "date": "2026-03-20",
    "type": "buy",
    "label": "iShares Core MSCI World",
    "amount": -765.00,
    "currency": "EUR",
    "instrument": "IE00B4L5Y983",
    "quantity": 10.0,
    "price": 76.50
  },
  {
    "id": 2,
    "account_id": "bp_00012345",
    "date": "2026-03-22",
    "type": "transfer",
    "label": "Virement reçu SALAIRE",
    "amount": 3200.00,
    "currency": "EUR",
    "instrument": null,
    "quantity": null,
    "price": null
  }
]
```

---

### Performance

#### `GET /api/performance`

P&L par période.

**Query params:**
- `from` (optionnel, défaut : -30 jours) : `YYYY-MM-DD`
- `to` (optionnel, défaut : aujourd'hui) : `YYYY-MM-DD`
- `connector_id` (optionnel)
- `limit` (optionnel, défaut : 100)
- `offset` (optionnel, défaut : 0)

**Response 200:**
```json
[
  {
    "connector_id": "tr_charles",
    "period_start": "2026-03-17",
    "period_end": "2026-03-23",
    "total_value": 16700.00,
    "total_invested": 14200.00,
    "pnl": 2500.00,
    "pnl_pct": 17.60,
    "breakdown": {
      "etf": {"value": 12000, "pnl": 1800},
      "stocks": {"value": 4700, "pnl": 700}
    }
  }
]
```

---

### Scheduler

#### `GET /api/scheduler/status`

État des jobs planifiés.

**Response 200:**
```json
{
  "jobs": [
    {
      "id": "daily_snapshot",
      "schedule": "cron(hour=23, minute=0)",
      "next_run": "2026-03-24T23:00:00Z",
      "last_run": "2026-03-23T23:00:00Z",
      "last_result": "ok"
    },
    {
      "id": "weekly_performance",
      "schedule": "cron(day_of_week=mon, hour=0, minute=5)",
      "next_run": "2026-03-31T00:05:00Z",
      "last_run": "2026-03-24T00:05:00Z",
      "last_result": "ok"
    }
  ]
}
```

---

### Health

#### `GET /api/health`

Healthcheck global.

**Response 200:**
```json
{
  "status": "ok",
  "vault": "unlocked",
  "scheduler": "running",
  "workers": {
    "tr_charles": "connected",
    "bp_rives": "disconnected",
    "ibkr_main": "connected"
  },
  "db": "ok",
  "uptime_seconds": 86400
}
```

**Response 503:** si DB inaccessible ou autre erreur critique.

---

### Server-Sent Events (SSE)

#### `GET /api/events`

Stream SSE pour recevoir les events des workers en temps réel. Évite le polling.

**Headers de la requête :**
```
Accept: text/event-stream
```

**Events envoyés :**

```
event: worker_status
data: {"connector_id": "tr_charles", "state": "connected"}

event: balance_update
data: {"account_id": "tr_CTO_EUR", "total_value": 16913.46, "updated_at": "2026-03-24T14:30:00Z"}

event: position_update
data: {"connector_id": "tr_charles", "account_id": "tr_CTO_EUR", "symbol": "IWDA", "current_price": 82.30}

event: snapshot_complete
data: {"connector_id": "tr_charles", "date": "2026-03-24", "status": "ok"}

event: error
data: {"connector_id": "bp_rives", "message": "Connection timeout"}
```

**Types d'events :**

| Event | Quand |
|---|---|
| `worker_status` | Changement d'état d'un worker (connect, disconnect, 2fa, error) |
| `balance_update` | Nouvelle balance reçue d'un worker streaming (TR, IBKR) |
| `position_update` | Mise à jour de prix/position |
| `snapshot_complete` | Un snapshot (scheduler ou manuel) est terminé |
| `error` | Erreur sur un worker |

Le frontend ouvre une seule connexion SSE au chargement et dispatch les events vers les composants concernés. Fallback : polling `GET /api/connectors` toutes les 10s si SSE non supporté.

---

## Codes d'erreur communs

| Code | Signification |
|---|---|
| 200 | OK |
| 201 | Créé |
| 202 | Accepté (action async en cours) |
| 204 | Supprimé (no content) |
| 400 | Requête invalide (validation Pydantic) |
| 401 | Master password incorrect |
| 404 | Ressource inconnue |
| 409 | Conflit (vault existe déjà, worker pas dans le bon état) |
| 423 | Vault locked — déverrouiller d'abord |
| 429 | Rate limit (2FA) |
| 503 | Service indisponible |

Format d'erreur standard :
```json
{
  "detail": "Vault is locked. POST /api/vault/unlock first."
}
```
