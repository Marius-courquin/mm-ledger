# mm-ledger Frontend Design Spec

> React SPA consuming the FastAPI backend, built with HeroUI + Recharts.

---

## Stack

| Layer | Choice | Why |
|-------|--------|-----|
| Runtime / PM | Bun | Already used in repo |
| Bundler | Vite | Fast, React-native HMR |
| UI framework | React 19 + TypeScript | Design system specifies React |
| Components | HeroUI (`@heroui/react`, `@heroui/styles`) | User choice, Tailwind v4 based |
| CSS | Tailwind CSS v4 (via HeroUI) | Utility-first, design tokens as CSS vars |
| Icons | Lucide React | Matches .pen icon references |
| Charts | Recharts | Design system specifies Recharts |
| Routing | React Router v7 | Standard SPA routing |

---

## Project Structure

```
frontend/
├── index.html
├── package.json
├── tsconfig.json
├── vite.config.ts
├── src/
│   ├── main.tsx                    # Entry: React root
│   ├── App.tsx                     # Router + providers
│   ├── app.css                     # Tailwind imports + custom theme
│   ├── api/
│   │   ├── client.ts              # Fetch wrapper (base URL, error handling)
│   │   ├── vault.ts               # Vault endpoints
│   │   ├── connectors.ts          # Connector CRUD + actions
│   │   ├── accounts.ts            # Accounts & balances
│   │   ├── portfolio.ts           # Portfolio positions
│   │   ├── snapshots.ts           # Historical snapshots
│   │   ├── transactions.ts        # Transaction list
│   │   ├── performance.ts         # Weekly P&L
│   │   └── system.ts              # Health, scheduler
│   ├── hooks/
│   │   ├── useSSE.ts              # Single EventSource connection
│   │   ├── useVault.ts            # Vault state + redirect logic
│   │   └── useConnectors.ts       # Connectors state, SSE-updated
│   ├── context/
│   │   └── AppContext.tsx          # Vault state, connectors, SSE dispatch
│   ├── layouts/
│   │   ├── AppLayout.tsx          # Sidebar + main content area
│   │   └── Sidebar.tsx            # Navigation sidebar (240px)
│   ├── pages/
│   │   ├── VaultSetup.tsx         # First-launch: create master password
│   │   ├── VaultUnlock.tsx        # Unlock screen: enter master password
│   │   ├── Dashboard.tsx          # Main dashboard with metrics + chart
│   │   ├── Portfolio.tsx          # Allocation + donut + holdings table
│   │   ├── Accounts.tsx           # Connector list + account detail
│   │   ├── AccountDetail.tsx      # Single connector detail view
│   │   └── Settings.tsx           # Connector management + vault settings
│   ├── components/
│   │   ├── MetricCard.tsx         # Reusable stat card (label, value, sub)
│   │   ├── PerformanceChart.tsx   # Area chart with period selector
│   │   ├── AllocationDonut.tsx    # Donut chart with center label
│   │   ├── HoldingsTable.tsx      # Portfolio positions table
│   │   ├── ConnectorRow.tsx       # Single connector in list
│   │   ├── ConnectorForm.tsx      # Add/edit connector modal form
│   │   ├── TwoFADialog.tsx        # 2FA code input modal
│   │   └── AccountRow.tsx         # Account row in connected accounts
│   └── lib/
│       ├── types.ts               # TypeScript types from API reference
│       └── format.ts              # Currency/date/percent formatters
```

---

## Theme

Dark-only. Custom CSS variables mapped to HeroUI's theming system via `@theme inline` and `:root`.

### CSS Variables (from design-system.md)

```css
:root {
  color-scheme: dark;

  /* Core */
  --background: #102b3f;
  --foreground: #f0ece4;
  --surface: #062726;
  --surface-elevated: #143a42;
  --accent: #C9A84C;
  --accent-lavender: #a06cd5;
  --accent-lilac: #6247aa;
  --border: #1a3d4d;

  /* Text */
  --text-primary: #f0ece4;
  --text-secondary: #e2cfea;
  --text-muted: #e2cfea80;

  /* Semantic */
  --gain: #C9A84C;
  --loss: #e2cfea70;

  /* Chart palette */
  --chart-1: #2c7ce5;
  --chart-2: #f8c421;
  --chart-3: #49cc5c;
  --chart-4: #6434e9;
  --chart-5: #fb6640;
  --chart-6: #f82553;

  /* Spacing */
  --radius-sm: 4px;
  --radius-md: 8px;
  --radius-lg: 12px;
  --radius-xl: 16px;
}
```

HeroUI components will be styled via className overrides using these Tailwind-mapped tokens. No light mode needed.

### Typography

- Font: Inter (Google Fonts, loaded via `<link>` in `index.html`)
- All amounts/percentages: `font-variant-numeric: tabular-nums`
- Sizes follow design system (11px captions through 40px hero amounts)

---

## Routing

```
/setup          → VaultSetup       (no sidebar, full-screen)
/unlock         → VaultUnlock      (no sidebar, full-screen)
/               → Dashboard        (sidebar layout)
/portfolio      → Portfolio        (sidebar layout)
/accounts       → Accounts         (sidebar layout)
/accounts/:id   → AccountDetail    (sidebar layout)
/settings       → Settings         (sidebar layout)
```

### Route Guard

`App.tsx` fetches `GET /api/vault/status` on mount:
- `uninitialized` → redirect to `/setup`
- `locked` → redirect to `/unlock`
- `unlocked` → render sidebar layout with child routes

Any 423 response from the API client → redirect to `/unlock`.

---

## Pages Detail

### 1. VaultSetup (`/setup`)

Centered card on dark background. HeroUI `Card` + `Input` + `Button`.
- Password input (type="password") + confirm password
- "Create Vault" button → `POST /api/vault/setup`
- On success → redirect to `/`
- On error → inline error message

### 2. VaultUnlock (`/unlock`)

Same centered layout.
- Password input
- "Unlock" button → `POST /api/vault/unlock`
- Handle 401 (wrong password), 429 (rate limited) with inline messages

### 3. Dashboard (`/`)

From .pen "Dashboard Overview" frame:

**Welcome Header:**
- Greeting with time-of-day ("Good morning, Marius")
- Current date formatted

**4 Metric Cards** (horizontal row, `fill_container`):
1. **Total Balance** — gold large value (32px/700), fetched from sum of account balances
2. **Monthly P&L** — gain-colored value + "% this month" sub
3. **Total Accounts** — count + "X connected" sub
4. **Best Performer** — symbol name + gain % sub

**Performance Chart:**
- Header: "Portfolio Performance" + period chips (1W, 1M, 3M, 1Y, All)
- Active chip: surface-elevated bg + gold border + gold text
- Recharts `AreaChart` with gold line, gold gradient fill, muted grid lines
- Y-axis labels (left), X-axis date labels (bottom)
- Data from `GET /api/snapshots` with date range matching selected period

**Connected Accounts:**
- Header: "Connected Accounts"
- List in a card: each row = icon (colored bg) + name/type + balance/perf (right-aligned)
- Data from `GET /api/connectors` + `GET /api/accounts/{id}/balance`

### 4. Portfolio (`/portfolio`)

From .pen "Portfolio Composition" frame:

**Header:**
- Left: "Portfolio Composition" title + subtitle
- Right: total value in gold (28px/700) + "Total Portfolio Value" label

**5 Allocation Cards** (horizontal row):
- Each: colored dot (chart-N) + category label + percentage (22px/700)
- Categories computed from position data grouped by `category`

**Chart Section** (side by side):
- Left: Recharts `PieChart` (donut) with chart colors, center label showing total
- Right: Legend rows (dot + label + value) vertically stacked

**Holdings Table:**
- Header: "Holdings Breakdown" + "N assets" count
- HeroUI `Table` with columns: Asset Name, Type, Quantity, Current Value, Weight %, Performance
- Type column in lavender, Performance column in gold (gain) or muted (loss)
- Data from `GET /api/portfolio`

### 5. Accounts (`/accounts`)

List view of all connectors with their accounts:
- Each connector as a card showing: label, type badge, worker state indicator, account count
- Click → navigate to `/accounts/:id`
- "Add Connector" button → opens ConnectorForm modal

### 6. AccountDetail (`/accounts/:id`)

From .pen "Account Detail" frame:

**Back link:** arrow-left icon + "Back to Accounts" in lavender

**Header:**
- Left: icon in bordered card (52px) + connector name (24px/600) + type badge + status text
- Right: "Export" button + "Disconnect" button (bordered, icon + text)

**3 Metric Cards:**
- Account Balance (gold, 32px) with trending-up icon + "% all time"
- Cash Available
- Positions Value

**Balance History Chart** (same style as dashboard performance chart)

**Transactions Table:**
- Data from `GET /api/transactions?account_id=X`
- Columns: Date, Type, Label, Amount, Instrument

### 7. Settings (`/settings`)

**Connectors Section:**
- List of all connectors with edit/delete actions
- "Add Connector" button → ConnectorForm modal
- ConnectorForm: dynamically built from `GET /api/connectors/types` (credential_fields + config_fields)

**Vault Section:**
- "Lock Vault" button → `POST /api/vault/lock`
- "Change Password" form → `POST /api/vault/change-password`

**System Info:**
- Health status from `GET /api/health`
- Scheduler jobs from `GET /api/scheduler/status`

---

## Data Layer

### API Client (`api/client.ts`)

Thin fetch wrapper:
- Base URL: `http://localhost:8000/api` (configurable via env var `VITE_API_URL`)
- JSON serialization/deserialization
- 423 responses → dispatch vault-locked event → redirect to `/unlock`
- Error responses → throw typed errors with `detail` message

### SSE (`hooks/useSSE.ts`)

Single `EventSource` connection to `GET /api/events`:
- Opened after vault unlock
- Listeners for: `worker_status`, `balance_update`, `position_update`, `snapshot_complete`, `error`
- `worker_status` with `waiting_2fa` → opens TwoFADialog
- `balance_update` / `position_update` → update local state
- Auto-reconnects (native EventSource behavior)

### App Context (`context/AppContext.tsx`)

Holds:
- `vaultState`: current vault status
- `connectors`: list of connectors with worker state (updated by SSE)
- `setVaultState` / `updateConnector`: dispatchers

No Redux/Zustand — scope is small enough for Context + local state.

---

## Components

### MetricCard
Props: `label`, `value`, `sub?`, `valueColor?` (defaults to text-primary), `icon?`
Uses HeroUI `Card` with surface bg, border, radius-lg.

### PerformanceChart
Props: `data` (date/value pairs), `periods` (chip options), `activePeriod`, `onPeriodChange`
Recharts `AreaChart` with gold stroke, gradient fill, muted grid.

### AllocationDonut
Props: `segments` ({label, value, color}[]), `centerLabel`, `centerSub`
Recharts `PieChart` with `innerRadius`/`outerRadius` for donut effect.

### HoldingsTable
Props: `positions` (Position[])
HeroUI `Table` with header styling matching .pen.

### ConnectorForm
Props: `connectorTypes`, `onSubmit`, `initial?` (for edit)
Dynamically renders fields from `credential_fields` and `config_fields`.

### TwoFADialog
Props: `connectorId`, `detail` (instruction text), `onSubmit`, `onClose`
HeroUI `Modal` with code input.

---

## Error Handling

| HTTP Status | Frontend Behavior |
|-------------|-------------------|
| 200-204 | Normal processing |
| 400 | Parse `detail` array, highlight fields |
| 401 | "Wrong password" inline message |
| 404 | Stale state — refetch list |
| 409 | Show `detail` message, refresh |
| 423 | Redirect to `/unlock` |
| 429 | Disable submit, show "too many attempts" |
| 503 | Banner: "Backend unavailable", retry with backoff |

---

## Types

All TypeScript types are defined in `lib/types.ts`, directly from the API reference's TypeScript Types section. This is the single source of truth for frontend types.
