import { api } from './client';
import type { Loan, LoanCandidate, LoanCreatePayload, LoanSummary, LoanType } from '../lib/loans';

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

export function listLoanCandidates(): Promise<LoanCandidate[]> {
  return api.get<LoanCandidate[]>('/loans/candidates');
}

export function linkLoanToAccount(loanId: number, accountId: string): Promise<Loan> {
  return api.post<Loan>(`/loans/${loanId}/link`, { account_id: accountId });
}

export function unlinkLoanFromAccount(loanId: number): Promise<void> {
  return api.del(`/loans/${loanId}/link`);
}

export function ignoreLoanCandidate(accountId: string): Promise<void> {
  // L'account_id contient des ":" qui doivent être encodés dans l'URL
  return api.post<void>(`/loans/candidates/${encodeURIComponent(accountId)}/ignore`, {});
}

export function unignoreLoanCandidate(accountId: string): Promise<void> {
  return api.del(`/loans/candidates/${encodeURIComponent(accountId)}/ignore`);
}

export interface FromAccountPayload {
  account_id: string;
  name: string;
  loan_type: LoanType;
  initial_capital: number;
  monthly_payment: number;
  total_months: number;
  start_date: string;
}

export function createLoanFromAccount(payload: FromAccountPayload): Promise<Loan> {
  return api.post<Loan>('/loans/from-account', payload);
}
