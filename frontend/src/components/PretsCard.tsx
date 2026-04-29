import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { getLoansSummary } from '@/api/loans';
import type { LoanSummary } from '@/lib/loans';
import { formatCurrency, formatShortDate } from '@/lib/format';

export function PretsCard() {
  const [summary, setSummary] = useState<LoanSummary | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    getLoansSummary()
      .then((s) => { if (!cancelled) setSummary(s); })
      .catch(() => { if (!cancelled) setSummary(null); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  return (
    <div className="bg-mm-surface border border-mm-border rounded-[12px] px-5 py-4 flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <span className="font-medium text-mm-text">Prêts</span>
        <Link to="/prets" className="text-sm text-mm-gold hover:underline">Voir tout →</Link>
      </div>
      {loading && <div className="text-sm text-mm-text-muted">Chargement…</div>}
      {!loading && (!summary || summary.active_count === 0) && (
        <div className="text-sm text-mm-text-muted">
          Aucun prêt actif. <Link to="/prets" className="text-mm-gold hover:underline">En déclarer un</Link>.
        </div>
      )}
      {!loading && summary && summary.active_count > 0 && (
        <>
          <div>
            <div className="text-2xl font-mono text-mm-text">
              {formatCurrency(summary.total_monthly_payment, 'EUR')}
              <span className="text-sm text-mm-text-muted font-sans"> / mois</span>
            </div>
            <div className="text-xs text-mm-text-muted">
              {summary.active_count} prêt{summary.active_count > 1 ? 's' : ''} actif{summary.active_count > 1 ? 's' : ''}
            </div>
          </div>
          <div className="text-xs text-mm-text-muted">
            Restant total : <span className="text-mm-text font-mono">{formatCurrency(summary.total_amount_remaining, 'EUR')}</span>
            {summary.last_end_date && <>, jusqu'en <span className="text-mm-text">{formatShortDate(summary.last_end_date)}</span></>}
          </div>
        </>
      )}
    </div>
  );
}
