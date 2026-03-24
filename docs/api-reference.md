# mm-ledger API Reference

> Backend Python (FastAPI) — Version 1.0
>
> This document is the single source of truth for frontend developers integrating with the mm-ledger backend.

---

## Getting Started

**Base URL:** `http://localhost:8000/api`

All responses are JSON (`Content-Type: application/json`).

### Error format

Every error response follows the same structure:

```json
{"detail": "Human-readable error message"}
```

### Pagination

List endpoints (`/api/transactions`, `/api/snapshots`, `/api/performance`) accept query parameters:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit` | int | 100 | Max items per page |
| `offset` | int | 0 | Number of items to skip |

The response includes an `X-Total-Count` header with the total number of matching records.

### Date filtering

List endpoints that accept date ranges use `from` and `to` query parameters.

| Parameter | Format | Default |
|-----------|--------|---------|
| `from` | `YYYY-MM-DD` | 30 days ago |
| `to` | `YYYY-MM-DD` | today |

Both are optional. Omitting them applies the defaults above.

---

## Authentication Flow

There is no user authentication (single-user app, access controlled via VPN). Instead, the API is gated by a **vault** that encrypts stored credentials at rest. The frontend must unlock the vault before most operations work.

### Flow

```
App loads
  |
  +-- GET /api/vault/status
       +-- "uninitialized"  -->  show setup screen   -->  POST /api/vault/setup
       +-- "locked"         -->  show unlock screen   -->  POST /api/vault/unlock
       +-- "unlocked"       -->  proceed to dashboard
```

On first launch, the vault does not exist. The frontend calls `/setup` to create it with a master password. On subsequent launches, the vault exists but is locked; the frontend calls `/unlock`. Once unlocked, the vault stays open until explicitly locked or the container restarts.

---

### `GET /api/vault/status`

Returns the current vault state. Call this on app load to decide which screen to render.

**Response `200 OK`:**

```json
{
  "state": "locked"
}
```

| `state` value | Meaning | Frontend action |
|---------------|---------|-----------------|
| `uninitialized` | First launch, no vault file exists | Show setup form |
| `locked` | Vault exists but is locked | Show unlock form |
| `unlocked` | Vault is open, app is ready | Proceed to dashboard |

---

### `POST /api/vault/setup`

Creates the encrypted vault. Call only when state is `uninitialized`.

**Request body:**

```json
{
  "password": "my_master_password"
}
```

**Response `201 Created`:**

```json
{
  "status": "created"
}
```

**Errors:**

| Status | Condition |
|--------|-----------|
| `409 Conflict` | Vault already exists |

---

### `POST /api/vault/unlock`

Decrypts the vault for the current session.

**Request body:**

```json
{
  "password": "my_master_password"
}
```

**Response `200 OK`:**

```json
{
  "status": "unlocked"
}
```

**Errors:**

| Status | Condition |
|--------|-----------|
| `401 Unauthorized` | Wrong password |
| `429 Too Many Requests` | Too many failed attempts. Backoff is exponential (1s, 2s, 4s, 8s...) after 3 consecutive failures. Resets on success |

---

### `POST /api/vault/lock`

Locks the vault. Already-connected workers keep running, but no new connections can be established (credentials become inaccessible).

**Request body:** none.

**Response `200 OK`:**

```json
{
  "status": "locked"
}
```

---

### `POST /api/vault/change-password`

Changes the master password. The vault must be unlocked.

**Request body:**

```json
{
  "old_password": "ancien",
  "new_password": "nouveau"
}
```

**Response `200 OK`:**

```json
{
  "status": "changed"
}
```

**Errors:**

| Status | Condition |
|--------|-----------|
| `401 Unauthorized` | `old_password` is incorrect |
| `423 Locked` | Vault is locked (unlock first) |

---

## Connector Types Reference

### `GET /api/connectors/types`

Returns the list of supported connector types with their credential and config field definitions. Use this to dynamically build "add connector" forms.

**Response `200 OK`:**

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

### Types summary

| Type | Label | Credentials | Config | 2FA | Streaming |
|------|-------|-------------|--------|-----|-----------|
| `trade_republic` | Trade Republic | `phone`, `pin` | -- | Yes | Yes |
| `ibkr` | Interactive Brokers | -- | `host`, `port` | No | Yes |
| `woob_bank` | Banque (Woob) | `login`, `password`, `bank_module`, `region` | -- | Yes | No |

**Notes:**
- Fields with `required: true` must be filled before submission.
- Fields with a `default` value should pre-populate the input.
- `credential_fields` are stored encrypted in the vault. `config_fields` are stored in plaintext.
- IBKR has no `credential_fields` because its credentials are env vars on the IB Gateway container.

---

## Connectors

### Worker States

Each connector has an associated worker process. The worker is always in one of these states:

| State | Description |
|---|---|
| `disconnected` | No worker process running. Default state. |
| `connecting` | Worker spawned, authentication in progress. Transient. |
| `connected` | Worker authenticated and ready. |
| `waiting_2fa` | Worker blocked waiting for a 2FA code. `detail` describes what is expected. |
| `error` | Worker crashed or unrecoverable error. No automatic restart. |

State transitions:

```
disconnected --connect--> connecting --> connected
                               |
                               +--> waiting_2fa --submit 2fa--> connecting --> connected
                               |
                               +--> error
connected --disconnect--> disconnected
connected --crash--> error
error --restart--> connecting
```

---

### `GET /api/connectors`

List all configured connectors with their current worker state.

**Response `200 OK`:**

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

### `POST /api/connectors`

Create a new connector. Stores credentials in the vault. Does **not** spawn a worker -- call `POST /api/connectors/{id}/connect` after.

**Request body:**

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

**Response `201 Created`:**

```json
{
  "id": "tr_charles",
  "type": "trade_republic",
  "label": "TR Charles"
}
```

Credentials are **never** returned in any API response.

**Errors:**

| Status | Condition |
|--------|-----------|
| `400` | Invalid request (missing fields, unknown type) |
| `409` | Connector with this ID already exists |
| `423` | Vault locked |

---

### `PUT /api/connectors/{id}`

Update a connector's label, config, or credentials. Running worker is **not** restarted -- disconnect and reconnect manually if credentials changed.

**Request body:** (all fields optional)

```json
{
  "label": "TR Charles CTO+PEA",
  "credentials": {"phone": "+33612345678", "pin": "5678"}
}
```

**Response `200 OK`:**

```json
{"id": "tr_charles", "type": "trade_republic", "label": "TR Charles CTO+PEA"}
```

**Errors:** `400`, `404`, `423`

---

### `DELETE /api/connectors/{id}`

Delete connector, remove credentials from vault, stop worker if active.

**Response `204 No Content`**

**Errors:** `404`

---

### `GET /api/connectors/{id}/status`

Detailed worker state.

**Response `200 OK`:**

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

When waiting for 2FA:

```json
{
  "id": "bp_rives",
  "state": "waiting_2fa",
  "detail": "Saisissez le code recu par SMS",
  "pid": 4312,
  "uptime_seconds": 8
}
```

**Errors:** `404`

---

### `POST /api/connectors/{id}/connect`

Spawn worker and start connection. Credentials read from vault. Returns immediately -- connection is async.

**Response `202 Accepted`:**

```json
{"status": "connecting"}
```

**Errors:** `404`, `409` (worker already running), `423` (vault locked)

---

### `POST /api/connectors/{id}/disconnect`

Stop worker gracefully.

**Response `200 OK`:**

```json
{"status": "disconnected"}
```

**Errors:** `404`, `409` (already disconnected)

---

### `POST /api/connectors/{id}/restart`

Stop + spawn. Use to recover from `error` state.

**Response `202 Accepted`:**

```json
{"status": "connecting"}
```

**Errors:** `404`, `423`

---

### `POST /api/connectors/{id}/2fa`

Submit a 2FA code. Only valid when worker is in `waiting_2fa` state.

**Request body:**

```json
{"code": "123456"}
```

**Response `200 OK`:**

```json
{"status": "submitted"}
```

**Errors:**

| Status | Condition |
|--------|-----------|
| `400` | Missing or empty code |
| `409` | Worker not in `waiting_2fa` state |
| `429` | Rate limited (max 5 attempts / 5 min per connector) |

---

### 2FA Flow (Frontend Perspective)

```
1. User clicks "Connect"
       |
       v
2. POST /api/connectors/{id}/connect  -->  202
       |
       v
3. Poll GET /api/connectors/{id}/status every 1-2s
   (or listen to SSE worker_status event)
       |
       +-- state = "connected"      -->  done
       +-- state = "error"          -->  show error
       +-- state = "waiting_2fa"    -->  continue
               |
               v
4. Show 2FA prompt (display worker.detail as instructions)
       |
       v
5. POST /api/connectors/{id}/2fa  {"code": "847291"}
       |
       v
6. Resume polling / listening
       +-- state = "connected"      -->  done
       +-- state = "error"          -->  wrong code or timeout
       +-- state = "waiting_2fa"    -->  another round (rare)
```

---

## Accounts & Balances

### `GET /api/accounts`

All accounts across all connectors.

**Query params:** `?connector_id=tr_charles` (optional filter)

**Response `200 OK`:**

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

### `GET /api/accounts/{id}/balance`

Current balance. Returns the latest cached value from memory. For streaming connectors (TR, IBKR) this is updated continuously. For Woob, it reflects the last fetch. Use `updated_at` to display freshness ("2 min ago").

**Response `200 OK`:**

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

| Field | Description |
|---|---|
| `cash` | Uninvested cash |
| `positions_value` | Sum of open position market values |
| `total_value` | `cash + positions_value` |
| `updated_at` | Last data refresh timestamp. Show relative freshness in UI. |

**Errors:** `404`

---

## Portfolio

### `GET /api/portfolio`

All positions aggregated across every connector.

**Query params:** `?connector_id=tr_charles` (optional filter)

The fields `total_invested`, `total_pnl`, `total_pnl_pct` are **computed on the fly**, not stored:
- `total_invested = SUM(quantity * avg_price)`
- `total_pnl = total_value - total_invested`
- `total_pnl_pct = (total_pnl / total_invested) * 100`

**Response `200 OK`:**

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

### `GET /api/portfolio/{connector_id}`

Positions for a single connector. Same format.

**Errors:** `404`

---

## Snapshots (Historical)

### `GET /api/snapshots`

Daily balance snapshots captured by the scheduler (23:00 daily) or triggered manually.

**Query params:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `from` | string | -30 days | Start date `YYYY-MM-DD` |
| `to` | string | today | End date `YYYY-MM-DD` |
| `account_id` | string | -- | Filter by account |
| `limit` | int | 100 | Max results |
| `offset` | int | 0 | Pagination offset |

**Response header:** `X-Total-Count: 58`

**Response `200 OK`:**

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

### `POST /api/snapshots/trigger`

Trigger immediate snapshot for all connected connectors. Uses `INSERT ... ON CONFLICT DO UPDATE` -- calling multiple times on the same day overwrites.

**Response `202 Accepted`:**

```json
{
  "triggered": ["tr_charles", "bp_rives"],
  "skipped": ["ibkr_main"],
  "reason_skipped": {"ibkr_main": "disconnected"}
}
```

---

### `POST /api/snapshots/trigger/{connector_id}`

Snapshot for one connector.

**Response `202 Accepted`:**

```json
{"triggered": "tr_charles"}
```

**Errors:** `404`, `409` (worker not connected)

---

## Transactions

### `GET /api/transactions`

Account movements with pagination and filters.

**Query params:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `from` | string | -30 days | Start date |
| `to` | string | today | End date |
| `account_id` | string | -- | Filter by account |
| `type` | string | -- | `buy`, `sell`, `dividend`, `fee`, `transfer`, `interest` |
| `limit` | int | 100 | Max results |
| `offset` | int | 0 | Pagination offset |

**Response header:** `X-Total-Count: 234`

**Response `200 OK`:**

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
    "label": "Virement recu SALAIRE",
    "amount": 3200.00,
    "currency": "EUR",
    "instrument": null,
    "quantity": null,
    "price": null
  }
]
```

| Field | Description |
|---|---|
| `amount` | Negative for outflows (buys, fees), positive for inflows |
| `instrument` | ISIN or symbol. `null` for non-instrument transactions |
| `quantity` / `price` | `null` for transfers, interest, etc. |

---

## Performance

### `GET /api/performance`

Weekly P&L records computed by the scheduler (Monday 00:05).

**Query params:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `from` | string | -30 days | Start date |
| `to` | string | today | End date |
| `connector_id` | string | -- | Filter by connector |
| `limit` | int | 100 | Max results |
| `offset` | int | 0 | Pagination offset |

**Response header:** `X-Total-Count: 12`

**Response `200 OK`:**

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

## Server-Sent Events (SSE)

### `GET /api/events`

Real-time event stream from all workers. Open one SSE connection at app startup.

**Request header:** `Accept: text/event-stream`

### Event Types

#### `worker_status`

Worker state change.

```
event: worker_status
data: {"connector_id": "tr_charles", "state": "connected"}
```

```
event: worker_status
data: {"connector_id": "bp_rives", "state": "waiting_2fa", "detail": "Confirmez sur Secur'Pass"}
```

#### `balance_update`

New balance from a streaming worker (TR, IBKR). Woob does not emit this.

```
event: balance_update
data: {"account_id": "tr_CTO_EUR", "total_value": 16913.46, "updated_at": "2026-03-24T14:30:00Z"}
```

#### `position_update`

Price or quantity change.

```
event: position_update
data: {"connector_id": "tr_charles", "account_id": "tr_CTO_EUR", "symbol": "IWDA", "current_price": 82.30}
```

#### `snapshot_complete`

Snapshot finished (scheduler or manual trigger).

```
event: snapshot_complete
data: {"connector_id": "tr_charles", "date": "2026-03-24", "status": "ok"}
```

#### `error`

Worker error.

```
event: error
data: {"connector_id": "bp_rives", "message": "Connection timeout"}
```

### Reconnection

`EventSource` auto-reconnects on drops. No `Last-Event-ID` replay -- reconnected clients receive only new events.

**Fallback:** If SSE unavailable, poll `GET /api/connectors` every 10s.

### JavaScript Example

```javascript
const events = new EventSource('/api/events');

events.addEventListener('worker_status', (e) => {
  const data = JSON.parse(e.data);
  updateConnectorStatus(data.connector_id, data.state, data.detail);
  if (data.state === 'waiting_2fa') show2FADialog(data.connector_id, data.detail);
});

events.addEventListener('balance_update', (e) => {
  const data = JSON.parse(e.data);
  updateAccountBalance(data.account_id, data.total_value, data.updated_at);
});

events.addEventListener('position_update', (e) => {
  const data = JSON.parse(e.data);
  updatePositionPrice(data.account_id, data.symbol, data.current_price);
});

events.addEventListener('snapshot_complete', (e) => {
  const data = JSON.parse(e.data);
  showToast(`Snapshot ${data.status} for ${data.connector_id}`);
});

events.addEventListener('error', (e) => {
  if (e.data) {
    const data = JSON.parse(e.data);
    showErrorNotification(`${data.connector_id}: ${data.message}`);
  }
});
```

---

## System

### `GET /api/health`

Global healthcheck.

**Response `200 OK`:**

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

**Response `503`:** critical subsystem down.

---

### `GET /api/scheduler/status`

Scheduler jobs state.

**Response `200 OK`:**

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

## Error Reference

### HTTP Status Codes

| Code | Meaning | Frontend handling |
|---|---|---|
| `200` | OK | Use response normally |
| `201` | Created | Resource created, proceed |
| `202` | Accepted | Async action started. Listen SSE or poll for completion |
| `204` | No Content | Resource deleted. Remove from local state |
| `400` | Bad Request | Parse `detail`, highlight invalid form fields |
| `401` | Unauthorized | Wrong password. Do not auto-retry |
| `404` | Not Found | Stale local state -- refetch resource list |
| `409` | Conflict | Show `detail` message. Refresh state before retrying |
| `423` | Locked | Redirect to vault unlock screen. After unlock, retry |
| `429` | Too Many Requests | Show "too many attempts". Disable submit temporarily |
| `503` | Unavailable | "Backend unavailable" banner. Retry with backoff |

### Validation Error Format (400)

```json
{
  "detail": [
    {"loc": ["body", "phone"], "msg": "Field required", "type": "missing"},
    {"loc": ["body", "pin"], "msg": "String should have at least 4 characters", "type": "string_too_short"}
  ]
}
```

---

## TypeScript Types

```typescript
// -- Vault --

interface VaultStatus {
  state: 'uninitialized' | 'locked' | 'unlocked';
}

// -- Connectors --

type ConnectorType = 'trade_republic' | 'ibkr' | 'woob_bank';
type WorkerState = 'disconnected' | 'connecting' | 'connected' | 'waiting_2fa' | 'error';

interface WorkerInfo {
  state: WorkerState;
  pid?: number;
  uptime_seconds?: number;
  last_error?: string | null;
  last_fetch?: string | null;
  accounts_count?: number;
  accounts?: string[];
  detail?: string;
}

interface Connector {
  id: string;
  type: ConnectorType;
  label: string;
  config: Record<string, unknown>;
  worker?: WorkerInfo;
}

interface CredentialField {
  name: string;
  type: 'text' | 'password' | 'number';
  required: boolean;
  placeholder?: string;
  default?: string | number;
}

interface ConnectorTypeInfo {
  type: ConnectorType;
  label: string;
  credential_fields: CredentialField[];
  config_fields: CredentialField[];
  supports_2fa: boolean;
  supports_streaming: boolean;
}

// -- Accounts & Balances --

type AccountType = 'cto' | 'pea' | 'checking' | 'savings' | 'margin';

interface Account {
  id: string;
  connector_id: string;
  name: string;
  type: AccountType;
  currency: string;
}

interface Balance {
  account_id: string;
  cash: number;
  positions_value: number;
  total_value: number;
  currency: string;
  updated_at: string; // ISO 8601
}

// -- Portfolio --

interface Position {
  connector_id: string;
  account_id: string;
  instrument: string; // ISIN
  name: string;
  symbol: string;
  category: string;
  quantity: number;
  avg_price: number;
  current_price: number;
  value: number;
  pnl: number;
  pnl_pct: number;
  currency: string;
}

interface Portfolio {
  total_value: number;
  total_invested: number;
  total_pnl: number;
  total_pnl_pct: number;
  currency: string;
  positions: Position[];
}

// -- Snapshots --

interface SnapshotPosition {
  symbol: string;
  qty: number;
  price: number;
  value: number;
}

interface Snapshot {
  account_id: string;
  date: string; // YYYY-MM-DD
  cash: number;
  positions_value: number;
  total_value: number;
  currency: string;
  positions: SnapshotPosition[];
}

// -- Transactions --

type TransactionType = 'buy' | 'sell' | 'dividend' | 'fee' | 'transfer' | 'interest';

interface Transaction {
  id: number;
  account_id: string;
  date: string; // YYYY-MM-DD
  type: TransactionType;
  label: string;
  amount: number;
  currency: string;
  instrument: string | null;
  quantity: number | null;
  price: number | null;
}

// -- Performance --

interface PerformanceBreakdown {
  [category: string]: { value: number; pnl: number };
}

interface Performance {
  connector_id: string;
  period_start: string;
  period_end: string;
  total_value: number;
  total_invested: number;
  pnl: number;
  pnl_pct: number;
  breakdown: PerformanceBreakdown;
}

// -- System --

interface HealthCheck {
  status: 'ok' | 'degraded';
  vault: 'uninitialized' | 'locked' | 'unlocked';
  scheduler: 'running' | 'stopped';
  workers: Record<string, WorkerState>;
  db: 'ok' | 'error';
  uptime_seconds: number;
}

interface SchedulerJob {
  id: string;
  schedule: string;
  next_run: string;
  last_run: string | null;
  last_result: 'ok' | 'error' | null;
}

interface SchedulerStatus {
  jobs: SchedulerJob[];
}

// -- SSE Events --

interface SSEWorkerStatus {
  connector_id: string;
  state: WorkerState;
  detail?: string;
}

interface SSEBalanceUpdate {
  account_id: string;
  total_value: number;
  updated_at: string;
}

interface SSEPositionUpdate {
  connector_id: string;
  account_id: string;
  symbol: string;
  current_price: number;
}

interface SSESnapshotComplete {
  connector_id: string;
  date: string;
  status: 'ok' | 'error';
  message?: string;
}

interface SSEError {
  connector_id: string;
  message: string;
}

type SSEEvent =
  | { type: 'worker_status'; data: SSEWorkerStatus }
  | { type: 'balance_update'; data: SSEBalanceUpdate }
  | { type: 'position_update'; data: SSEPositionUpdate }
  | { type: 'snapshot_complete'; data: SSESnapshotComplete }
  | { type: 'error'; data: SSEError };

// -- API Errors --

interface APIError {
  detail: string;
}

interface ValidationErrorItem {
  loc: (string | number)[];
  msg: string;
  type: string;
}

interface APIValidationError {
  detail: ValidationErrorItem[];
}
```
