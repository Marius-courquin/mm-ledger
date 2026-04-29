export type LoanType = 'immo' | 'conso' | 'auto' | 'other';

export interface Loan {
  id: number;
  name: string;
  loan_type: LoanType;
  initial_capital: number;
  monthly_payment: number;
  total_months: number;
  start_date: string;
  archived: boolean;
  created_at: string;
  end_date: string;
  months_paid: number;
  months_remaining: number;
  amount_remaining: number;
  progress_pct: number;
  is_active: boolean;
}

export interface LoanCreatePayload {
  name: string;
  loan_type: LoanType;
  initial_capital: number;
  monthly_payment: number;
  total_months: number;
  start_date: string;
}

export interface LoanSummary {
  total_monthly_payment: number;
  total_amount_remaining: number;
  last_end_date: string | null;
  active_count: number;
}

export const LOAN_TYPE_LABELS: Record<LoanType, string> = {
  immo: 'Immobilier',
  conso: 'Consommation',
  auto: 'Auto',
  other: 'Autre',
};
