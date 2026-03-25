import { api } from './client';

export function getCashflow(period: string = '1M') {
  return api.get('/cashflow', { period });
}
