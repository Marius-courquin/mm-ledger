import { useState, useEffect, useMemo } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';
import { getPortfolio } from '@/api/portfolio';
import { formatCurrency, formatPercent } from '@/lib/format';
import type { Portfolio as PortfolioData, PortfolioAccount, PortfolioCategory, Position } from '@/lib/types';

// ── Category section (collapsible) ───────────────────────────────────────────

interface CategorySectionProps {
  category: PortfolioCategory;
  currency: string;
  accountValue: number;
}

function CategorySection({ category, currency, accountValue }: CategorySectionProps) {
  const [open, setOpen] = useState(true);

  return (
    <div className="border-t border-mm-border">
      {/* Category header */}
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-2 px-5 py-3 hover:bg-mm-surface-elevated transition-colors text-left"
      >
        {open ? (
          <ChevronDown size={14} className="text-mm-text-muted shrink-0" />
        ) : (
          <ChevronRight size={14} className="text-mm-text-muted shrink-0" />
        )}
        <span className="flex-1 text-[13px] font-semibold text-mm-lavender uppercase tracking-wide">
          {category.categoryType}
        </span>
        <span className="text-[12px] text-mm-text-muted tabular-nums">
          {formatCurrency(category.total_value, currency)}
        </span>
        <span
          className={`text-[12px] font-medium tabular-nums ml-3 ${
            category.pnl_pct >= 0 ? 'text-mm-gain' : 'text-mm-loss'
          }`}
        >
          {formatPercent(category.pnl_pct)}
        </span>
      </button>

      {/* Positions table */}
      {open && (
        <table className="w-full">
          <thead>
            <tr className="border-t border-mm-border bg-mm-surface-elevated/50">
              <th className="px-5 py-2 text-left text-[11px] font-semibold uppercase tracking-wide text-mm-text-muted">
                Name
              </th>
              <th className="w-[90px] px-3 py-2 text-right text-[11px] font-semibold uppercase tracking-wide text-mm-text-muted">
                Quantity
              </th>
              <th className="w-[100px] px-3 py-2 text-right text-[11px] font-semibold uppercase tracking-wide text-mm-text-muted">
                Avg Price
              </th>
              <th className="w-[100px] px-3 py-2 text-right text-[11px] font-semibold uppercase tracking-wide text-mm-text-muted">
                Price
              </th>
              <th className="w-[100px] px-3 py-2 text-right text-[11px] font-semibold uppercase tracking-wide text-mm-text-muted">
                Value
              </th>
              <th className="w-[80px] px-3 py-2 text-right text-[11px] font-semibold uppercase tracking-wide text-mm-text-muted">
                Weight
              </th>
              <th className="w-[90px] px-3 py-2 text-right text-[11px] font-semibold uppercase tracking-wide text-mm-text-muted">
                P&amp;L
              </th>
              <th className="w-[80px] px-3 py-2 text-right text-[11px] font-semibold uppercase tracking-wide text-mm-text-muted">
                P&amp;L %
              </th>
            </tr>
          </thead>
          <tbody>
            {category.positions.map((pos: Position) => {
              const weight = accountValue > 0 ? (pos.value / accountValue) * 100 : 0;
              return (
                <tr
                  key={`${pos.account_id}-${pos.instrument}`}
                  className="border-t border-mm-border hover:bg-mm-surface-elevated/30 transition-colors"
                >
                  <td className="px-5 py-3">
                    <span className="text-[13px] font-medium text-mm-text">{pos.name}</span>
                    {pos.symbol && (
                      <span className="ml-2 text-[11px] text-mm-text-muted">{pos.symbol}</span>
                    )}
                  </td>
                  <td className="w-[90px] px-3 py-3 text-right">
                    <span className="text-[13px] text-mm-text-secondary tabular-nums">
                      {pos.quantity.toLocaleString('fr-FR', { maximumFractionDigits: 6 })}
                    </span>
                  </td>
                  <td className="w-[100px] px-3 py-3 text-right">
                    <span className="text-[13px] text-mm-text-secondary tabular-nums">
                      {formatCurrency(pos.avg_price, pos.currency)}
                    </span>
                  </td>
                  <td className="w-[100px] px-3 py-3 text-right">
                    <span className="text-[13px] font-medium text-mm-text tabular-nums">
                      {formatCurrency(pos.current_price, pos.currency)}
                    </span>
                  </td>
                  <td className="w-[100px] px-3 py-3 text-right">
                    <span className="text-[13px] font-semibold text-mm-text tabular-nums">
                      {formatCurrency(pos.value, pos.currency)}
                    </span>
                  </td>
                  <td className="w-[80px] px-3 py-3 text-right">
                    <span className="text-[13px] text-mm-text-secondary tabular-nums">
                      {weight.toFixed(1)}%
                    </span>
                  </td>
                  <td className="w-[90px] px-3 py-3 text-right">
                    <span
                      className={`text-[13px] tabular-nums ${
                        pos.pnl >= 0 ? 'text-mm-gain' : 'text-mm-loss'
                      }`}
                    >
                      {formatCurrency(pos.pnl, pos.currency)}
                    </span>
                  </td>
                  <td className="w-[80px] px-3 py-3 text-right">
                    <span
                      className={`text-[13px] font-medium tabular-nums ${
                        pos.pnl_pct >= 0 ? 'text-mm-gain' : 'text-mm-loss'
                      }`}
                    >
                      {formatPercent(pos.pnl_pct)}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}

// ── Account card ──────────────────────────────────────────────────────────────

interface AccountCardProps {
  account: PortfolioAccount;
  currency: string;
}

function AccountCard({ account, currency }: AccountCardProps) {
  return (
    <div className="bg-mm-surface border border-mm-border rounded-[12px] overflow-hidden">
      {/* Account header */}
      <div className="px-5 py-4 flex items-start justify-between">
        <div className="flex flex-col gap-0.5">
          <div className="flex items-center gap-2">
            <h2 className="text-base font-semibold text-mm-text">{account.label}</h2>
            <span className="text-[11px] px-2 py-0.5 rounded-full bg-mm-surface-elevated text-mm-text-muted border border-mm-border">
              {account.productType}
            </span>
          </div>
          <span className="text-[12px] text-mm-text-muted">{account.secAccNo}</span>
        </div>
        <div className="flex items-end flex-col gap-1">
          <span className="text-[22px] font-bold text-mm-gold tabular-nums">
            {formatCurrency(account.total_value, currency)}
          </span>
          <div className="flex gap-4 text-[12px] text-mm-text-muted">
            <span>
              Cash:{' '}
              <span className="text-mm-text-secondary tabular-nums">
                {formatCurrency(account.cash, currency)}
              </span>
            </span>
            <span>
              Positions:{' '}
              <span className="text-mm-text-secondary tabular-nums">
                {formatCurrency(account.positions_value, currency)}
              </span>
            </span>
            <span>
              P&amp;L:{' '}
              <span
                className={`font-medium tabular-nums ${
                  account.pnl >= 0 ? 'text-mm-gain' : 'text-mm-loss'
                }`}
              >
                {formatCurrency(account.pnl, currency)} ({formatPercent(account.pnl_pct)})
              </span>
            </span>
          </div>
        </div>
      </div>

      {/* Categories */}
      {account.categories.map((cat) => (
        <CategorySection
          key={cat.categoryType}
          category={cat}
          currency={currency}
          accountValue={account.total_value}
        />
      ))}
    </div>
  );
}

// ── Portfolio page ────────────────────────────────────────────────────────────

export function Portfolio() {
  const [portfolio, setPortfolio] = useState<PortfolioData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;

    async function fetchData() {
      setLoading(true);
      setError('');
      try {
        const data = await getPortfolio();
        if (!cancelled) setPortfolio(data);
      } catch (err: unknown) {
        if (!cancelled) {
          const detail = (err as { detail?: string }).detail ?? 'Failed to load portfolio';
          setError(detail);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    fetchData();
    return () => { cancelled = true; };
  }, []);

  const totalPositionsCount = useMemo(() => {
    if (!portfolio) return 0;
    return portfolio.accounts.reduce(
      (sum, acc) => sum + acc.categories.reduce((s, cat) => s + cat.positions.length, 0),
      0
    );
  }, [portfolio]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-mm-gold border-t-transparent" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-64">
        <p className="text-sm text-red-400">{error}</p>
      </div>
    );
  }

  if (!portfolio) return null;

  const currency = portfolio.currency ?? 'EUR';

  return (
    <div className="flex flex-col gap-8">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div className="flex flex-col gap-1">
          <h1 className="text-2xl font-semibold text-mm-text">Portfolio Composition</h1>
          <p className="text-[13px] text-mm-text-muted">
            {portfolio.accounts.length} account{portfolio.accounts.length !== 1 ? 's' : ''} &middot;{' '}
            {totalPositionsCount} position{totalPositionsCount !== 1 ? 's' : ''}
          </p>
        </div>
        <div className="flex flex-col items-end gap-1">
          <span className="text-[28px] font-bold text-mm-gold tabular-nums">
            {formatCurrency(portfolio.total_value, currency)}
          </span>
          <span className="text-xs text-mm-text-muted">Total Portfolio Value</span>
        </div>
      </div>

      {/* Summary strip */}
      <div className="grid grid-cols-4 gap-3">
        <div className="bg-mm-surface border border-mm-border rounded-[12px] p-4 flex flex-col gap-1">
          <span className="text-[11px] uppercase tracking-wide text-mm-text-muted">Total Value</span>
          <span className="text-[22px] font-bold text-mm-gold tabular-nums">
            {formatCurrency(portfolio.total_value, currency)}
          </span>
        </div>
        <div className="bg-mm-surface border border-mm-border rounded-[12px] p-4 flex flex-col gap-1">
          <span className="text-[11px] uppercase tracking-wide text-mm-text-muted">Cash</span>
          <span className="text-[22px] font-bold text-mm-text tabular-nums">
            {formatCurrency(portfolio.total_cash, currency)}
          </span>
        </div>
        <div className="bg-mm-surface border border-mm-border rounded-[12px] p-4 flex flex-col gap-1">
          <span className="text-[11px] uppercase tracking-wide text-mm-text-muted">Invested</span>
          <span className="text-[22px] font-bold text-mm-text tabular-nums">
            {formatCurrency(portfolio.total_invested, currency)}
          </span>
        </div>
        <div className="bg-mm-surface border border-mm-border rounded-[12px] p-4 flex flex-col gap-1">
          <span className="text-[11px] uppercase tracking-wide text-mm-text-muted">Total P&amp;L</span>
          <span
            className={`text-[22px] font-bold tabular-nums ${
              portfolio.total_pnl >= 0 ? 'text-mm-gain' : 'text-mm-loss'
            }`}
          >
            {formatCurrency(portfolio.total_pnl, currency)}
          </span>
          <span
            className={`text-[12px] font-medium tabular-nums ${
              portfolio.total_pnl_pct >= 0 ? 'text-mm-gain' : 'text-mm-loss'
            }`}
          >
            {formatPercent(portfolio.total_pnl_pct)}
          </span>
        </div>
      </div>

      {/* Account cards */}
      {portfolio.accounts.map((account) => (
        <AccountCard key={account.secAccNo} account={account} currency={currency} />
      ))}
    </div>
  );
}
