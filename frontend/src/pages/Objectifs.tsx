import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { listTargets, getProgression } from '@/api/targets';
import type { Target, Progression } from '@/lib/targets';
import { TargetCreateModal } from '@/components/TargetCreateModal';

interface TargetWithProgression extends Target {
  progression?: Progression;
}

export function Objectifs() {
  const [targets, setTargets] = useState<TargetWithProgression[]>([]);
  const [loading, setLoading] = useState(true);
  const [showArchived, setShowArchived] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);

  async function load() {
    setLoading(true);
    try {
      const list = await listTargets(showArchived);
      const withProg = await Promise.all(
        list.map(async (t) => {
          try {
            const p = await getProgression(t.id);
            return { ...t, progression: p } as TargetWithProgression;
          } catch {
            return t as TargetWithProgression;
          }
        })
      );
      setTargets(withProg);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showArchived]);

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-[28px] font-semibold text-mm-text">Objectifs</h1>
        <div className="flex gap-2">
          <button
            onClick={() => setShowArchived((v) => !v)}
            className={`px-4 py-2 text-sm rounded-[8px] border transition-colors ${
              showArchived
                ? 'border-mm-gold text-mm-gold'
                : 'border-mm-border text-mm-text-muted hover:text-mm-text-secondary'
            }`}
          >
            {showArchived ? 'Afficher actives' : 'Afficher archivées'}
          </button>
          <button
            onClick={() => setCreateOpen(true)}
            className="px-4 py-2 bg-mm-gold text-mm-bg text-sm font-semibold rounded-[8px] transition-opacity hover:opacity-90"
          >
            Nouvelle cible
          </button>
        </div>
      </div>

      {loading && <div className="text-sm text-mm-text-muted">Chargement…</div>}

      {!loading && targets.length === 0 && (
        <div className="bg-mm-surface border border-mm-border rounded-[12px] px-5 py-12 text-center text-sm text-mm-text-muted">
          Aucune cible pour l'instant. Crée ta première cible pour démarrer.
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {targets.map((t) => {
          const pct = Math.min(100, t.progression?.progress_pct ?? 0);
          const eta = t.progression?.eta_months;
          const status = t.progression?.eta_status;
          return (
            <Link
              key={t.id}
              to={`/objectifs/${t.id}`}
              className="bg-mm-surface border border-mm-border rounded-[12px] p-4 flex flex-col gap-3 hover:border-mm-gold/40 transition-colors"
            >
              <div className="flex justify-between items-start">
                <div>
                  <div className="font-medium text-mm-text">{t.name}</div>
                  <span className="mt-1 inline-block text-[11px] font-medium px-2 py-0.5 rounded-full bg-mm-surface-elevated text-mm-text-muted">
                    {t.type === 'asset' ? 'Actif' : 'Bucket'}
                  </span>
                </div>
                <div className="text-right">
                  <div className="text-xs text-mm-text-muted">cible</div>
                  <div className="font-mono text-mm-text">{t.target_amount.toLocaleString('fr-FR')} €</div>
                </div>
              </div>
              <div className="flex flex-col gap-1.5">
                <div className="w-full bg-mm-surface-elevated rounded-full h-1.5 overflow-hidden">
                  <div
                    className="h-full rounded-full bg-mm-gain"
                    style={{ width: `${pct}%` }}
                  />
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-mm-text">{(t.progression?.current_value ?? 0).toLocaleString('fr-FR')} €</span>
                  <span className="text-mm-text-muted">{pct.toFixed(1)} %</span>
                </div>
                <div className="text-xs text-mm-text-muted">
                  {status === 'reached' && '🎉 Atteint'}
                  {status === 'ok' && eta != null && `À ton rythme : ${Math.round(eta)} mois`}
                  {status === 'insufficient' && 'Rythme insuffisant'}
                </div>
              </div>
            </Link>
          );
        })}
      </div>

      <TargetCreateModal isOpen={createOpen} onClose={() => setCreateOpen(false)} onCreated={load} />
    </div>
  );
}
