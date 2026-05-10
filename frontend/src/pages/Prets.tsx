import { useEffect, useState } from 'react';
import { Pencil, Trash2, Plus } from 'lucide-react';
import { listLoans, deleteLoan, listLoanCandidates, linkLoanToAccount, ignoreLoanCandidate } from '@/api/loans';
import type { Loan, LoanCandidate } from '@/lib/loans';
import { LOAN_TYPE_LABELS } from '@/lib/loans';
import { LoanFormModal } from '@/components/LoanFormModal';
import { LoanCandidates } from '@/components/LoanCandidates';
import { formatCurrency, formatShortDate } from '@/lib/format';

export function Prets() {
  const [loans, setLoans] = useState<Loan[]>([]);
  const [candidates, setCandidates] = useState<LoanCandidate[]>([]);
  const [loading, setLoading] = useState(true);
  const [showArchived, setShowArchived] = useState(false);
  const [editing, setEditing] = useState<Loan | null>(null);
  const [creating, setCreating] = useState(false);
  const [fromCandidate, setFromCandidate] = useState<LoanCandidate | null>(null);

  // Modale "Lier à un prêt existant"
  const [linkingCandidate, setLinkingCandidate] = useState<LoanCandidate | null>(null);
  const [selectedLoanId, setSelectedLoanId] = useState<number | ''>('');
  const [linking, setLinking] = useState(false);
  const [linkError, setLinkError] = useState<string | null>(null);

  async function loadLoans() {
    try { setLoans(await listLoans(showArchived)); }
    catch { /* silencieux */ }
  }

  async function loadCandidates() {
    try { setCandidates(await listLoanCandidates()); }
    catch { /* silencieux — endpoint peut ne pas être disponible */ }
  }

  async function load() {
    setLoading(true);
    try { await Promise.all([loadLoans(), loadCandidates()]); }
    finally { setLoading(false); }
  }

  useEffect(() => { load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [showArchived]);

  async function handleDelete(loan: Loan) {
    if (!confirm(`Supprimer "${loan.name}" ?`)) return;
    await deleteLoan(loan.id);
    load();
  }

  function handleCreateFromCandidate(c: LoanCandidate) {
    setFromCandidate(c);
  }

  function handleLinkCandidate(c: LoanCandidate) {
    setLinkingCandidate(c);
    setSelectedLoanId('');
    setLinkError(null);
  }

  async function handleIgnoreCandidate(c: LoanCandidate) {
    await ignoreLoanCandidate(c.account_id);
    setCandidates((prev) => prev.filter((x) => x.account_id !== c.account_id));
    loadCandidates();
  }

  async function submitLink() {
    if (!linkingCandidate || selectedLoanId === '') return;
    setLinking(true);
    setLinkError(null);
    try {
      await linkLoanToAccount(Number(selectedLoanId), linkingCandidate.account_id);
      setLinkingCandidate(null);
      load();
    } catch (e: any) {
      setLinkError(e?.detail ?? 'Erreur lors de la liaison');
    } finally {
      setLinking(false);
    }
  }

  const activeLoans = loans.filter((l) => l.is_active && !l.archived);

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

      {/* Candidats détectés via connecteurs bancaires */}
      <LoanCandidates
        candidates={candidates}
        onLink={handleLinkCandidate}
        onCreate={handleCreateFromCandidate}
        onIgnore={handleIgnoreCandidate}
      />

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
                  <td className="px-4 py-3 text-mm-text">
                    <div className="flex flex-col">
                      <span>{l.name}</span>
                      {l.linked_account_id && (
                        <span className="text-xs text-mm-text-muted mt-0.5">
                          Lié à : <span className="font-medium">{l.linked_label ?? l.linked_account_id}</span>
                          {l.amount_source === 'bank' ? ' · solde synchronisé' : ' · calcul calendaire'}
                        </span>
                      )}
                    </div>
                  </td>
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

      {/* Modale création standard */}
      <LoanFormModal isOpen={creating} onClose={() => setCreating(false)} onSaved={load} />

      {/* Modale modification */}
      <LoanFormModal isOpen={!!editing} loan={editing} onClose={() => setEditing(null)} onSaved={load} />

      {/* Modale création depuis candidat (préremplie) */}
      <LoanFormModal
        isOpen={!!fromCandidate}
        fromCandidate={fromCandidate}
        onClose={() => setFromCandidate(null)}
        onSaved={() => { setFromCandidate(null); load(); }}
      />

      {/* Modale lier candidat à un prêt existant */}
      {linkingCandidate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={() => setLinkingCandidate(null)}>
          <div
            className="bg-mm-surface border border-mm-border rounded-[12px] p-6 w-full max-w-md mx-4 flex flex-col gap-4"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="text-lg font-semibold text-mm-text">Lier à un prêt existant</h2>
            <p className="text-sm text-mm-text-muted">
              Compte : <span className="font-medium text-mm-text">{linkingCandidate.label}</span>
            </p>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-mm-text-muted">Prêt à lier</span>
              <select
                className="w-full px-3 py-2 bg-mm-surface-elevated border border-mm-border rounded-[8px] text-sm text-mm-text focus:outline-none focus:border-mm-gold"
                value={selectedLoanId}
                onChange={(e) => setSelectedLoanId(e.target.value === '' ? '' : Number(e.target.value))}
              >
                <option value="">— Choisir un prêt —</option>
                {activeLoans.map((l) => (
                  <option key={l.id} value={l.id}>{l.name}</option>
                ))}
              </select>
            </label>
            {linkError && <p className="text-sm text-mm-loss">{linkError}</p>}
            {activeLoans.length === 0 && (
              <p className="text-xs text-mm-text-muted">Aucun prêt actif disponible. Crée d'abord un prêt.</p>
            )}
            <div className="flex justify-end gap-2 pt-2">
              <button
                onClick={() => setLinkingCandidate(null)}
                className="px-4 py-2 text-sm rounded-[8px] border border-mm-border text-mm-text-muted"
              >
                Annuler
              </button>
              <button
                onClick={submitLink}
                disabled={linking || selectedLoanId === ''}
                className="px-4 py-2 bg-mm-gold text-mm-bg text-sm font-semibold rounded-[8px] disabled:opacity-50"
              >
                {linking ? 'Liaison…' : 'Lier'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function Th({ children, align = 'left' }: { children: React.ReactNode; align?: 'left' | 'right' }) {
  return <th className={`px-4 py-3 font-medium ${align === 'right' ? 'text-right' : 'text-left'}`}>{children}</th>;
}
