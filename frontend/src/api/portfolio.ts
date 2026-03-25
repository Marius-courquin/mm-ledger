import { api } from './client';
import type { Portfolio } from '../lib/types';

export function getPortfolio(connectorId?: string): Promise<Portfolio> {
  return api.get<Portfolio>('/portfolio', connectorId ? { connector_id: connectorId } : undefined);
}
