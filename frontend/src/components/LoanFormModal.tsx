import { useEffect, useState } from 'react';
import { createLoan, createLoanFromAccount, updateLoan } from '@/api/loans';
import type { Loan, LoanCandidate, LoanType, LoanCreatePayload } from '@/lib/loans';
import { LOAN_TYPE_LABELS } from '@/lib/loans';

interface Props {
  isOpen: boolean;
  loan?: Loan | null;
  /** Si fourni, la modale crée le prêt via createLoanFromAccount et lie le compte. */
  fromCandidate?: LoanCandidate | null;
  onClose: () => void;
  onSaved: () => void;
}

export function LoanFormModal({ isOpen, loan, fromCandidate, onClose, onSaved }: Props) {
  const editing = !!loan;
  const [name, setName] = useState('');
  const [loanType, setLoanType] = useState<LoanType>('immo');
  const [initialCapital, setInitialCapital] = useState('');
  const [monthlyPayment, setMonthlyPayment] = useState('');
  const [totalMonths, setTotalMonths] = useState('');
  const [startDate, setStartDate] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen) return;
    if (loan) {
      setName(loan.name);
      setLoanType(loan.loan_type);
      setInitialCapital(String(loan.initial_capital));
      setMonthlyPayment(String(loan.monthly_payment));
      setTotalMonths(String(loan.total_months));
      setStartDate(loan.start_date);
    } else if (fromCandidate) {
      setName(fromCandidate.label);
      setLoanType('immo');
      setInitialCapital(String(Math.abs(fromCandidate.balance)));
      setMonthlyPayment('');
      setTotalMonths('');
      setStartDate('');
    } else {
      setName(''); setLoanType('immo'); setInitialCapital('');
      setMonthlyPayment(''); setTotalMonths(''); setStartDate('');
    }
    setError(null);
  }, [isOpen, loan, fromCandidate]);

  async function submit() {
    setError(null);
    const ic = parseFloat(initialCapital);
    const mp = parseFloat(monthlyPayment);
    const tm = parseInt(totalMonths, 10);
    if (!name.trim() || !(ic > 0) || !(mp > 0) || !(tm > 0) || !startDate) {
      setError('Tous les champs sont obligatoires (montants > 0).');
      return;
    }
    const payload: LoanCreatePayload = {
      name: name.trim(), loan_type: loanType, initial_capital: ic,
      monthly_payment: mp, total_months: tm, start_date: startDate,
    };
    setSubmitting(true);
    try {
      if (editing && loan) {
        await updateLoan(loan.id, payload);
      } else if (fromCandidate) {
        await createLoanFromAccount({ ...payload, account_id: fromCandidate.account_id });
      } else {
        await createLoan(payload);
      }
      onSaved();
      onClose();
    } catch (e: any) {
      setError(e?.detail ?? 'Erreur à l\'enregistrement');
    } finally {
      setSubmitting(false);
    }
  }

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={onClose}>
      <div
        className="bg-mm-surface border border-mm-border rounded-[12px] p-6 w-full max-w-lg mx-4 flex flex-col gap-4"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-lg font-semibold text-mm-text">
          {editing ? 'Modifier le prêt' : fromCandidate ? `Créer un prêt depuis "${fromCandidate.label}"` : 'Nouveau prêt'}
        </h2>
        <div className="flex flex-col gap-3">
          <Field label="Nom">
            <input className={inputCls} value={name} onChange={(e) => setName(e.target.value)} placeholder="Ex. Crédit immo Paris" />
          </Field>
          <Field label="Type">
            <select className={inputCls} value={loanType} onChange={(e) => setLoanType(e.target.value as LoanType)}>
              {(Object.keys(LOAN_TYPE_LABELS) as LoanType[]).map((t) => (
                <option key={t} value={t}>{LOAN_TYPE_LABELS[t]}</option>
              ))}
            </select>
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Capital emprunté (€)">
              <input className={inputCls} type="number" value={initialCapital} onChange={(e) => setInitialCapital(e.target.value)} />
            </Field>
            <Field label="Mensualité (€)">
              <input className={inputCls} type="number" value={monthlyPayment} onChange={(e) => setMonthlyPayment(e.target.value)} />
            </Field>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Durée (mois)">
              <input className={inputCls} type="number" value={totalMonths} onChange={(e) => setTotalMonths(e.target.value)} />
            </Field>
            <Field label="Date 1ère mensualité">
              <input className={inputCls} type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
            </Field>
          </div>
          {error && <p className="text-sm text-mm-loss">{error}</p>}
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <button onClick={onClose} className="px-4 py-2 text-sm rounded-[8px] border border-mm-border text-mm-text-muted">
            Annuler
          </button>
          <button
            onClick={submit}
            disabled={submitting}
            className="px-4 py-2 bg-mm-gold text-mm-bg text-sm font-semibold rounded-[8px] disabled:opacity-50"
          >
            {submitting ? 'Enregistrement…' : editing ? 'Enregistrer' : 'Créer'}
          </button>
        </div>
      </div>
    </div>
  );
}

const inputCls = 'w-full px-3 py-2 bg-mm-surface-elevated border border-mm-border rounded-[8px] text-sm text-mm-text focus:outline-none focus:border-mm-gold';

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-xs text-mm-text-muted">{label}</span>
      {children}
    </label>
  );
}
