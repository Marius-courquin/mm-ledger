import { api } from './client';
import type { Connector, ConnectorTypeInfo, WorkerInfo } from '../lib/types';

export function getConnectorTypes(): Promise<ConnectorTypeInfo[]> {
  return api.get<ConnectorTypeInfo[]>('/connectors/types');
}

export function getConnectors(): Promise<Connector[]> {
  return api.get<Connector[]>('/connectors');
}

export function createConnector(data: {
  type: string;
  label: string;
  credentials: Record<string, unknown>;
  config?: Record<string, unknown>;
}): Promise<Connector> {
  return api.post<Connector>('/connectors', data);
}

export function updateConnector(
  id: string,
  data: { label?: string; credentials?: Record<string, unknown>; config?: Record<string, unknown> },
): Promise<Connector> {
  return api.put<Connector>(`/connectors/${id}`, data);
}

export function deleteConnector(id: string): Promise<void> {
  return api.del(`/connectors/${id}`);
}

export function getConnectorStatus(id: string): Promise<WorkerInfo & { id: string }> {
  return api.get<WorkerInfo & { id: string }>(`/connectors/${id}/status`);
}

export function connectConnector(id: string): Promise<void> {
  return api.post<void>(`/connectors/${id}/connect`);
}

export function disconnectConnector(id: string): Promise<void> {
  return api.post<void>(`/connectors/${id}/disconnect`);
}

export function restartConnector(id: string): Promise<void> {
  return api.post<void>(`/connectors/${id}/restart`);
}

export function submit2FA(id: string, code: string): Promise<void> {
  return api.post<void>(`/connectors/${id}/2fa`, { code });
}
