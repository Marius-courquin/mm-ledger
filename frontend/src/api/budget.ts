import { api } from './client';
import type { BudgetView, BudgetSection, BudgetItem, SectionType } from '../lib/budget';

export function getBudget(): Promise<BudgetView> {
  return api.get<BudgetView>('/budget');
}

export function createSection(payload: { name: string; section_type: SectionType; position?: number }): Promise<BudgetSection> {
  return api.post<BudgetSection>('/budget/sections', payload);
}

export function updateSection(id: number, patch: Partial<{ name: string; section_type: SectionType; position: number }>): Promise<BudgetSection> {
  return api.put<BudgetSection>(`/budget/sections/${id}`, patch);
}

export function deleteSection(id: number): Promise<void> {
  return api.del(`/budget/sections/${id}`);
}

export function createItem(sectionId: number, payload: { label: string; amount: number; position?: number }): Promise<BudgetItem> {
  return api.post<BudgetItem>(`/budget/sections/${sectionId}/items`, payload);
}

export function updateItem(id: number, patch: Partial<{ label: string; amount: number; position: number }>): Promise<BudgetItem> {
  return api.put<BudgetItem>(`/budget/items/${id}`, patch);
}

export function deleteItem(id: number): Promise<void> {
  return api.del(`/budget/items/${id}`);
}

export function applyToProjection(cashShare: number, marketShare: number): Promise<{
  cash_monthly_contribution: number;
  market_monthly_contribution: number;
  investment_capacity: number;
}> {
  return api.post('/budget/apply-to-projection', { cash_share: cashShare, market_share: marketShare });
}
