import { api } from './client';
import type { Loan, LoanCreatePayload, LoanSummary } from '../lib/loans';

export function listLoans(archived = false): Promise<Loan[]> {
  return api.get<Loan[]>('/loans', { archived });
}

export function getLoan(id: number): Promise<Loan> {
  return api.get<Loan>(`/loans/${id}`);
}

export function createLoan(payload: LoanCreatePayload): Promise<Loan> {
  return api.post<Loan>('/loans', payload);
}

export function updateLoan(id: number, patch: Partial<LoanCreatePayload & { archived: boolean }>): Promise<Loan> {
  return api.put<Loan>(`/loans/${id}`, patch);
}

export function deleteLoan(id: number): Promise<void> {
  return api.del(`/loans/${id}`);
}

export function getLoansSummary(): Promise<LoanSummary> {
  return api.get<LoanSummary>('/loans/summary');
}
