export type SectionType = 'income' | 'fixed_expense' | 'variable_expense';

export interface BudgetItem {
  id: number | string;
  label: string;
  amount: number;
  position: number;
  is_virtual: boolean;
}

export interface BudgetSection {
  id: number | string;
  name: string;
  section_type: SectionType;
  position: number;
  is_virtual: boolean;
  items: BudgetItem[];
}

export interface BudgetTotals {
  income: number;
  fixed_expense: number;
  variable_expense: number;
  expense: number;
  investment_capacity: number;
}

export interface BudgetView {
  sections: BudgetSection[];
  totals: BudgetTotals;
}

export const SECTION_TYPE_LABELS: Record<SectionType, string> = {
  income: 'Revenus',
  fixed_expense: 'Charges fixes',
  variable_expense: 'Charges variables',
};
