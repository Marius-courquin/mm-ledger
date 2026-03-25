import { api } from './client';
import type { Transaction, TransactionType } from '../lib/types';

export function getTransactions(params?: {
  from?: string;
  to?: string;
  account_id?: string;
  type?: TransactionType;
  limit?: number;
  offset?: number;
}): Promise<Transaction[]> {
  return api.get<Transaction[]>('/transactions', params);
}
