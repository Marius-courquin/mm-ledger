import { useEffect, useMemo, useState } from 'react';
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from 'recharts';
import {
  computeProjection, updateProjectionSettings, setAccountOverride, clearAccountOverride,
} from '@/api/projection';
import type { ProjectionResult, ProjectionCategory } from '@/lib/projection';
import { formatCurrency } from '@/lib/format';

const HORIZON_OPTIONS = [5, 10, 20, 30];

export function Projection() {
  const [data, setData] = useState<ProjectionResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [showOverrides, setShowOverrides] = useState(false);

  async function load() {
    setLoading(true);
    try { setData(await computeProjection()); }
    finally { setLoading(false); }
  }

  useEffect(() => { load(); }, []);

  async function patchSettings(patch: Partial<import('@/lib/projection').ProjectionSettings>) {
    if (!data) return;
    await updateProjectionSettings(patch);
    load();
  }

  async function toggleOverride(account_id: string, currentCategory: ProjectionCategory, isAuto: boolean) {
    if (isAuto) {
      const newCat: ProjectionCategory = currentCategory === 'cash' ? 'market' : 'cash';
      await setAccountOverride(account_id, newCat);
    } else {
      await clearAccountOverride(account_id);
    }
    load();
  }

  const milestones = useMemo(() => {
    if (!data) return [];
    return [60, 120, 240, 360].map((m) => {
      const p = data.points.find((pt) => pt.month_offset === m);
      const years = m / 12;
      return { years, point: p };
    }).filter((x) => !!x.point);
  }, [data]);

  if (loading || !data) {
    return <div className="text-sm text-mm-text-muted">Chargement…</div>;
  }

  const { settings, starting_state, points, classifications } = data;
  const chartData = points.map((p) => ({
    label: `M+${p.month_offset}`,
    year: p.month_offset / 12,
    cash: p.cash,
    market: p.market,
    total: p.total,
  }));

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-[28px] font-semibold text-mm-text">Projection</h1>
        <button
          onClick={() => setShowOverrides((v) => !v)}
          className="px-4 py-2 text-sm rounded-[8px] border border-mm-border text-mm-text-muted hover:text-mm-text"
        >
          Classification des comptes
        </button>
      </div>

      {/* Capital de départ */}
      <div className="grid grid-cols-3 gap-4">
        <Stat label="Cash actuel" value={formatCurrency(starting_state.cash, 'EUR')} />
        <Stat label="Marché actuel" value={formatCurrency(starting_state.market, 'EUR')} />
        <Stat
          label="Mensualités prêts"
          value={`${formatCurrency(starting_state.loan_monthly, 'EUR')} / mois`}
          muted
        />
      </div>

      {/* Hypothèses */}
      <div className="bg-mm-surface border border-mm-border rounded-[12px] p-5 flex flex-col gap-4">
        <span className="text-sm font-medium text-mm-text">Hypothèses</span>
        <div className="grid grid-cols-2 gap-x-6 gap-y-4">
          <Slider
            label="Taux annuel cash"
            value={settings.cash_annual_rate * 100}
            min={0} max={10} step={0.1}
            suffix=" %"
            onChange={(v) => patchSettings({ cash_annual_rate: v / 100 })}
          />
          <Slider
            label="Taux annuel marché"
            value={settings.market_annual_rate * 100}
            min={0} max={15} step={0.1}
            suffix=" %"
            onChange={(v) => patchSettings({ market_annual_rate: v / 100 })}
          />
          <NumberInput
            label="Apport mensuel cash (€)"
            value={settings.cash_monthly_contribution}
            onChange={(v) => patchSettings({ cash_monthly_contribution: v })}
          />
          <NumberInput
            label="Apport mensuel marché (€)"
            value={settings.market_monthly_contribution}
            onChange={(v) => patchSettings({ market_monthly_contribution: v })}
          />
          <div className="col-span-2 flex items-center gap-3">
            <span className="text-xs text-mm-text-muted">Horizon</span>
            <div className="flex gap-1">
              {HORIZON_OPTIONS.map((h) => {
                const active = settings.horizon_years === h;
                return (
                  <button
                    key={h}
                    onClick={() => patchSettings({ horizon_years: h })}
                    className={`px-3 py-1.5 text-xs rounded-[6px] border ${
                      active
                        ? 'border-mm-gold text-mm-gold bg-mm-surface-elevated'
                        : 'border-mm-border text-mm-text-muted'
                    }`}
                  >
                    {h} ans
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      </div>

      {/* Courbe empilée */}
      <div className="bg-mm-surface border border-mm-border rounded-[12px] p-5">
        <div className="text-sm font-medium text-mm-text mb-3">Évolution projetée</div>
        <ResponsiveContainer width="100%" height={320}>
          <AreaChart data={chartData} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
            <defs>
              <linearGradient id="projCash" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="var(--mm-gain)" stopOpacity={0.5} />
                <stop offset="100%" stopColor="var(--mm-gain)" stopOpacity={0.05} />
              </linearGradient>
              <linearGradient id="projMarket" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="var(--mm-accent-gold)" stopOpacity={0.5} />
                <stop offset="100%" stopColor="var(--mm-accent-gold)" stopOpacity={0.05} />
              </linearGradient>
            </defs>
            <CartesianGrid stroke="#1a3d4d40" horizontal vertical={false} />
            <XAxis
              dataKey="year"
              tickFormatter={(y) => `${y.toFixed(0)} an${y >= 2 ? 's' : ''}`}
              axisLine={false} tickLine={false}
              tick={{ fill: 'rgba(226,207,234,0.5)', fontSize: 10 }}
            />
            <YAxis
              axisLine={false} tickLine={false}
              tick={{ fill: 'rgba(226,207,234,0.5)', fontSize: 10 }}
              tickFormatter={(v) => `${(v / 1000).toFixed(0)} k€`}
            />
            <Tooltip
              contentStyle={{ backgroundColor: '#143a42', border: '1px solid #1a3d4d', borderRadius: 8, color: '#f0ece4', fontSize: 12 }}
              formatter={(v: number, name: string) => [formatCurrency(v, 'EUR'), name === 'cash' ? 'Cash' : 'Marché']}
              labelFormatter={(y: number) => `Dans ${y.toFixed(1)} ans`}
            />
            <Legend wrapperStyle={{ fontSize: 11, color: '#e2cfea' }} />
            <Area type="monotone" dataKey="cash" stackId="1" name="Cash" stroke="var(--mm-gain)" fill="url(#projCash)" />
            <Area type="monotone" dataKey="market" stackId="1" name="Marché" stroke="var(--mm-accent-gold)" fill="url(#projMarket)" />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      {/* Cards "à X ans" */}
      <div className="grid grid-cols-4 gap-4">
        {milestones.map(({ years, point }) => (
          <div key={years} className="bg-mm-surface border border-mm-border rounded-[12px] p-4">
            <div className="text-xs text-mm-text-muted">À {years} ans</div>
            <div className="text-xl font-mono text-mm-text mt-1">
              {formatCurrency(point!.total, 'EUR')}
            </div>
            <div className="text-[11px] text-mm-text-muted mt-1">
              cash {formatCurrency(point!.cash, 'EUR')} · marché {formatCurrency(point!.market, 'EUR')}
            </div>
          </div>
        ))}
      </div>

      {showOverrides && (
        <div className="bg-mm-surface border border-mm-border rounded-[12px] p-5">
          <div className="text-sm font-medium text-mm-text mb-3">Classification des comptes</div>
          <p className="text-xs text-mm-text-muted mb-3">
            Auto = déduit du type de connecteur (banque → cash, courtier → marché). Clique pour basculer en override manuel.
          </p>
          <div className="grid grid-cols-2 gap-2">
            {classifications.map((c) => (
              <button
                key={c.account_id}
                onClick={() => toggleOverride(c.account_id, c.category, c.auto)}
                className="flex items-center justify-between px-3 py-2 bg-mm-surface-elevated rounded-[8px] hover:bg-mm-surface-elevated/70 text-left"
              >
                <span className="text-sm text-mm-text font-mono">{c.account_id}</span>
                <span className={`text-xs px-2 py-0.5 rounded-full ${
                  c.category === 'cash' ? 'bg-mm-gain/15 text-mm-gain' : 'bg-mm-gold/15 text-mm-gold'
                }`}>
                  {c.category} {c.auto ? '(auto)' : '(override)'}
                </span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function Stat({ label, value, muted }: { label: string; value: string; muted?: boolean }) {
  return (
    <div className="bg-mm-surface border border-mm-border rounded-[12px] px-5 py-4">
      <div className="text-xs text-mm-text-muted">{label}</div>
      <div className={`mt-1 font-mono ${muted ? 'text-lg text-mm-text-muted' : 'text-2xl text-mm-text'}`}>
        {value}
      </div>
    </div>
  );
}

function Slider({ label, value, min, max, step, suffix, onChange }: {
  label: string; value: number; min: number; max: number; step: number; suffix: string;
  onChange: (v: number) => void;
}) {
  const [local, setLocal] = useState(value);
  useEffect(() => { setLocal(value); }, [value]);
  return (
    <label className="flex flex-col gap-1.5">
      <div className="flex justify-between text-xs">
        <span className="text-mm-text-muted">{label}</span>
        <span className="text-mm-text font-mono">{local.toFixed(step < 1 ? 1 : 0)}{suffix}</span>
      </div>
      <input
        type="range"
        min={min} max={max} step={step} value={local}
        onChange={(e) => setLocal(parseFloat(e.target.value))}
        onMouseUp={(e) => onChange(parseFloat((e.target as HTMLInputElement).value))}
        onTouchEnd={(e) => onChange(parseFloat((e.target as HTMLInputElement).value))}
        className="accent-mm-gold"
      />
    </label>
  );
}

function NumberInput({ label, value, onChange }: {
  label: string; value: number; onChange: (v: number) => void;
}) {
  const [local, setLocal] = useState(String(value));
  useEffect(() => { setLocal(String(value)); }, [value]);
  return (
    <label className="flex flex-col gap-1">
      <span className="text-xs text-mm-text-muted">{label}</span>
      <input
        type="number" min={0}
        value={local}
        onChange={(e) => setLocal(e.target.value)}
        onBlur={() => {
          const v = parseFloat(local);
          if (!Number.isNaN(v) && v >= 0 && v !== value) onChange(v);
        }}
        className="px-3 py-2 bg-mm-surface-elevated border border-mm-border rounded-[8px] text-sm text-mm-text focus:outline-none focus:border-mm-gold"
      />
    </label>
  );
}
