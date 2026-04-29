import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { getBudget } from '@/api/budget';
import type { BudgetTotals } from '@/lib/budget';
import { formatCurrency } from '@/lib/format';

export function BudgetCard() {
  const [totals, setTotals] = useState<BudgetTotals | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    getBudget()
      .then((b) => { if (!cancelled) setTotals(b.totals); })
      .catch(() => { if (!cancelled) setTotals(null); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  return (
    <div className="bg-mm-surface border border-mm-border rounded-[12px] px-5 py-4 flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <span className="font-medium text-mm-text">Budget</span>
        <Link to="/budget" className="text-sm text-mm-gold hover:underline">Voir →</Link>
      </div>
      {loading && <div className="text-sm text-mm-text-muted">Chargement…</div>}
      {!loading && (!totals || (totals.income === 0 && totals.expense === 0)) && (
        <div className="text-sm text-mm-text-muted">
          Pas encore de budget. <Link to="/budget" className="text-mm-gold hover:underline">En créer un</Link>.
        </div>
      )}
      {!loading && totals && (totals.income > 0 || totals.expense > 0) && (
        <>
          <div>
            <div className={`text-2xl font-mono ${totals.investment_capacity >= 0 ? 'text-mm-gain' : 'text-mm-loss'}`}>
              {formatCurrency(totals.investment_capacity, 'EUR')}
              <span className="text-sm text-mm-text-muted font-sans"> / mois</span>
            </div>
            <div className="text-xs text-mm-text-muted">Capacité d'investissement</div>
          </div>
          <div className="text-xs text-mm-text-muted">
            Revenus : <span className="text-mm-text font-mono">{formatCurrency(totals.income, 'EUR')}</span> ·
            Charges : <span className="text-mm-text font-mono">{formatCurrency(totals.expense, 'EUR')}</span>
          </div>
        </>
      )}
    </div>
  );
}
