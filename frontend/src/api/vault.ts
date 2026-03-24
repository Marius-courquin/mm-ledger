import { api } from './client';
import type { VaultStatus } from '../lib/types';

export function getVaultStatus(): Promise<VaultStatus> {
  return api.get<VaultStatus>('/vault/status');
}

export function setupVault(password: string): Promise<void> {
  return api.post<void>('/vault/setup', { password });
}

export function unlockVault(password: string): Promise<void> {
  return api.post<void>('/vault/unlock', { password });
}

export function lockVault(): Promise<void> {
  return api.post<void>('/vault/lock');
}

export function changePassword(oldPassword: string, newPassword: string): Promise<void> {
  return api.post<void>('/vault/change-password', {
    old_password: oldPassword,
    new_password: newPassword,
  });
}
