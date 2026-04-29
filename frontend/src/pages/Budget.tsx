import { useEffect, useState } from 'react';
import { Plus, Trash2, Lock, Link as LinkIcon } from 'lucide-react';
import { Link } from 'react-router-dom';
import {
  getBudget, createSection, deleteSection,
  createItem, updateItem, deleteItem, applyToProjection,
} from '@/api/budget';
import type { BudgetView, BudgetSection, SectionType } from '@/lib/budget';
import { formatCurrency } from '@/lib/format';

const COLUMNS: { type: SectionType; label: string }[] = [
  { type: 'income', label: 'Revenus' },
  { type: 'fixed_expense', label: 'Charges fixes' },
  { type: 'variable_expense', label: 'Charges variables' },
];

export function Budget() {
  const [data, setData] = useState<BudgetView | null>(null);
  const [loading, setLoading] = useState(true);
  const [applyOpen, setApplyOpen] = useState(false);

  async function load() {
    setLoading(true);
    try { setData(await getBudget()); }
    finally { setLoading(false); }
  }

  useEffect(() => { load(); }, []);

  async function addSection(type: SectionType) {
    const name = prompt('Nom de la section :');
    if (!name?.trim()) return;
    await createSection({ name: name.trim(), section_type: type });
    load();
  }

  if (loading || !data) {
    return <div className="text-sm text-mm-text-muted">Chargement…</div>;
  }

  return (
    <div className="flex flex-col gap-6 pb-24">
      <div className="flex items-center justify-between">
        <h1 className="text-[28px] font-semibold text-mm-text">Budget</h1>
        <button
          onClick={() => setApplyOpen(true)}
          className="px-4 py-2 bg-mm-gold text-mm-bg text-sm font-semibold rounded-[8px] flex items-center gap-1.5 hover:opacity-90"
          disabled={data.totals.investment_capacity <= 0}
          title={data.totals.investment_capacity <= 0 ? 'Capacité d\'investissement nulle ou négative' : ''}
        >
          <LinkIcon size={14} /> Appliquer à la projection
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {COLUMNS.map(({ type, label }) => (
          <div key={type} className="flex flex-col gap-3">
            <div className="flex items-center justify-between">
              <h2 className="text-base font-semibold text-mm-text">{label}</h2>
              <button onClick={() => addSection(type)} className="text-xs text-mm-gold hover:underline">
                + Section
              </button>
            </div>
            {data.sections
              .filter((s) => s.section_type === type)
              .map((s) => (
                <SectionCard key={String(s.id)} section={s} onChange={load} />
              ))}
            {data.sections.filter((s) => s.section_type === type).length === 0 && (
              <div className="text-xs text-mm-text-muted bg-mm-surface border border-mm-border border-dashed rounded-[8px] px-3 py-4 text-center">
                Aucune section. Clique sur "+ Section" pour démarrer.
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Footer sticky avec totaux */}
      <div className="fixed bottom-0 left-0 right-0 bg-mm-surface border-t border-mm-border px-6 py-3 ml-[--sidebar-width,220px]">
        <div className="max-w-7xl mx-auto flex items-center justify-between text-sm">
          <div className="flex gap-6">
            <Total label="Revenus" value={data.totals.income} positive />
            <Total label="Charges" value={data.totals.expense} />
          </div>
          <div className="flex items-center gap-2">
            <span className="text-mm-text-muted text-xs">Capacité d'investissement</span>
            <span className={`text-2xl font-mono font-semibold ${
              data.totals.investment_capacity >= 0 ? 'text-mm-gain' : 'text-mm-loss'
            }`}>
              {formatCurrency(data.totals.investment_capacity, 'EUR')} / mois
            </span>
          </div>
        </div>
      </div>

      <ApplyModal
        isOpen={applyOpen}
        capacity={data.totals.investment_capacity}
        onClose={() => setApplyOpen(false)}
        onApplied={() => { setApplyOpen(false); load(); }}
      />
    </div>
  );
}

function Total({ label, value, positive }: { label: string; value: number; positive?: boolean }) {
  return (
    <div>
      <div className="text-xs text-mm-text-muted">{label}</div>
      <div className={`font-mono ${positive ? 'text-mm-gain' : 'text-mm-text'}`}>
        {formatCurrency(value, 'EUR')}
      </div>
    </div>
  );
}

function SectionCard({ section, onChange }: { section: BudgetSection; onChange: () => void }) {
  const total = section.items.reduce((s, i) => s + i.amount, 0);

  async function handleDeleteSection() {
    if (section.is_virtual) return;
    if (!confirm(`Supprimer la section "${section.name}" ?`)) return;
    await deleteSection(section.id as number);
    onChange();
  }

  async function handleAddItem() {
    if (section.is_virtual) return;
    const label = prompt('Libellé :');
    if (!label?.trim()) return;
    const amountStr = prompt('Montant (€) :');
    const amount = parseFloat(amountStr ?? '');
    if (!Number.isFinite(amount)) return;
    await createItem(section.id as number, { label: label.trim(), amount });
    onChange();
  }

  return (
    <div className="bg-mm-surface border border-mm-border rounded-[12px] flex flex-col">
      <div className="flex items-center justify-between px-3 py-2 border-b border-mm-border">
        <div className="flex items-center gap-2">
          {section.is_virtual && <Lock size={12} className="text-mm-text-muted" />}
          <span className="text-sm font-medium text-mm-text">{section.name}</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs font-mono text-mm-text-muted">{formatCurrency(total, 'EUR')}</span>
          {!section.is_virtual && (
            <>
              <button onClick={handleAddItem} className="text-mm-gold hover:opacity-80">
                <Plus size={14} />
              </button>
              <button onClick={handleDeleteSection} className="text-mm-text-muted hover:text-mm-loss">
                <Trash2 size={12} />
              </button>
            </>
          )}
        </div>
      </div>
      <div className="flex flex-col">
        {section.items.length === 0 && !section.is_virtual && (
          <div className="px-3 py-3 text-xs text-mm-text-muted text-center">Aucun item.</div>
        )}
        {section.is_virtual && section.items.length === 0 && (
          <div className="px-3 py-3 text-xs text-mm-text-muted text-center">Aucun prêt actif.</div>
        )}
        {section.items.map((it) => (
          <ItemRow key={String(it.id)} sectionId={section.id} item={it} virtual={section.is_virtual} onChange={onChange} />
        ))}
        {section.is_virtual && (
          <div className="px-3 py-2 text-[11px] text-mm-text-muted border-t border-mm-border">
            Auto-généré depuis <Link to="/prets" className="text-mm-gold hover:underline">Prêts</Link>.
          </div>
        )}
      </div>
    </div>
  );
}

function ItemRow({ item, virtual, onChange }: {
  sectionId: number | string;
  item: { id: number | string; label: string; amount: number; is_virtual: boolean };
  virtual: boolean;
  onChange: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [label, setLabel] = useState(item.label);
  const [amount, setAmount] = useState(String(item.amount));

  async function save() {
    const a = parseFloat(amount);
    if (!Number.isFinite(a) || !label.trim()) return;
    await updateItem(item.id as number, { label: label.trim(), amount: a });
    setEditing(false);
    onChange();
  }

  async function handleDelete() {
    if (virtual) return;
    if (!confirm(`Supprimer "${item.label}" ?`)) return;
    await deleteItem(item.id as number);
    onChange();
  }

  if (virtual) {
    return (
      <div className="flex items-center justify-between px-3 py-2 text-sm">
        <span className="text-mm-text-muted">{item.label}</span>
        <span className="font-mono text-mm-text">{formatCurrency(item.amount, 'EUR')}</span>
      </div>
    );
  }

  if (editing) {
    return (
      <div className="flex items-center gap-2 px-3 py-2 bg-mm-surface-elevated">
        <input
          className="flex-1 bg-mm-surface border border-mm-border rounded-[6px] px-2 py-1 text-sm text-mm-text focus:outline-none focus:border-mm-gold"
          value={label}
          onChange={(e) => setLabel(e.target.value)}
        />
        <input
          type="number"
          className="w-24 bg-mm-surface border border-mm-border rounded-[6px] px-2 py-1 text-sm text-mm-text font-mono text-right focus:outline-none focus:border-mm-gold"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
        />
        <button onClick={save} className="text-xs text-mm-gold">OK</button>
        <button onClick={() => { setEditing(false); setLabel(item.label); setAmount(String(item.amount)); }} className="text-xs text-mm-text-muted">×</button>
      </div>
    );
  }

  return (
    <div
      className="flex items-center justify-between px-3 py-2 text-sm hover:bg-mm-surface-elevated/50 cursor-pointer group"
      onClick={() => setEditing(true)}
    >
      <span className="text-mm-text">{item.label}</span>
      <div className="flex items-center gap-2">
        <span className="font-mono text-mm-text">{formatCurrency(item.amount, 'EUR')}</span>
        <button
          onClick={(e) => { e.stopPropagation(); handleDelete(); }}
          className="text-mm-text-muted opacity-0 group-hover:opacity-100 hover:text-mm-loss"
        >
          <Trash2 size={12} />
        </button>
      </div>
    </div>
  );
}

function ApplyModal({ isOpen, capacity, onClose, onApplied }: {
  isOpen: boolean; capacity: number; onClose: () => void; onApplied: () => void;
}) {
  const [marketShare, setMarketShare] = useState(1.0);
  const [submitting, setSubmitting] = useState(false);
  if (!isOpen) return null;
  const cashShare = 1 - marketShare;

  async function submit() {
    setSubmitting(true);
    try {
      await applyToProjection(cashShare, marketShare);
      onApplied();
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={onClose}>
      <div
        className="bg-mm-surface border border-mm-border rounded-[12px] p-6 w-full max-w-md mx-4 flex flex-col gap-4"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-lg font-semibold text-mm-text">Appliquer à la projection</h2>
        <p className="text-sm text-mm-text-muted">
          Capacité d'investissement : <span className="font-mono text-mm-text">{formatCurrency(capacity, 'EUR')} / mois</span>
        </p>
        <div className="flex flex-col gap-2">
          <label className="text-xs text-mm-text-muted">Répartition marché / cash</label>
          <input
            type="range" min={0} max={1} step={0.05}
            value={marketShare}
            onChange={(e) => setMarketShare(parseFloat(e.target.value))}
            className="accent-mm-gold"
          />
          <div className="flex justify-between text-xs text-mm-text-muted">
            <span>Cash : <span className="text-mm-text font-mono">{formatCurrency(capacity * cashShare, 'EUR')}</span> ({(cashShare * 100).toFixed(0)} %)</span>
            <span>Marché : <span className="text-mm-text font-mono">{formatCurrency(capacity * marketShare, 'EUR')}</span> ({(marketShare * 100).toFixed(0)} %)</span>
          </div>
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <button onClick={onClose} className="px-4 py-2 text-sm rounded-[8px] border border-mm-border text-mm-text-muted">
            Annuler
          </button>
          <button
            onClick={submit}
            disabled={submitting}
            className="px-4 py-2 bg-mm-gold text-mm-bg text-sm font-semibold rounded-[8px] disabled:opacity-50"
          >
            Appliquer
          </button>
        </div>
      </div>
    </div>
  );
}
