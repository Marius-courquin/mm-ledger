export type TargetType = 'asset' | 'bucket';
export type AllocationKind = 'amount' | 'percent';
export type RateSource = 'auto' | 'override';
export type EtaStatus = 'reached' | 'ok' | 'insufficient';

export interface Slice {
  id: number;
  account_id: string;
  allocation_kind: AllocationKind;
  allocation_value: number;
}

export interface Target {
  id: number;
  name: string;
  type: TargetType;
  target_amount: number;
  asset_account_id: string | null;
  asset_symbol: string | null;
  rate_override: number | null;
  archived: boolean;
  created_at: string;
  slices: Slice[];
}

export interface HistoryPoint {
  date: string;
  value: number;
}

export interface Progression {
  target_id: number;
  target_amount: number;
  current_value: number;
  progress_pct: number;
  rate: number;
  rate_source: RateSource;
  eta_months: number | null;
  eta_status: EtaStatus;
  history: HistoryPoint[];
}

export interface TargetCreatePayload {
  name: string;
  type: TargetType;
  target_amount: number;
  asset_account_id?: string;
  asset_symbol?: string;
  rate_override?: number | null;
  slices: { account_id: string; allocation_kind: AllocationKind; allocation_value: number }[];
}
