import { useEffect, useState } from 'react';
import { createTarget } from '@/api/targets';
import { getAccounts } from '@/api/accounts';
import type { TargetCreatePayload, AllocationKind } from '@/lib/targets';

interface Account { id: string; name?: string | null; type?: string | null; }

interface Props {
  isOpen: boolean;
  onClose: () => void;
  onCreated: () => void;
}

export function TargetCreateModal({ isOpen, onClose, onCreated }: Props) {
  const [type, setType] = useState<'asset' | 'bucket'>('bucket');
  const [name, setName] = useState('');
  const [targetAmount, setTargetAmount] = useState('');
  const [accounts, setAccounts] = useState<Account[]>([]);

  const [assetAccount, setAssetAccount] = useState('');
  const [assetSymbol, setAssetSymbol] = useState('');

  const [slices, setSlices] = useState<Array<{
    account_id: string; allocation_kind: AllocationKind; allocation_value: number;
  }>>([]);

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (isOpen) {
      getAccounts().then(setAccounts).catch(() => setAccounts([]));
      setName('');
      setTargetAmount('');
      setAssetAccount('');
      setAssetSymbol('');
      setSlices([]);
      setError(null);
    }
  }, [isOpen]);

  async function submit() {
    setError(null);
    const amount = parseFloat(targetAmount);
    if (!name.trim() || !(amount > 0)) {
      setError('Nom et montant cible obligatoires');
      return;
    }
    const payload: TargetCreatePayload = { name, type, target_amount: amount, slices: [] };
    if (type === 'asset') {
      if (!assetAccount || !assetSymbol) {
        setError('Compte et symbole obligatoires pour une cible sur actif');
        return;
      }
      payload.asset_account_id = assetAccount;
      payload.asset_symbol = assetSymbol;
    } else {
      payload.slices = slices;
    }
    setSubmitting(true);
    try {
      await createTarget(payload);
      onCreated();
      onClose();
    } catch (e: any) {
      setError(e?.detail ?? 'Erreur à la création');
    } finally {
      setSubmitting(false);
    }
  }

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={onClose}>
      <div
        className="bg-mm-surface border border-mm-border rounded-[16px] w-full max-w-2xl p-6 flex flex-col gap-5 max-h-[85vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-lg font-semibold text-mm-text">Nouvelle cible</h2>

        {/* Type tabs */}
        <div className="flex gap-1 bg-mm-surface-elevated p-1 rounded-[8px]">
          {(['bucket', 'asset'] as const).map((t) => (
            <button
              key={t}
              onClick={() => setType(t)}
              className={`flex-1 py-1.5 text-sm rounded-[6px] transition-colors ${
                type === t
                  ? 'bg-mm-surface text-mm-text font-medium'
                  : 'text-mm-text-muted hover:text-mm-text-secondary'
              }`}
            >
              {t === 'bucket' ? 'Bucket abstrait' : 'Actif précis'}
            </button>
          ))}
        </div>

        <p className="text-sm text-mm-text-muted -mt-2">
          {type === 'bucket'
            ? 'Composé de slices d\'allocation sur tes comptes (ex. 30 % du CTO + 1 500 € du Livret A).'
            : 'Lié à une position spécifique (ex. atteindre 5 000 € sur VWCE).'}
        </p>

        <div className="flex flex-col gap-3">
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-medium text-mm-text-secondary">Nom</label>
            <input
              type="text"
              placeholder="Ex. Apport immo"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="bg-mm-surface-elevated border border-mm-border rounded-[8px] px-3 py-2 text-sm text-mm-text placeholder:text-mm-text-muted outline-none focus:border-mm-gold transition-colors"
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-medium text-mm-text-secondary">Montant cible (€)</label>
            <input
              type="number"
              value={targetAmount}
              onChange={(e) => setTargetAmount(e.target.value)}
              className="bg-mm-surface-elevated border border-mm-border rounded-[8px] px-3 py-2 text-sm text-mm-text outline-none focus:border-mm-gold transition-colors"
            />
          </div>

          {type === 'asset' && (
            <>
              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-medium text-mm-text-secondary">Compte</label>
                <select
                  value={assetAccount}
                  onChange={(e) => setAssetAccount(e.target.value)}
                  className="bg-mm-surface-elevated border border-mm-border rounded-[8px] px-3 py-2 text-sm text-mm-text outline-none focus:border-mm-gold transition-colors appearance-none cursor-pointer"
                >
                  <option value="">Sélectionner un compte</option>
                  {accounts.map((a) => (
                    <option key={a.id} value={a.id}>{a.name ?? a.id}</option>
                  ))}
                </select>
              </div>
              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-medium text-mm-text-secondary">Symbole / ISIN</label>
                <input
                  type="text"
                  placeholder="VWCE / IE00BK5BQT80"
                  value={assetSymbol}
                  onChange={(e) => setAssetSymbol(e.target.value)}
                  className="bg-mm-surface-elevated border border-mm-border rounded-[8px] px-3 py-2 text-sm text-mm-text placeholder:text-mm-text-muted outline-none focus:border-mm-gold transition-colors"
                />
              </div>
            </>
          )}

          {type === 'bucket' && (
            <SliceListEditor accounts={accounts} slices={slices} onChange={setSlices} />
          )}

          {error && <p className="text-sm" style={{ color: 'var(--mm-loss)' }}>{error}</p>}
        </div>

        <div className="flex justify-end gap-3 pt-2">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm text-mm-text-muted hover:text-mm-text-secondary transition-colors"
          >
            Annuler
          </button>
          <button
            onClick={submit}
            disabled={submitting}
            className="px-5 py-2 bg-mm-gold text-mm-bg text-sm font-semibold rounded-[8px] disabled:opacity-50 transition-opacity"
          >
            {submitting ? 'Création...' : 'Créer'}
          </button>
        </div>
      </div>
    </div>
  );
}

function SliceListEditor({
  accounts, slices, onChange,
}: {
  accounts: Account[];
  slices: Array<{ account_id: string; allocation_kind: AllocationKind; allocation_value: number; }>;
  onChange: (s: typeof slices) => void;
}) {
  function addSlice() {
    onChange([...slices, { account_id: accounts[0]?.id ?? '', allocation_kind: 'percent', allocation_value: 0 }]);
  }
  function update(idx: number, patch: Partial<{ account_id: string; allocation_kind: AllocationKind; allocation_value: number }>) {
    const next = slices.slice();
    next[idx] = { ...next[idx], ...patch } as { account_id: string; allocation_kind: AllocationKind; allocation_value: number };
    onChange(next);
  }
  function remove(idx: number) {
    onChange(slices.filter((_, i) => i !== idx));
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-mm-text-secondary">Slices d'allocation</span>
        <button
          onClick={addSlice}
          className="px-3 py-1 text-xs border border-mm-border text-mm-text-muted hover:text-mm-text-secondary rounded-[6px] transition-colors"
        >
          + Ajouter
        </button>
      </div>
      {slices.length === 0 && (
        <p className="text-xs text-mm-text-muted">Ajoute au moins une slice (un compte source + montant ou %).</p>
      )}
      {slices.map((s, i) => (
        <div key={i} className="flex gap-2 items-end">
          <div className="flex-1 flex flex-col gap-1">
            <label className="text-xs text-mm-text-muted">Compte</label>
            <select
              value={s.account_id}
              onChange={(e) => update(i, { account_id: e.target.value })}
              className="bg-mm-surface-elevated border border-mm-border rounded-[8px] px-2 py-1.5 text-sm text-mm-text outline-none focus:border-mm-gold transition-colors appearance-none cursor-pointer"
            >
              {accounts.map((a) => (
                <option key={a.id} value={a.id}>{a.name ?? a.id}</option>
              ))}
            </select>
          </div>
          <div className="w-24 flex flex-col gap-1">
            <label className="text-xs text-mm-text-muted">Type</label>
            <select
              value={s.allocation_kind}
              onChange={(e) => update(i, { allocation_kind: e.target.value as AllocationKind })}
              className="bg-mm-surface-elevated border border-mm-border rounded-[8px] px-2 py-1.5 text-sm text-mm-text outline-none focus:border-mm-gold transition-colors appearance-none cursor-pointer"
            >
              <option value="percent">%</option>
              <option value="amount">€</option>
            </select>
          </div>
          <div className="w-24 flex flex-col gap-1">
            <label className="text-xs text-mm-text-muted">Valeur</label>
            <input
              type="number"
              value={s.allocation_value}
              onChange={(e) => update(i, { allocation_value: parseFloat(e.target.value) || 0 })}
              className="bg-mm-surface-elevated border border-mm-border rounded-[8px] px-2 py-1.5 text-sm text-mm-text outline-none focus:border-mm-gold transition-colors"
            />
          </div>
          <button
            onClick={() => remove(i)}
            className="px-2 py-1.5 text-sm text-red-400 hover:text-red-300 transition-colors mb-[1px]"
          >
            ×
          </button>
        </div>
      ))}
    </div>
  );
}
