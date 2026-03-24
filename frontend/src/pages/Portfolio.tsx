import { useState, useEffect, useMemo } from 'react';
import { ChevronDown, ChevronRight, Wallet, TrendingUp, Bitcoin, Landmark, Briefcase } from 'lucide-react';
import { getPortfolio } from '@/api/portfolio';
import { formatCurrency } from '@/lib/format';
import type { Portfolio as PortfolioData, PortfolioAccount, PortfolioCategory, Position } from '@/lib/types';

// ── Label maps ──────────────────────────────────────────────────────────────

const ACCOUNT_LABELS: Record<string, string> = {
  DEFAULT: 'Compte-Titres Ordinaire',
  TAX_WRAPPER: 'Plan Epargne Actions',
  PEA: 'Plan Epargne Actions',
  CRYPTOS: 'Actifs numériques',
  PRIVATEMARKETS: 'Investissements privés',
};

const ACCOUNT_SHORT: Record<string, string> = {
  DEFAULT: 'CTO',
  TAX_WRAPPER: 'PEA',
  PEA: 'PEA',
  CRYPTOS: 'Crypto',
  PRIVATEMARKETS: 'Private Equity',
};

const CATEGORY_LABELS: Record<string, string> = {
  stocksAndETFs: 'Actions & ETFs',
  cryptos: 'Crypto',
  privateMarkets: 'Private Equity',
  bonds: 'Obligations',
};

const ACCOUNT_ICONS: Record<string, typeof Wallet> = {
  DEFAULT: TrendingUp,
  TAX_WRAPPER: Landmark,
  PEA: Landmark,
  CRYPTOS: Bitcoin,
  PRIVATEMARKETS: Briefcase,
};

const ACCOUNT_COLORS: Record<string, string> = {
  DEFAULT: 'from-blue-500/10 to-transparent border-blue-500/20',
  TAX_WRAPPER: 'from-emerald-500/10 to-transparent border-emerald-500/20',
  PEA: 'from-emerald-500/10 to-transparent border-emerald-500/20',
  CRYPTOS: 'from-orange-500/10 to-transparent border-orange-500/20',
  PRIVATEMARKETS: 'from-purple-500/10 to-transparent border-purple-500/20',
};

const ACCOUNT_ICON_COLORS: Record<string, string> = {
  DEFAULT: 'text-blue-400',
  TAX_WRAPPER: 'text-emerald-400',
  PEA: 'text-emerald-400',
  CRYPTOS: 'text-orange-400',
  PRIVATEMARKETS: 'text-purple-400',
};

// ── Position row ─────────────────────────────────────────────────────────────

function PositionRow({ pos, totalValue, currency }: { pos: Position; totalValue: number; currency: string }) {
  const weight = totalValue > 0 ? (pos.value / totalValue) * 100 : 0;
  const hasPrice = pos.current_price > 0;

  return (
    <tr className="border-t border-mm-border/50 hover:bg-white/[0.02] transition-colors">
      <td className="px-5 py-2.5">
        <span className="text-[13px] text-mm-text">{pos.name}</span>
      </td>
      <td className="px-3 py-2.5 text-right">
        <span className="text-[13px] text-mm-text-secondary tabular-nums">
          {pos.quantity.toLocaleString('fr-FR', { maximumFractionDigits: 4 })}
        </span>
      </td>
      <td className="px-3 py-2.5 text-right">
        <span className="text-[13px] text-mm-text-muted tabular-nums">
          {formatCurrency(pos.avg_price, currency)}
        </span>
      </td>
      <td className="px-3 py-2.5 text-right">
        <span className={`text-[13px] tabular-nums ${hasPrice ? 'text-mm-text' : 'text-mm-text-muted'}`}>
          {hasPrice ? formatCurrency(pos.current_price, currency) : '—'}
        </span>
      </td>
      <td className="px-3 py-2.5 text-right">
        <span className={`text-[13px] font-medium tabular-nums ${hasPrice ? 'text-mm-text' : 'text-mm-text-muted'}`}>
          {hasPrice ? formatCurrency(pos.value, currency) : '—'}
        </span>
      </td>
      <td className="px-3 py-2.5 text-right">
        <span className="text-[12px] text-mm-text-muted tabular-nums">
          {hasPrice ? `${weight.toFixed(1)}%` : '—'}
        </span>
      </td>
      <td className="px-3 py-2.5 text-right">
        {hasPrice ? (
          <span className={`text-[13px] tabular-nums ${pos.pnl >= 0 ? 'text-mm-gain' : 'text-red-400'}`}>
            {pos.pnl >= 0 ? '+' : ''}{formatCurrency(pos.pnl, currency)}
          </span>
        ) : (
          <span className="text-[13px] text-mm-text-muted">—</span>
        )}
      </td>
      <td className="px-3 py-2.5 text-right">
        {hasPrice ? (
          <span className={`text-[13px] font-medium tabular-nums ${pos.pnl_pct >= 0 ? 'text-mm-gain' : 'text-red-400'}`}>
            {pos.pnl_pct >= 0 ? '+' : ''}{pos.pnl_pct.toFixed(2)}%
          </span>
        ) : (
          <span className="text-[13px] text-mm-text-muted">—</span>
        )}
      </td>
    </tr>
  );
}

// ── Category section ─────────────────────────────────────────────────────────

function CategorySection({ category, currency, accountValue }: {
  category: PortfolioCategory;
  currency: string;
  accountValue: number;
}) {
  const [open, setOpen] = useState(true);
  const label = CATEGORY_LABELS[category.categoryType] ?? category.categoryType;
  const hasValue = category.total_value > 0;
  const positionsWithPrice = category.positions.filter(p => p.current_price > 0);
  const positionsNoPrice = category.positions.filter(p => p.current_price <= 0);

  return (
    <div>
      <button
        onClick={() => setOpen(v => !v)}
        className="w-full flex items-center gap-3 px-5 py-2.5 hover:bg-white/[0.02] transition-colors"
      >
        {open
          ? <ChevronDown size={12} className="text-mm-text-muted" />
          : <ChevronRight size={12} className="text-mm-text-muted" />
        }
        <span className="text-[13px] font-medium text-mm-text-secondary flex-1 text-left">
          {label}
        </span>
        <span className="text-[12px] text-mm-text-muted tabular-nums">
          {category.positions.length} position{category.positions.length > 1 ? 's' : ''}
        </span>
        {hasValue && (
          <>
            <span className="text-[13px] font-medium text-mm-text tabular-nums ml-4">
              {formatCurrency(category.total_value, currency)}
            </span>
            <span className={`text-[12px] font-medium tabular-nums ml-2 ${
              category.pnl_pct >= 0 ? 'text-mm-gain' : 'text-red-400'
            }`}>
              {category.pnl_pct >= 0 ? '+' : ''}{category.pnl_pct.toFixed(2)}%
            </span>
          </>
        )}
      </button>

      {open && (
        <table className="w-full">
          <thead>
            <tr className="bg-white/[0.01]">
              {['Name', 'Qty', 'Avg Price', 'Price', 'Value', 'Weight', 'P&L', 'P&L %'].map((h) => (
                <th key={h} className={`px-${h === 'Name' ? '5' : '3'} py-1.5 text-[10px] font-medium uppercase tracking-wider text-mm-text-muted ${h === 'Name' ? 'text-left' : 'text-right'}`}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {positionsWithPrice.map(pos => (
              <PositionRow key={`${pos.account_id}-${pos.instrument}`} pos={pos} totalValue={accountValue} currency={currency} />
            ))}
            {positionsNoPrice.map(pos => (
              <PositionRow key={`${pos.account_id}-${pos.instrument}`} pos={pos} totalValue={accountValue} currency={currency} />
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

// ── Account card ─────────────────────────────────────────────────────────────

function AccountCard({ account, currency }: { account: PortfolioAccount; currency: string }) {
  const shortLabel = ACCOUNT_SHORT[account.productType] ?? account.label;
  const longLabel = ACCOUNT_LABELS[account.productType] ?? account.label;
  const Icon = ACCOUNT_ICONS[account.productType] ?? Briefcase;
  const gradientClass = ACCOUNT_COLORS[account.productType] ?? 'from-purple-500/10 to-transparent border-purple-500/20';
  const iconColor = ACCOUNT_ICON_COLORS[account.productType] ?? 'text-purple-400';

  const posCount = account.categories.reduce((s, c) => s + c.positions.length, 0);

  return (
    <div className="bg-mm-surface border border-mm-border rounded-[14px] overflow-hidden">
      {/* Account header with gradient */}
      <div className={`bg-gradient-to-r ${gradientClass} border-b border-mm-border px-5 py-4`}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className={`h-9 w-9 rounded-[10px] bg-mm-surface-elevated flex items-center justify-center ${iconColor}`}>
              <Icon size={18} />
            </div>
            <div className="flex flex-col">
              <div className="flex items-center gap-2">
                <h2 className="text-lg font-semibold text-mm-text">{shortLabel}</h2>
                <span className="text-[12px] text-mm-text-muted">{longLabel}</span>
              </div>
              <span className="text-[11px] text-mm-text-muted">
                {posCount} position{posCount > 1 ? 's' : ''}
              </span>
            </div>
          </div>
          <div className="flex flex-col items-end gap-0.5">
            <span className="text-[24px] font-bold text-mm-gold tabular-nums">
              {account.total_invested > 0 ? formatCurrency(account.positions_value > 0 ? account.total_value : account.total_invested, currency) : formatCurrency(account.total_value, currency)}
            </span>
            <div className="flex items-center gap-3 text-[12px]">
              {account.cash > 0 && (
                <span className="text-mm-text-muted">
                  Cash <span className="text-mm-text-secondary tabular-nums">{formatCurrency(account.cash, currency)}</span>
                </span>
              )}
              {account.total_invested > 0 && (
                <span className="text-mm-text-muted">
                  Investi <span className="text-mm-text-secondary tabular-nums">{formatCurrency(account.total_invested, currency)}</span>
                </span>
              )}
              {account.positions_value > 0 && (
                <span className={`font-medium tabular-nums ${account.pnl >= 0 ? 'text-mm-gain' : 'text-red-400'}`}>
                  {account.pnl >= 0 ? '+' : ''}{formatCurrency(account.pnl, currency)} ({account.pnl_pct >= 0 ? '+' : ''}{account.pnl_pct.toFixed(2)}%)
                </span>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Categories */}
      <div className="divide-y divide-mm-border/50">
        {account.categories.map(cat => (
          <CategorySection
            key={cat.categoryType}
            category={cat}
            currency={currency}
            accountValue={account.total_value}
          />
        ))}
      </div>
    </div>
  );
}

// ── Portfolio page ───────────────────────────────────────────────────────────

export function Portfolio() {
  const [portfolio, setPortfolio] = useState<PortfolioData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    async function fetchData() {
      setLoading(true);
      try {
        const data = await getPortfolio();
        if (!cancelled) setPortfolio(data);
      } catch (err: unknown) {
        if (!cancelled) setError((err as { detail?: string }).detail ?? 'Failed to load portfolio');
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    fetchData();
    return () => { cancelled = true; };
  }, []);

  const totalPositions = useMemo(() => {
    if (!portfolio) return 0;
    return portfolio.accounts.reduce((s, a) => s + a.categories.reduce((s2, c) => s2 + c.positions.length, 0), 0);
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
    <div className="flex flex-col gap-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-mm-text">Portfolio</h1>
          <p className="text-[13px] text-mm-text-muted mt-0.5">
            {portfolio.accounts.length} compte{portfolio.accounts.length > 1 ? 's' : ''} &middot; {totalPositions} position{totalPositions > 1 ? 's' : ''}
          </p>
        </div>
        <div className="text-right">
          <span className="text-[28px] font-bold text-mm-gold tabular-nums">
            {formatCurrency(portfolio.total_value, currency)}
          </span>
          <div className="flex items-center justify-end gap-3 mt-0.5">
            <span className="text-[12px] text-mm-text-muted">
              Investi <span className="text-mm-text-secondary tabular-nums">{formatCurrency(portfolio.total_invested, currency)}</span>
            </span>
            <span className={`text-[13px] font-medium tabular-nums ${portfolio.total_pnl >= 0 ? 'text-mm-gain' : 'text-red-400'}`}>
              {portfolio.total_pnl >= 0 ? '+' : ''}{formatCurrency(portfolio.total_pnl, currency)} ({portfolio.total_pnl_pct >= 0 ? '+' : ''}{portfolio.total_pnl_pct.toFixed(2)}%)
            </span>
          </div>
        </div>
      </div>

      {/* Account cards */}
      {portfolio.accounts.map(account => (
        <AccountCard key={account.secAccNo} account={account} currency={currency} />
      ))}
    </div>
  );
}
