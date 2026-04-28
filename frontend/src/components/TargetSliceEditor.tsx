import { useState } from 'react';
import type { Slice, AllocationKind } from '@/lib/targets';
import { addSlice, updateSlice, deleteSlice } from '@/api/targets';

interface Account { id: string; name?: string | null; }

interface Props {
  targetId: number;
  slices: Slice[];
  accounts: Account[];
  onChange: () => void;
}

export function TargetSliceEditor({ targetId, slices, accounts, onChange }: Props) {
  const [pending, setPending] = useState(false);

  async function add() {
    setPending(true);
    try {
      await addSlice(targetId, {
        account_id: accounts[0]?.id ?? '',
        allocation_kind: 'percent',
        allocation_value: 0,
      });
      onChange();
    } finally { setPending(false); }
  }

  async function update(slice: Slice, patch: Partial<{
    account_id: string; allocation_kind: AllocationKind; allocation_value: number;
  }>) {
    await updateSlice(targetId, slice.id, patch);
    onChange();
  }

  async function remove(slice: Slice) {
    await deleteSlice(targetId, slice.id);
    onChange();
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-mm-text">Slices d'allocation</span>
        <button
          onClick={add}
          disabled={pending}
          className="px-3 py-1 text-xs border border-mm-border text-mm-text-muted hover:text-mm-text-secondary rounded-[6px] transition-colors disabled:opacity-50"
        >
          {pending ? '...' : '+ Ajouter'}
        </button>
      </div>
      {slices.length === 0 && (
        <p className="text-sm text-mm-text-muted">Aucune slice. Ajoute au moins un compte source.</p>
      )}
      {slices.map((s) => (
        <div key={s.id} className="flex gap-2 items-end">
          <div className="flex-1 flex flex-col gap-1">
            <label className="text-xs text-mm-text-muted">Compte</label>
            <select
              value={s.account_id}
              onChange={(e) => update(s, { account_id: e.target.value })}
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
              onChange={(e) => update(s, { allocation_kind: e.target.value as AllocationKind })}
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
              className="bg-mm-surface-elevated border border-mm-border rounded-[8px] px-2 py-1.5 text-sm text-mm-text outline-none focus:border-mm-gold transition-colors"
              defaultValue={s.allocation_value}
              onBlur={(e) => {
                const v = parseFloat(e.target.value);
                if (!Number.isNaN(v) && v !== s.allocation_value) update(s, { allocation_value: v });
              }}
            />
          </div>
          <button
            onClick={() => remove(s)}
            className="px-2 py-1.5 text-sm text-red-400 hover:text-red-300 transition-colors mb-[1px]"
          >
            ×
          </button>
        </div>
      ))}
    </div>
  );
}
