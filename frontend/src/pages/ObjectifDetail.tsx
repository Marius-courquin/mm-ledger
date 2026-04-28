import { useCallback, useEffect, useState } from 'react';
import { useNavigate, useParams, Link } from 'react-router-dom';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts';
import { getTarget, deleteTarget, getProgression, updateTarget } from '@/api/targets';
import { getAccounts } from '@/api/accounts';
import { TargetSliceEditor } from '@/components/TargetSliceEditor';
import type { Target, Progression } from '@/lib/targets';

interface Account { id: string; name?: string | null; }

export function ObjectifDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const targetId = Number(id);
  const [target, setTarget] = useState<Target | null>(null);
  const [progression, setProgression] = useState<Progression | null>(null);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [overrideInput, setOverrideInput] = useState('');

  const load = useCallback(async () => {
    const [t, p, accs] = await Promise.all([
      getTarget(targetId), getProgression(targetId), getAccounts(),
    ]);
    setTarget(t);
    setProgression(p);
    setAccounts(accs);
    setOverrideInput(t.rate_override == null ? '' : String(t.rate_override));
  }, [targetId]);

  useEffect(() => { load(); }, [load]);

  async function saveOverride() {
    const val = overrideInput.trim() === '' ? null : parseFloat(overrideInput);
    if (val !== null && Number.isNaN(val)) return;
    await updateTarget(targetId, { rate_override: val });
    load();
  }

  async function remove() {
    if (!confirm('Supprimer cette cible ?')) return;
    await deleteTarget(targetId);
    navigate('/objectifs');
  }

  if (!target || !progression) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-mm-gold border-t-transparent" />
      </div>
    );
  }

  const pct = Math.min(100, progression.progress_pct);
  const eta = progression.eta_months;
  const status = progression.eta_status;

  return (
    <div className="flex flex-col gap-6 max-w-5xl mx-auto">
      <div className="text-sm text-mm-text-muted">
        <Link to="/objectifs" className="hover:text-mm-text-secondary transition-colors">← Objectifs</Link>
      </div>

      <div className="flex items-start justify-between">
        <div className="flex flex-col gap-1">
          <h1 className="text-[28px] font-semibold text-mm-text">{target.name}</h1>
          <span className="inline-block text-[11px] font-medium px-2 py-0.5 rounded-full bg-mm-surface-elevated text-mm-text-muted w-fit">
            {target.type === 'asset' ? 'Actif précis' : 'Bucket'}
          </span>
        </div>
        <button
          onClick={remove}
          className="px-4 py-2 text-sm border border-red-400/40 text-red-400 hover:bg-red-400/10 rounded-[8px] transition-colors"
        >
          Supprimer
        </button>
      </div>

      {/* Progression */}
      <div className="bg-mm-surface border border-mm-border rounded-[12px] p-5 flex flex-col gap-3">
        <div className="flex justify-between items-end">
          <div>
            <div className="text-sm text-mm-text-muted">Valeur courante</div>
            <div className="text-3xl font-mono text-mm-text">{progression.current_value.toLocaleString('fr-FR')} €</div>
          </div>
          <div className="text-right">
            <div className="text-sm text-mm-text-muted">Cible</div>
            <div className="text-2xl font-mono text-mm-text">{target.target_amount.toLocaleString('fr-FR')} €</div>
          </div>
        </div>
        <div className="w-full bg-mm-surface-elevated rounded-full h-2 overflow-hidden">
          <div className="h-full rounded-full bg-mm-gain" style={{ width: `${pct}%` }} />
        </div>
        <div className="flex justify-between text-sm text-mm-text-muted">
          <span>{pct.toFixed(1)} % atteint</span>
          <span>
            {status === 'reached' && '🎉 Objectif atteint'}
            {status === 'ok' && eta != null && `Au rythme actuel (${progression.rate.toFixed(0)} €/mois) → ${Math.round(eta)} mois`}
            {status === 'insufficient' && 'Rythme insuffisant'}
          </span>
        </div>
      </div>

      {/* Historique */}
      <div className="bg-mm-surface border border-mm-border rounded-[12px] p-5 flex flex-col gap-3">
        <h2 className="text-base font-semibold text-mm-text">Historique</h2>
        {progression.history.length === 0 ? (
          <p className="text-sm text-mm-text-muted">Pas encore d'historique disponible.</p>
        ) : (
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={progression.history}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="date" />
              <YAxis />
              <Tooltip />
              <Line type="monotone" dataKey="value" stroke="var(--mm-gain)" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* Rythme estimé */}
      <div className="bg-mm-surface border border-mm-border rounded-[12px] p-5 flex flex-col gap-3">
        <h2 className="text-base font-semibold text-mm-text">Rythme estimé</h2>
        <div className="text-sm text-mm-text-muted">
          Source : {progression.rate_source === 'auto' ? 'calcul automatique sur 3 mois' : 'override manuel'}.
          Valeur : {progression.rate.toFixed(2)} €/mois.
        </div>
        <div className="flex gap-2 items-end">
          <div className="flex-1 flex flex-col gap-1.5">
            <label className="text-xs font-medium text-mm-text-secondary">Override (€/mois)</label>
            <input
              type="number"
              placeholder={progression.rate_source === 'auto' ? `auto: ${progression.rate.toFixed(0)}` : ''}
              value={overrideInput}
              onChange={(e) => setOverrideInput(e.target.value)}
              className="bg-mm-surface-elevated border border-mm-border rounded-[8px] px-3 py-2 text-sm text-mm-text placeholder:text-mm-text-muted outline-none focus:border-mm-gold transition-colors"
            />
          </div>
          <button
            onClick={saveOverride}
            className="px-4 py-2 bg-mm-gold text-mm-bg text-sm font-semibold rounded-[8px] transition-opacity hover:opacity-90"
          >
            Enregistrer
          </button>
        </div>
        <p className="text-xs text-mm-text-muted">Vide = retour au calcul automatique.</p>
      </div>

      {/* Slices (bucket uniquement) */}
      {target.type === 'bucket' && (
        <div className="bg-mm-surface border border-mm-border rounded-[12px] p-5 flex flex-col gap-3">
          <h2 className="text-base font-semibold text-mm-text">Composition (slices)</h2>
          <TargetSliceEditor
            targetId={targetId}
            slices={target.slices}
            accounts={accounts}
            onChange={load}
          />
        </div>
      )}

      {/* Position suivie (asset uniquement) */}
      {target.type === 'asset' && (
        <div className="bg-mm-surface border border-mm-border rounded-[12px] p-5 flex flex-col gap-3">
          <h2 className="text-base font-semibold text-mm-text">Position suivie</h2>
          <div className="text-sm text-mm-text flex flex-col gap-1">
            <p>Compte : <code className="bg-mm-surface-elevated px-1.5 py-0.5 rounded text-xs">{target.asset_account_id}</code></p>
            <p>Symbole : <code className="bg-mm-surface-elevated px-1.5 py-0.5 rounded text-xs">{target.asset_symbol}</code></p>
            <p className="text-mm-text-muted mt-1">
              La valeur courante est lue automatiquement depuis cette position.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
