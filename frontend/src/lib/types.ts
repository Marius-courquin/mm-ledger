// ── Vault ────────────────────────────────────────────────────────────────────

export interface VaultStatus {
  state: 'uninitialized' | 'locked' | 'unlocked';
}

// ── Connectors ───────────────────────────────────────────────────────────────

export type ConnectorType = 'trade_republic' | 'ibkr' | 'woob_bank';
export type WorkerState = 'disconnected' | 'connecting' | 'starting_gateway' | 'connected' | 'waiting_2fa' | 'error';

export interface WorkerInfo {
  state: WorkerState;
  pid?: number;
  uptime_seconds?: number;
  last_error?: string | null;
  last_fetch?: string | null;
  accounts_count?: number;
  accounts?: string[];
  detail?: string;
}

export interface Connector {
  id: string;
  type: ConnectorType;
  label: string;
  config: Record<string, unknown>;
  worker?: WorkerInfo;
}

export interface CredentialField {
  name: string;
  type: 'text' | 'password' | 'number' | 'select';
  required: boolean;
  placeholder?: string;
  default?: string | number;
  options?: Array<{ value: string; label: string }>;
}

export interface ConnectorTypeInfo {
  type: ConnectorType;
  label: string;
  credential_fields: CredentialField[];
  config_fields: CredentialField[];
  supports_2fa: boolean;
  supports_streaming: boolean;
}

// ── Accounts & Balances ──────────────────────────────────────────────────────

export type AccountType = 'cto' | 'pea' | 'checking' | 'savings' | 'margin';

export interface Account {
  id: string;
  connector_id: string;
  name: string;
  type: AccountType;
  currency: string;
}

export interface Balance {
  account_id: string;
  cash: number;
  positions_value: number;
  total_value: number;
  currency: string;
  updated_at: string;
}

// ── Portfolio ────────────────────────────────────────────────────────────────

export interface Position {
  connector_id: string;
  account_id: string;
  instrument: string;
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

export interface PortfolioCategory {
  categoryType: string;
  total_value: number;
  total_invested: number;
  pnl: number;
  pnl_pct: number;
  positions: Position[];
}

export interface PortfolioAccount {
  secAccNo: string;
  label: string;
  productType: string;
  cash: number;
  positions_value: number;
  total_value: number;
  total_invested: number;
  pnl: number;
  pnl_pct: number;
  categories: PortfolioCategory[];
}

export interface Portfolio {
  total_value: number;
  total_cash: number;
  total_invested: number;
  total_pnl: number;
  total_pnl_pct: number;
  currency: string;
  accounts: PortfolioAccount[];
}

// ── Snapshots ────────────────────────────────────────────────────────────────

export interface SnapshotPosition {
  symbol: string;
  qty: number;
  price: number;
  value: number;
}

export interface Snapshot {
  account_id: string;
  date: string;
  cash: number;
  positions_value: number;
  total_value: number;
  currency: string;
  positions: SnapshotPosition[];
}

// ── Transactions ─────────────────────────────────────────────────────────────

export type TransactionType = 'buy' | 'sell' | 'dividend' | 'fee' | 'transfer' | 'interest';

export interface Transaction {
  id: number;
  account_id: string;
  date: string;
  type: TransactionType;
  label: string;
  amount: number;
  currency: string;
  instrument: string | null;
  quantity: number | null;
  price: number | null;
}

// ── Performance ──────────────────────────────────────────────────────────────

export interface PerformanceBreakdown {
  [category: string]: { value: number; pnl: number };
}

export interface Performance {
  connector_id: string;
  period_start: string;
  period_end: string;
  total_value: number;
  total_invested: number;
  pnl: number;
  pnl_pct: number;
  breakdown: PerformanceBreakdown;
}

// ── System ───────────────────────────────────────────────────────────────────

export interface HealthCheck {
  status: 'ok' | 'degraded';
  vault: 'uninitialized' | 'locked' | 'unlocked';
  scheduler: 'running' | 'stopped';
  workers: Record<string, WorkerState>;
  db: 'ok' | 'error';
  uptime_seconds: number;
}

export interface SchedulerJob {
  id: string;
  schedule: string;
  next_run: string;
  last_run: string | null;
  last_result: 'ok' | 'error' | null;
}

export interface SchedulerStatus {
  jobs: SchedulerJob[];
}

// ── SSE Events ───────────────────────────────────────────────────────────────

export interface SSEWorkerStatus {
  connector_id: string;
  state: WorkerState;
  detail?: string;
}

export interface SSEBalanceUpdate {
  account_id: string;
  total_value: number;
  updated_at: string;
}

export interface SSEPositionUpdate {
  connector_id: string;
  account_id: string;
  symbol: string;
  current_price: number;
}

export interface SSESnapshotComplete {
  connector_id: string;
  date: string;
  status: 'ok' | 'error';
  message?: string;
}

export interface SSEError {
  connector_id: string;
  message: string;
}

// ── API Errors ───────────────────────────────────────────────────────────────

export interface APIError {
  detail: string;
}

export interface ValidationErrorItem {
  loc: (string | number)[];
  msg: string;
  type: string;
}

export interface APIValidationError {
  detail: ValidationErrorItem[];
}
