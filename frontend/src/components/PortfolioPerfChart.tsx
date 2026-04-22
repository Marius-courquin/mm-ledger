import { useState } from 'react';
import {
  AreaChart, Area, LineChart, Line, ReferenceLine,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts';
import type { PerfPoint } from '@/api/performance';
import { formatCurrency, formatPercent, formatShortDate } from '@/lib/format';

interface Props {
  series: PerfPoint[];
  totalPct: number;
  valueNow: number;
  currency: string;
  periods: string[];
  activePeriod: string;
  onPeriodChange: (p: string) => void;
  periodLabel: string;
}

type Mode = 'value' | 'perf';

export function PortfolioPerfChart({
  series, totalPct, valueNow, currency, periods, activePeriod, onPeriodChange, periodLabel,
}: Props) {
  const [mode, setMode] = useState<Mode>('value');

  const positive = totalPct >= 0;
  const perfColor = positive ? 'var(--mm-gain)' : 'var(--mm-loss)';
  const bigNumberColor = mode === 'value' ? 'var(--mm-accent-gold)' : perfColor;

  const data = series.map(p => ({
    date: formatShortDate(p.date),
    value: p.value,
    cum_pct: p.cum_pct,
  }));

  return (
    <div className="bg-mm-surface border border-mm-border rounded-[12px] p-5">
      {/* Header : toggle + périodes */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-1">
          <button
            onClick={() => setMode('value')}
            className={['rounded-[4px] px-3 py-1.5 text-xs transition-colors',
              mode === 'value'
                ? 'bg-mm-surface-elevated border border-mm-gold text-mm-gold font-semibold'
                : 'border border-transparent text-mm-text-muted'].join(' ')}
          >Valeur</button>
          <button
            onClick={() => setMode('perf')}
            className={['rounded-[4px] px-3 py-1.5 text-xs transition-colors',
              mode === 'perf'
                ? 'bg-mm-surface-elevated border border-mm-gold text-mm-gold font-semibold'
                : 'border border-transparent text-mm-text-muted'].join(' ')}
          >Perf</button>
        </div>
        <div className="flex items-center gap-1">
          {periods.map((p) => {
            const active = p === activePeriod;
            return (
              <button key={p} onClick={() => onPeriodChange(p)}
                className={['rounded-[4px] px-3 py-1.5 text-xs transition-colors',
                  active
                    ? 'bg-mm-surface-elevated border border-mm-gold text-mm-gold font-semibold'
                    : 'border border-transparent text-mm-text-muted'].join(' ')}>
                {p}
              </button>
            );
          })}
        </div>
      </div>

      {/* Big number */}
      <div className="mb-3">
        <div className="text-[28px] font-semibold" style={{ color: bigNumberColor }}>
          {mode === 'value'
            ? formatCurrency(valueNow, currency)
            : formatPercent(totalPct)}
        </div>
        <div className="text-[11px] text-mm-text-muted mt-0.5">
          {mode === 'value' ? 'Valeur actuelle' : `Rendement sur ${periodLabel}`}
        </div>
      </div>

      {/* Chart */}
      <ResponsiveContainer width="100%" height={240}>
        {mode === 'value' ? (
          <AreaChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
            <defs>
              <linearGradient id="perfGoldGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="var(--mm-accent-gold)" stopOpacity={0.25} />
                <stop offset="100%" stopColor="var(--mm-accent-gold)" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid stroke="#1a3d4d40" horizontal vertical={false} />
            <XAxis dataKey="date" axisLine={false} tickLine={false}
              tick={{ fill: 'rgba(226,207,234,0.5)', fontSize: 10 }} />
            <YAxis axisLine={false} tickLine={false}
              tick={{ fill: 'rgba(226,207,234,0.5)', fontSize: 10 }} />
            <Tooltip contentStyle={{ backgroundColor: '#143a42', border: '1px solid #1a3d4d', borderRadius: 8, color: '#f0ece4', fontSize: 12 }}
              formatter={(v: number) => [formatCurrency(v, currency), 'Valeur']} />
            <Area type="monotone" dataKey="value" stroke="var(--mm-accent-gold)" strokeWidth={2} fill="url(#perfGoldGrad)" />
          </AreaChart>
        ) : (
          <LineChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
            <CartesianGrid stroke="#1a3d4d40" horizontal vertical={false} />
            <XAxis dataKey="date" axisLine={false} tickLine={false}
              tick={{ fill: 'rgba(226,207,234,0.5)', fontSize: 10 }} />
            <YAxis axisLine={false} tickLine={false}
              tick={{ fill: 'rgba(226,207,234,0.5)', fontSize: 10 }}
              tickFormatter={(v) => `${v >= 0 ? '+' : ''}${v.toFixed(1)}%`} />
            <Tooltip contentStyle={{ backgroundColor: '#143a42', border: '1px solid #1a3d4d', borderRadius: 8, color: '#f0ece4', fontSize: 12 }}
              formatter={(v: number) => [`${v >= 0 ? '+' : ''}${v.toFixed(2)}%`, 'Perf']} />
            <ReferenceLine y={0} stroke="rgba(226,207,234,0.35)" strokeDasharray="3 3" />
            <Line type="monotone" dataKey="cum_pct" stroke={perfColor} strokeWidth={2} dot={false} />
          </LineChart>
        )}
      </ResponsiveContainer>
    </div>
  );
}
