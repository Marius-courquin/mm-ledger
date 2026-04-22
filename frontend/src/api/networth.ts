import { api } from './client';

export function getNetWorth() {
  return api.get('/net-worth');
}

export function getNetWorthHistory(from?: string) {
  const params: Record<string, string> = {};
  if (from) params.from = from;
  return api.get('/net-worth/history', params);
}

export function getInvestmentsHistory() {
  return api.get('/net-worth/investments/history');
}
