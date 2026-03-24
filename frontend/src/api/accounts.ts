import { api } from './client';
import type { Account, Balance } from '../lib/types';

export function getAccounts(connectorId?: string): Promise<Account[]> {
  return api.get<Account[]>('/accounts', connectorId ? { connector_id: connectorId } : undefined);
}

export function getAccountBalance(id: string): Promise<Balance> {
  return api.get<Balance>(`/accounts/${id}/balance`);
}
