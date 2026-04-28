import { api } from './client';
import type {
  Target, Progression, Slice, TargetCreatePayload, AllocationKind,
} from '../lib/targets';

export function listTargets(archived = false): Promise<Target[]> {
  return api.get<Target[]>('/targets', { archived });
}

export function getTarget(id: number): Promise<Target> {
  return api.get<Target>(`/targets/${id}`);
}

export function createTarget(payload: TargetCreatePayload): Promise<Target> {
  return api.post<Target>('/targets', payload);
}

export function updateTarget(id: number, patch: Partial<{
  name: string; target_amount: number; rate_override: number | null; archived: boolean;
}>): Promise<Target> {
  return api.put<Target>(`/targets/${id}`, patch);
}

export function deleteTarget(id: number): Promise<void> {
  return api.del(`/targets/${id}`);
}

export function addSlice(targetId: number, payload: {
  account_id: string; allocation_kind: AllocationKind; allocation_value: number;
}): Promise<Slice> {
  return api.post<Slice>(`/targets/${targetId}/slices`, payload);
}

export function updateSlice(targetId: number, sliceId: number, patch: Partial<{
  account_id: string; allocation_kind: AllocationKind; allocation_value: number;
}>): Promise<Slice> {
  return api.put<Slice>(`/targets/${targetId}/slices/${sliceId}`, patch);
}

export function deleteSlice(targetId: number, sliceId: number): Promise<void> {
  return api.del(`/targets/${targetId}/slices/${sliceId}`);
}

export function getProgression(targetId: number): Promise<Progression> {
  return api.get<Progression>(`/targets/${targetId}/progression`);
}
