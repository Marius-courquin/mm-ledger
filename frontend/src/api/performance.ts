import { api } from './client';

export interface PerfPoint {
  date: string;
  value: number;
  cum_pct: number;
}

export interface PerfHistory {
  period: string;
  series: PerfPoint[];
  total_pct: number;
  value_now: number;
  value_start: number;
  currency: string;
}

export function getPerformanceHistory(params: {
  period?: string;
  connector_id?: string;
  account_id?: string;
} = {}): Promise<PerfHistory> {
  const query: Record<string, string> = {};
  if (params.period) query.period = params.period;
  if (params.connector_id) query.connector_id = params.connector_id;
  if (params.account_id) query.account_id = params.account_id;
  return api.get('/performance/history', query) as Promise<PerfHistory>;
}
