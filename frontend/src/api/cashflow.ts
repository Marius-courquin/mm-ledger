import { api } from './client';

export function getCashflow(period: string = '1M', includeInvestments: boolean = true) {
  return api.get('/cashflow', { period, include_investments: String(includeInvestments) });
}
