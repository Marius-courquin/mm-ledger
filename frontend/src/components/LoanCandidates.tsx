import type { LoanCandidate } from '../lib/loans';
import { formatCurrency } from '../lib/format';

interface Props {
  candidates: LoanCandidate[];
  onLink: (c: LoanCandidate) => void;
  onCreate: (c: LoanCandidate) => void;
  onIgnore: (c: LoanCandidate) => void;
}

export function LoanCandidates({ candidates, onLink, onCreate, onIgnore }: Props) {
  if (candidates.length === 0) return null;
  return (
    <div className="bg-mm-surface border border-mm-border rounded-[12px] p-4 flex flex-col gap-3">
      <div className="flex flex-col gap-1">
        <h2 className="text-base font-semibold text-mm-text">Candidats détectés</h2>
        <p className="text-xs text-mm-text-muted">
          Comptes de type prêt remontés par tes connecteurs bancaires.
        </p>
      </div>
      <div className="flex flex-col gap-2">
        {candidates.map((c) => (
          <div
            key={c.account_id}
            className="flex items-center justify-between p-3 rounded-lg bg-mm-surface-elevated"
          >
            <div className="flex flex-col">
              <span className="font-medium text-sm text-mm-text">{c.label}</span>
              <span className="text-xs text-mm-text-muted">
                {formatCurrency(c.balance, c.currency)} · {c.connector_type}
              </span>
            </div>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => onLink(c)}
                className="text-xs px-3 py-1.5 rounded-md border border-mm-border hover:bg-mm-surface text-mm-text"
              >
                Lier à un prêt
              </button>
              <button
                type="button"
                onClick={() => onCreate(c)}
                className="text-xs px-3 py-1.5 rounded-md border border-mm-border hover:bg-mm-surface text-mm-text"
              >
                Créer un prêt
              </button>
              <button
                type="button"
                onClick={() => onIgnore(c)}
                className="text-xs px-3 py-1.5 rounded-md text-mm-text-muted hover:text-mm-text"
              >
                Ignorer
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
