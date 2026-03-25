import { api } from './client';

export function getCashflow(month?: string) {
  const params: Record<string, string> = {};
  if (month) params.month = month;
  return api.get('/cashflow', params);
}
