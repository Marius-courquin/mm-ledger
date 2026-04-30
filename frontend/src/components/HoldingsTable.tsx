import type { Position } from '@/lib/types';
import { formatCurrency, formatPercent } from '@/lib/format';

interface HoldingsTableProps {
  positions: Position[];
  totalValue: number;
}

export function HoldingsTable({ positions, totalValue }: HoldingsTableProps) {
  return (
    <div className="bg-mm-surface border border-mm-border rounded-[12px] overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-4">
        <h3 className="text-base font-semibold text-mm-text">Holdings Breakdown</h3>
        <span className="text-xs text-mm-text-muted">{positions.length} assets</span>
      </div>

      {/* Table */}
      <table className="w-full">
        <thead>
          <tr className="border-t border-mm-border">
            <th className="px-5 py-2.5 text-left text-[11px] font-semibold uppercase tracking-wide text-mm-text-muted">
              Asset Name
            </th>
            <th className="w-[70px] px-3 py-2.5 text-left text-[11px] font-semibold uppercase tracking-wide text-mm-text-muted">
              Type
            </th>
            <th className="w-[80px] px-3 py-2.5 text-right text-[11px] font-semibold uppercase tracking-wide text-mm-text-muted">
              Quantity
            </th>
            <th className="w-[110px] px-3 py-2.5 text-right text-[11px] font-semibold uppercase tracking-wide text-mm-text-muted">
              Current Value
            </th>
            <th className="w-[70px] px-3 py-2.5 text-right text-[11px] font-semibold uppercase tracking-wide text-mm-text-muted">
              Weight %
            </th>
            <th className="w-[90px] px-3 py-2.5 text-right text-[11px] font-semibold uppercase tracking-wide text-mm-text-muted">
              Performance
            </th>
          </tr>
        </thead>
        <tbody>
          {positions.map((pos) => {
            const value = pos.value ?? 0;
            const pnlPct = pos.pnl_pct ?? 0;
            const weight = totalValue > 0 ? (value / totalValue) * 100 : 0;
            return (
              <tr key={`${pos.account_id}-${pos.instrument}`} className="border-t border-mm-border">
                <td className="px-5 py-3">
                  <span className="text-[13px] font-medium text-mm-text">{pos.name}</span>
                </td>
                <td className="w-[70px] px-3 py-3">
                  <span className="text-xs text-mm-lavender">{pos.category}</span>
                </td>
                <td className="w-[80px] px-3 py-3 text-right">
                  <span className="text-[13px] text-mm-text-secondary tabular-nums">
                    {pos.quantity.toLocaleString('fr-FR', { maximumFractionDigits: 4 })}
                  </span>
                </td>
                <td className="w-[110px] px-3 py-3 text-right">
                  <span className="text-[13px] font-medium text-mm-text tabular-nums">
                    {formatCurrency(value, pos.currency)}
                  </span>
                </td>
                <td className="w-[70px] px-3 py-3 text-right">
                  <span className="text-[13px] text-mm-text-secondary tabular-nums">
                    {weight.toFixed(1)}%
                  </span>
                </td>
                <td className="w-[90px] px-3 py-3 text-right">
                  <span
                    className={`text-[13px] font-medium tabular-nums ${
                      pnlPct >= 0 ? 'text-mm-gold' : 'text-mm-loss'
                    }`}
                  >
                    {formatPercent(pnlPct)}
                  </span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
