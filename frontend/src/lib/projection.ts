// frontend/src/lib/projection.ts
export type ProjectionCategory = 'cash' | 'market';

export interface ProjectionSettings {
  cash_annual_rate: number;
  market_annual_rate: number;
  cash_monthly_contribution: number;
  market_monthly_contribution: number;
  horizon_years: number;
}

export interface AccountCategorization {
  account_id: string;
  category: ProjectionCategory;
  auto: boolean;
}

export interface ProjectionPoint {
  month_offset: number;
  cash: number;
  market: number;
  total: number;
  loan_monthly_active: number;
}

export interface ProjectionStartingState {
  cash: number;
  market: number;
  loan_monthly: number;
}

export interface ProjectionResult {
  settings: ProjectionSettings;
  starting_state: ProjectionStartingState;
  points: ProjectionPoint[];
  classifications: AccountCategorization[];
}

export interface ProjectionSettingsView {
  settings: ProjectionSettings;
  classifications: AccountCategorization[];
}
