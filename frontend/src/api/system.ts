import { api } from './client';
import type { HealthCheck, SchedulerStatus } from '../lib/types';

export function getHealth(): Promise<HealthCheck> {
  return api.get<HealthCheck>('/health');
}

export function getSchedulerStatus(): Promise<SchedulerStatus> {
  return api.get<SchedulerStatus>('/scheduler/status');
}
