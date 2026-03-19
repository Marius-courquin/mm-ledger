# mm-ledger — Architecture Proposal

## Overview

Self-hosted portfolio aggregator running on a Raspberry Pi at home. Aggregates data from multiple brokers/banks, archives historical snapshots, and serves a PWA dashboard accessible via VPN.

---

## Infrastructure

```
                        ┌─── Internet ──────────────────────────────┐
                        │                                           │
┌─ Mobile (PWA) ──┐     │  WireGuard VPN Tunnel                    │
│  React SPA      │◄────┼──────────────────────►┌─ Raspberry Pi ──────────────────┐
│  (installable)  │     │                       │                                  │
└─────────────────┘     │                       │  ┌─ Bun Server (:3001) ────────┐ │
                        │                       │  │  API routes                  │ │
┌─ Desktop (PWA) ─┐     │                       │  │  Connector manager (RAM)     │ │
│  React SPA      │◄────┼──────────────────────►│  │  Archiver (cron)             │ │
│  (browser)      │     │                       │  └──┬────┬────┬────┬───────────┘ │
└─────────────────┘     │                       │     │    │    │    │              │
                        │                       │     ▼    ▼    ▼    ▼              │
                        │                       │   ┌──┐ ┌──┐ ┌──┐ ┌────────────┐  │
                        │                       │   │TR│ │BP│ │IB│ │ PostgreSQL  │  │
                        │                       │   │WS│ │Py│ │GW│ │ (archive)  │  │
                        │                       │   └──┘ └──┘ └──┘ └────────────┘  │
                        │                       │                                  │
                        │                       │  ┌─ Docker ───────────────────┐  │
                        │                       │  │  ib-gateway (Java)         │  │
                        │                       │  │  chromium + xvfb (WAF)     │  │
                        │                       │  │  postgresql:16             │  │
                        │                       │  └───────────────────────────┘  │
                        │                       └──────────────────────────────────┘
                        └───────────────────────────────────────────┘
```

---

## Security Model

### Principle: credentials never touch disk

| Data | Storage | Lifetime |
|---|---|---|
| Broker passwords (TR PIN, BP password) | **RAM only** | Until server restart |
| Session tokens (TR WebSocket, IBKR TCP) | **RAM only** | Until disconnect |
| TR cookie file (`~/.tr_api_cookies.json`) | Disk (temp) | Deleted after WebSocket established |
| Portfolio snapshots, balances, transactions | **PostgreSQL** | Permanent (archival) |
| VPN keys (WireGuard) | Disk (encrypted) | Permanent |
| User preferences, connector config | **PostgreSQL** | Permanent |

### What a hacker sees if they access the Rasp

- **DB**: historical balances, transaction labels, portfolio snapshots — no passwords, no tokens
- **RAM**: only if they get root access while the server is running — credentials are in process memory
- **Disk**: no credential files (everything ephemeral)

### Network security

- **WireGuard VPN**: only devices with a valid key can reach the Rasp
- **No port forwarding**: the Rasp is not exposed to the internet
- **HTTPS optional**: VPN already encrypts traffic, but can add Caddy for TLS on LAN if needed
- **Each user = a WireGuard peer**: auth is implicit via VPN key

---

## Authentication Flow (per connector)

### Trade Republic

```
User (PWA)                    Backend (Rasp)               TR API
    │                              │                          │
    │  POST /api/settings          │                          │
    │  {phone, pin}                │                          │
    ├─────────────────────────────►│                          │
    │                              │ 1. Try trapi.login()     │
    │                              │────────────────────────►  │
    │                              │    403 (WAF blocked)     │
    │                              │◄──────────────────────── │
    │                              │                          │
    │                              │ 2. Launch Chromium+xvfb  │
    │                              │    Load app.tr.com       │
    │                              │    WAF JS resolves       │
    │                              │    POST login via browser│
    │                              │────────────────────────►  │
    │                              │    200 {processId}       │
    │                              │◄──────────────────────── │
    │                              │                          │
    │  GET /api/settings           │                          │
    │  {waitingForPin: true}       │                          │
    │◄─────────────────────────────┤                          │
    │                              │                          │
    │  [User validates 2FA on      │                          │
    │   TR mobile app]             │                          │
    │                              │                          │
    │  POST /api/auth/pin          │                          │
    │  {pin: "1234"}               │                          │
    ├─────────────────────────────►│                          │
    │                              │ 3. Verify 2FA via browser│
    │                              │────────────────────────►  │
    │                              │    200 + cookies          │
    │                              │◄──────────────────────── │
    │                              │                          │
    │                              │ 4. Save session, close   │
    │                              │    browser, connect WS   │
    │                              │════════════════════════►  │
    │                              │    WebSocket connected   │
    │                              │◄════════════════════════ │
    │  GET /api/settings           │                          │
    │  {connected: true}           │                          │
    │◄─────────────────────────────┤                          │
```

### Interactive Brokers

```
User                         Backend (Rasp)             IB Gateway (Docker)
  │                              │                          │
  │  docker compose up           │                          │
  │  (with IBKR creds as env)    │                          │
  │                              │                     [Gateway starts,
  │                              │                      logs in to IBKR,
  │                              │                      2FA via mobile]
  │                              │                          │
  │  POST /api/ibkr/connect      │                          │
  │  {host, port}                │                          │
  ├─────────────────────────────►│                          │
  │                              │  TCP connect :4001       │
  │                              │─────────────────────────►│
  │                              │  Connected               │
  │                              │◄─────────────────────────│
  │                              │  reqManagedAccts()       │
  │                              │─────────────────────────►│
  │                              │  accounts, positions     │
  │                              │◄─────────────────────────│
  │  {connected: true}           │                          │
  │◄─────────────────────────────┤                          │
```

### Banque Populaire

```
User                         Backend (Rasp)             Woob (Python subprocess)
  │                              │                          │
  │  POST /api/bp/settings       │                          │
  │  {login, password, region}   │                          │
  ├─────────────────────────────►│                          │
  │                              │  spawn bridge.py         │
  │                              │─────────stdin───────────►│
  │                              │  {"action":"connect"}    │
  │                              │                          │  [Woob connects]
  │                              │  stdout: {"type":"2fa"}  │
  │                              │◄─────────stdout──────────│
  │                              │                          │
  │  {waiting2FA: "app"}         │                          │
  │◄─────────────────────────────┤                          │
  │                              │                          │
  │  [User validates Secur'Pass] │                          │
  │                              │                          │
  │  POST /api/bp/auth           │                          │
  │  {method: "app"}             │                          │
  ├─────────────────────────────►│                          │
  │                              │  stdin: validate_2fa     │
  │                              │─────────────────────────►│
  │                              │  stdout: {connected}     │
  │                              │◄─────────────────────────│
  │  {connected: true}           │                          │
  │◄─────────────────────────────┤                          │
```

---

## Data Archival (PostgreSQL)

### Schema

```sql
-- Users (mapped to VPN peers)
CREATE TABLE users (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name        TEXT NOT NULL,
  created_at  TIMESTAMPTZ DEFAULT now()
);

-- Connector configs (no passwords — just type + display name)
CREATE TABLE connectors (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     UUID REFERENCES users(id),
  type        TEXT NOT NULL, -- 'trade-republic', 'interactive-brokers', 'banque-populaire'
  label       TEXT NOT NULL, -- 'CTO (Trade Republic)', 'PEA', etc.
  meta        JSONB,         -- non-sensitive config (account IDs, region, etc.)
  created_at  TIMESTAMPTZ DEFAULT now()
);

-- Daily snapshots of account balances
CREATE TABLE balance_snapshots (
  id            BIGSERIAL PRIMARY KEY,
  connector_id  UUID REFERENCES connectors(id),
  snapshot_date DATE NOT NULL,
  cash          NUMERIC(14,2),
  positions_value NUMERIC(14,2),
  total_value   NUMERIC(14,2),
  currency      TEXT DEFAULT 'EUR',
  positions     JSONB,  -- [{symbol, qty, price, value, pnl}, ...]
  created_at    TIMESTAMPTZ DEFAULT now(),
  UNIQUE(connector_id, snapshot_date)
);

-- Bank transactions (BP, TR compte courant)
CREATE TABLE transactions (
  id            BIGSERIAL PRIMARY KEY,
  connector_id  UUID REFERENCES connectors(id),
  tx_date       DATE NOT NULL,
  label         TEXT,
  amount        NUMERIC(14,2),
  currency      TEXT DEFAULT 'EUR',
  category      TEXT,  -- auto-categorized or manual
  raw           JSONB, -- original data from source
  created_at    TIMESTAMPTZ DEFAULT now()
);

-- Weekly portfolio performance summary
CREATE TABLE performance_weekly (
  id            BIGSERIAL PRIMARY KEY,
  user_id       UUID REFERENCES users(id),
  week_start    DATE NOT NULL,
  total_value   NUMERIC(14,2),
  total_invested NUMERIC(14,2),
  total_pnl     NUMERIC(14,2),
  pnl_pct       NUMERIC(8,4),
  breakdown     JSONB,  -- {cto: {value, pnl}, pea: {...}, ibkr: {...}}
  created_at    TIMESTAMPTZ DEFAULT now(),
  UNIQUE(user_id, week_start)
);
```

### Archiver (cron job)

```
Every day at 23:00:
  1. For each connected user:
     a. Fetch current balances from all connectors (TR, IBKR, BP)
     b. INSERT INTO balance_snapshots
     c. Fetch new bank transactions (BP)
     d. INSERT INTO transactions (upsert by date+label+amount)

Every Monday at 00:00:
  1. For each user:
     a. Compute weekly P&L from balance_snapshots
     b. INSERT INTO performance_weekly
```

### What this enables

- **Cash flow tracking**: "Am I spending more than I earn?" (transactions table)
- **Portfolio growth over time**: real historical data, not projected from current holdings
- **Weekly performance email/notification**: "+2.3% this week across all accounts"
- **Tax reporting**: all transactions with dates and amounts

---

## Multi-user

Each VPN peer = one user. The backend identifies the user by their VPN IP (WireGuard assigns static IPs per peer).

```
WireGuard Config:
  Peer 1 (Marius):  10.0.0.2/32
  Peer 2 (Magni):   10.0.0.3/32
  Server (Rasp):    10.0.0.1/32
```

The backend reads the source IP from the request and maps it to a user:

```typescript
const USER_MAP: Record<string, string> = {
  "10.0.0.2": "marius",
  "10.0.0.3": "magni",
};
```

Each user has their own connector instances in RAM — no cross-contamination.

---

## Docker Compose (production)

```yaml
services:
  app:
    build: .
    ports: ["3001:3001"]
    depends_on: [postgres, ib-gateway]
    environment:
      DATABASE_URL: postgresql://mm:mm@postgres:5432/mmledger

  postgres:
    image: postgres:16-alpine
    volumes: [pgdata:/var/lib/postgresql/data]
    environment:
      POSTGRES_DB: mmledger
      POSTGRES_USER: mm
      POSTGRES_PASSWORD: mm

  ib-gateway:
    image: ghcr.io/gnzsnz/ib-gateway:latest
    network_mode: host
    environment:
      TWS_USERID: ${IBKR_USERNAME}
      TWS_PASSWORD: ${IBKR_PASSWORD}
      TRADING_MODE: live
      READ_ONLY_API: "yes"

  chromium:
    image: browserless/chromium
    ports: ["3002:3000"]
    # Used by backend for TR WAF bypass
    # Alternative: install chromium+xvfb directly in app container

volumes:
  pgdata:
```

---

## Tech Stack Summary

| Component | Tech | Why |
|---|---|---|
| Runtime | Bun | Fast, TS native, small footprint for Rasp |
| Frontend | React + Vite | PWA-ready, offline-capable |
| Backend | Bun.serve() | Simple, no framework needed |
| DB | PostgreSQL | Reliable, good for time series, JSONB for flexible data |
| VPN | WireGuard | Lightweight, fast, built into Linux kernel |
| TR connector | trapi + Playwright/Chromium (WAF bypass) | WebSocket for data, browser for login |
| IBKR connector | @stoqey/ib + IB Gateway Docker | TCP socket, most complete API |
| BP connector | Woob (Python subprocess) | Only option for French banks |
| Deployment | Docker Compose on Raspberry Pi | Simple, reproducible |

---

## Migration Path (POC → Production)

1. **Now (POC)**: Local dev, Brave for WAF, in-memory only
2. **Phase 1**: Add PostgreSQL, daily archiver, basic cash flow tracking
3. **Phase 2**: PWA manifest + service worker, WireGuard setup on Rasp
4. **Phase 3**: Multi-user, deploy on Raspberry Pi with Docker Compose
5. **Phase 4**: Mobile-first UX improvements, notifications, tax reporting
