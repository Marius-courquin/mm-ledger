import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { listTargets, getProgression } from '@/api/targets';
import type { Target, Progression } from '@/lib/targets';

interface Row { target: Target; progression?: Progression; }

export function ObjectifsCard() {
  const [rows, setRows] = useState<Row[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const targets = await listTargets(false);
        const enriched = await Promise.all(
          targets.map(async (t) => {
            try {
              const p = await getProgression(t.id);
              return { target: t, progression: p } as Row;
            } catch {
              return { target: t } as Row;
            }
          })
        );
        if (!cancelled) {
          enriched.sort((a, b) => (b.progression?.progress_pct ?? 0) - (a.progression?.progress_pct ?? 0));
          setRows(enriched.slice(0, 3));
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  return (
    <div className="bg-mm-surface border border-mm-border rounded-[12px] p-4 flex flex-col gap-3">
      <div className="flex justify-between items-center">
        <span className="text-sm font-semibold text-mm-text">Objectifs</span>
        <Link to="/objectifs" className="text-xs text-mm-gold hover:opacity-80 transition-opacity">Voir tout →</Link>
      </div>
      {loading && <div className="text-sm text-mm-text-muted">Chargement…</div>}
      {!loading && rows.length === 0 && (
        <div className="text-sm text-mm-text-muted">
          Pas encore de cible.{' '}
          <Link to="/objectifs" className="text-mm-gold hover:opacity-80 transition-opacity">En créer une</Link>.
        </div>
      )}
      {rows.map((r) => {
        const pct = Math.min(100, r.progression?.progress_pct ?? 0);
        return (
          <div key={r.target.id} className="flex flex-col gap-1">
            <div className="flex justify-between text-sm">
              <Link to={`/objectifs/${r.target.id}`} className="text-mm-text hover:underline truncate max-w-[70%]">
                {r.target.name}
              </Link>
              <span className="text-mm-text-muted tabular-nums">{pct.toFixed(0)} %</span>
            </div>
            <div className="w-full bg-mm-surface-elevated rounded-full h-1.5 overflow-hidden">
              <div className="h-full rounded-full bg-mm-gain" style={{ width: `${pct}%` }} />
            </div>
          </div>
        );
      })}
    </div>
  );
}
