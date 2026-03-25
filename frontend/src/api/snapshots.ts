import { api } from './client';
import type { Snapshot } from '../lib/types';

export function getSnapshots(params?: {
  from?: string;
  to?: string;
  account_id?: string;
  limit?: number;
  offset?: number;
}): Promise<Snapshot[]> {
  return api.get<Snapshot[]>('/snapshots', params);
}

export function triggerSnapshot(): Promise<{ triggered: string[]; skipped: string[] }> {
  return api.post<{ triggered: string[]; skipped: string[] }>('/snapshots/trigger');
}
