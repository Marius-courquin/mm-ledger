import { useEffect, useState } from 'react';
import { Pencil, Trash2, Plus } from 'lucide-react';
import { listLoans, deleteLoan } from '@/api/loans';
import type { Loan } from '@/lib/loans';
import { LOAN_TYPE_LABELS } from '@/lib/loans';
import { LoanFormModal } from '@/components/LoanFormModal';
import { formatCurrency, formatShortDate } from '@/lib/format';

export function Prets() {
  const [loans, setLoans] = useState<Loan[]>([]);
  const [loading, setLoading] = useState(true);
  const [showArchived, setShowArchived] = useState(false);
  const [editing, setEditing] = useState<Loan | null>(null);
  const [creating, setCreating] = useState(false);

  async function load() {
    setLoading(true);
    try { setLoans(await listLoans(showArchived)); }
    finally { setLoading(false); }
  }

  useEffect(() => { load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [showArchived]);

  async function handleDelete(loan: Loan) {
    if (!confirm(`Supprimer "${loan.name}" ?`)) return;
    await deleteLoan(loan.id);
    load();
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-[28px] font-semibold text-mm-text">Prêts</h1>
        <div className="flex gap-2">
          <button
            onClick={() => setShowArchived((v) => !v)}
            className={`px-4 py-2 text-sm rounded-[8px] border transition-colors ${
              showArchived ? 'border-mm-gold text-mm-gold' : 'border-mm-border text-mm-text-muted'
            }`}
          >
            {showArchived ? 'Afficher actifs' : 'Afficher archivés'}
          </button>
          <button
            onClick={() => setCreating(true)}
            className="px-4 py-2 bg-mm-gold text-mm-bg text-sm font-semibold rounded-[8px] flex items-center gap-1.5 hover:opacity-90"
          >
            <Plus size={16} /> Nouveau prêt
          </button>
        </div>
      </div>

      {loading && <div className="text-sm text-mm-text-muted">Chargement…</div>}

      {!loading && loans.length === 0 && (
        <div className="bg-mm-surface border border-mm-border rounded-[12px] px-5 py-12 text-center text-sm text-mm-text-muted">
          Aucun prêt déclaré. Crée ton premier prêt pour démarrer le suivi.
        </div>
      )}

      {!loading && loans.length > 0 && (
        <div className="bg-mm-surface border border-mm-border rounded-[12px] overflow-hidden">
          <table className="w-full text-sm">
            <thead className="border-b border-mm-border text-xs text-mm-text-muted">
              <tr>
                <Th>Nom</Th>
                <Th>Type</Th>
                <Th align="right">Mensualité</Th>
                <Th align="right">Restantes</Th>
                <Th>Fin</Th>
                <Th align="right">Restant total</Th>
                <Th align="right">Progression</Th>
                <Th>Actions</Th>
              </tr>
            </thead>
            <tbody>
              {loans.map((l) => (
                <tr key={l.id} className="border-b border-mm-border last:border-0 hover:bg-mm-surface-elevated/30">
                  <td className="px-4 py-3 text-mm-text">{l.name}</td>
                  <td className="px-4 py-3 text-mm-text-muted">{LOAN_TYPE_LABELS[l.loan_type]}</td>
                  <td className="px-4 py-3 text-right font-mono text-mm-text">{formatCurrency(l.monthly_payment, 'EUR')}</td>
                  <td className="px-4 py-3 text-right text-mm-text-muted">{l.months_remaining} / {l.total_months}</td>
                  <td className="px-4 py-3 text-mm-text-muted">{formatShortDate(l.end_date)}</td>
                  <td className="px-4 py-3 text-right font-mono text-mm-text">{formatCurrency(l.amount_remaining, 'EUR')}</td>
                  <td className="px-4 py-3 text-right">
                    <div className="flex items-center justify-end gap-2">
                      <div className="w-20 bg-mm-surface-elevated rounded-full h-1.5 overflow-hidden">
                        <div className="h-full bg-mm-gold rounded-full" style={{ width: `${l.progress_pct}%` }} />
                      </div>
                      <span className="text-xs text-mm-text-muted w-10 text-right">{l.progress_pct.toFixed(0)} %</span>
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex gap-2">
                      <button onClick={() => setEditing(l)} className="text-mm-text-muted hover:text-mm-gold"><Pencil size={14} /></button>
                      <button onClick={() => handleDelete(l)} className="text-mm-text-muted hover:text-mm-loss"><Trash2 size={14} /></button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <LoanFormModal isOpen={creating} onClose={() => setCreating(false)} onSaved={load} />
      <LoanFormModal isOpen={!!editing} loan={editing} onClose={() => setEditing(null)} onSaved={load} />
    </div>
  );
}

function Th({ children, align = 'left' }: { children: React.ReactNode; align?: 'left' | 'right' }) {
  return <th className={`px-4 py-3 font-medium ${align === 'right' ? 'text-right' : 'text-left'}`}>{children}</th>;
}
