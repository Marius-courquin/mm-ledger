// frontend/src/api/projection.ts
import { api } from './client';
import type {
  ProjectionResult, ProjectionSettings, ProjectionSettingsView, ProjectionCategory,
} from '../lib/projection';

export function getProjectionSettings(): Promise<ProjectionSettingsView> {
  return api.get<ProjectionSettingsView>('/projection/settings');
}

export function updateProjectionSettings(patch: Partial<ProjectionSettings>): Promise<{ settings: ProjectionSettings }> {
  return api.put<{ settings: ProjectionSettings }>('/projection/settings', patch);
}

export function computeProjection(): Promise<ProjectionResult> {
  return api.get<ProjectionResult>('/projection/compute');
}

export function setAccountOverride(account_id: string, category: ProjectionCategory): Promise<void> {
  return api.post('/projection/account-override', { account_id, category });
}

export function clearAccountOverride(account_id: string): Promise<void> {
  return api.del(`/projection/account-override/${account_id}`);
}
