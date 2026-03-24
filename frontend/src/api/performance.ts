import { api } from './client';
import type { Performance } from '../lib/types';

export function getPerformance(params?: {
  from?: string;
  to?: string;
  connector_id?: string;
  limit?: number;
  offset?: number;
}): Promise<Performance[]> {
  return api.get<Performance[]>('/performance', params);
}
