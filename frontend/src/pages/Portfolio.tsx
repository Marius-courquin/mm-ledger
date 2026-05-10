import { useState, useEffect, useMemo } from 'react';
import { ChevronDown, ChevronRight, Wallet, TrendingUp, Bitcoin, Landmark, Briefcase } from 'lucide-react';
import { getPortfolio } from '@/api/portfolio';
import { useApp } from '@/context/AppContext';
import { formatCurrency } from '@/lib/format';
import type { Portfolio as PortfolioData, PortfolioAccount, Position } from '@/lib/types';

// ── Label maps (keyed by tax_wrapper) ───────────────────────────────────────

const ACCOUNT_LABELS: Record<string, string> = {
  cto:          'Compte-Titres Ordinaire',
  pea:          'Plan Épargne Actions',
  pea_pme:      'PEA-PME',
  per:          'Plan Épargne Retraite',
  av:           'Assurance Vie',
  livret_a:     'Livret A',
  livret_jeune: 'Livret Jeune',
  ldds:         'LDDS',
  lep:          'LEP',
  cel:          'CEL',
  pel:          'PEL',
  // fallbacks for kind-based resolution
  securities:   'Titres',
  cash:         'Espèces',
  liability:    'Passif',
};

const ACCOUNT_SHORT: Record<string, string> = {
  cto:          'CTO',
  pea:          'PEA',
  pea_pme:      'PEA-PME',
  per:          'PER',
  av:           'AV',
  livret_a:     'Livret A',
  livret_jeune: 'Livret Jeune',
  ldds:         'LDDS',
  lep:          'LEP',
  cel:          'CEL',
  pel:          'PEL',
  securities:   'Titres',
  cash:         'Espèces',
  liability:    'Passif',
};

const CATEGORY_LABELS: Record<string, string> = {
  equity:  'Actions',
  etf:     'ETF',
  bond:    'Obligations',
  crypto:  'Cryptomonnaies',
  private: 'Private Markets',
  other:   'Autres',
};

const ACCOUNT_ICONS: Record<string, typeof Wallet> = {
  cto:          TrendingUp,
  pea:          Landmark,
  pea_pme:      Landmark,
  per:          Briefcase,
  av:           Briefcase,
  livret_a:     Wallet,
  livret_jeune: Wallet,
  ldds:         Wallet,
  lep:          Wallet,
  cel:          Wallet,
  pel:          Wallet,
  crypto:       Bitcoin,
  securities:   TrendingUp,
  cash:         Wallet,
  liability:    Briefcase,
};

const ACCOUNT_COLORS: Record<string, string> = {
  cto:          'from-blue-500/10 to-transparent border-blue-500/20',
  pea:          'from-emerald-500/10 to-transparent border-emerald-500/20',
  pea_pme:      'from-emerald-500/10 to-transparent border-emerald-500/20',
  per:          'from-indigo-500/10 to-transparent border-indigo-500/20',
  av:           'from-teal-500/10 to-transparent border-teal-500/20',
  livret_a:     'from-green-500/10 to-transparent border-green-500/20',
  livret_jeune: 'from-green-500/10 to-transparent border-green-500/20',
  ldds:         'from-green-500/10 to-transparent border-green-500/20',
  lep:          'from-green-500/10 to-transparent border-green-500/20',
  cel:          'from-green-500/10 to-transparent border-green-500/20',
  pel:          'from-green-500/10 to-transparent border-green-500/20',
  crypto:       'from-orange-500/10 to-transparent border-orange-500/20',
  securities:   'from-purple-500/10 to-transparent border-purple-500/20',
  cash:         'from-emerald-500/10 to-transparent border-emerald-500/20',
  liability:    'from-rose-500/10 to-transparent border-rose-500/20',
};

const ACCOUNT_ICON_COLORS: Record<string, string> = {
  cto:          'text-blue-400',
  pea:          'text-emerald-400',
  pea_pme:      'text-emerald-400',
  per:          'text-indigo-400',
  av:           'text-teal-400',
  livret_a:     'text-green-400',
  livret_jeune: 'text-green-400',
  ldds:         'text-green-400',
  lep:          'text-green-400',
  cel:          'text-green-400',
  pel:          'text-green-400',
  crypto:       'text-orange-400',
  securities:   'text-purple-400',
  cash:         'text-emerald-400',
  liability:    'text-rose-400',
};

// Resolve display key from account (tax_wrapper first, then kind fallback)
function resolveAccountKey(account: PortfolioAccount): string {
  const { tax_wrapper, kind, label } = account;
  if (tax_wrapper !== 'none') return tax_wrapper;
  // For none tax_wrapper, check label for hints (Crypto / Private)
  const lc = label.toLowerCase();
  if (lc.includes('crypto')) return 'crypto';
  if (lc.includes('private') || lc.includes('equity') || lc.includes('privé')) return 'securities';
  return kind; // 'cash' | 'securities' | 'liability'
}

// ── Position row ─────────────────────────────────────────────────────────────

function PositionRow({ pos, totalValue, currency }: { pos: Position; totalValue: number; currency: string }) {
  const value = pos.value ?? 0;
  const weight = totalValue > 0 ? (value / totalValue) * 100 : 0;
  const hasPrice = pos.current_price != null && pos.current_price > 0;
  const pnl = pos.pnl ?? 0;
  const pnlPct = pos.pnl_pct ?? 0;

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
          {pos.avg_price != null ? formatCurrency(pos.avg_price, currency) : '—'}
        </span>
      </td>
      <td className="px-3 py-2.5 text-right">
        <span className={`text-[13px] tabular-nums ${hasPrice ? 'text-mm-text' : 'text-mm-text-muted'}`}>
          {hasPrice ? formatCurrency(pos.current_price!, currency) : '—'}
        </span>
      </td>
      <td className="px-3 py-2.5 text-right">
        <span className={`text-[13px] font-medium tabular-nums ${hasPrice ? 'text-mm-text' : 'text-mm-text-muted'}`}>
          {hasPrice ? formatCurrency(value, currency) : '—'}
        </span>
      </td>
      <td className="px-3 py-2.5 text-right">
        <span className="text-[12px] text-mm-text-muted tabular-nums">
          {hasPrice ? `${weight.toFixed(1)}%` : '—'}
        </span>
      </td>
      <td className="px-3 py-2.5 text-right">
        {hasPrice ? (
          <span className={`text-[13px] tabular-nums ${pnl >= 0 ? 'text-mm-gain' : 'text-red-400'}`}>
            {pnl >= 0 ? '+' : ''}{formatCurrency(pnl, currency)}
          </span>
        ) : (
          <span className="text-[13px] text-mm-text-muted">—</span>
        )}
      </td>
      <td className="px-3 py-2.5 text-right">
        {hasPrice ? (
          <span className={`text-[13px] font-medium tabular-nums ${pnlPct >= 0 ? 'text-mm-gain' : 'text-red-400'}`}>
            {pnlPct >= 0 ? '+' : ''}{pnlPct.toFixed(2)}%
          </span>
        ) : (
          <span className="text-[13px] text-mm-text-muted">—</span>
        )}
      </td>
    </tr>
  );
}

// ── Asset-class section ──────────────────────────────────────────────────────

function AssetClassSection({ assetClass, positions, currency, accountValue }: {
  assetClass: string;
  positions: Position[];
  currency: string;
  accountValue: number;
}) {
  const [open, setOpen] = useState(true);
  const label = CATEGORY_LABELS[assetClass] ?? assetClass;

  const sectionTotal = positions.reduce((sum, p) => sum + (p.value ?? 0), 0);
  const sectionInvested = positions.reduce((sum, p) => sum + p.quantity * (p.avg_price ?? 0), 0);
  const hasValue = sectionTotal > 0;
  const pnl = sectionTotal - sectionInvested;
  const pnlPct = sectionInvested > 0 ? (pnl / sectionInvested) * 100 : null;

  const positionsWithPrice = positions.filter(p => (p.current_price ?? 0) > 0);
  const positionsNoPrice = positions.filter(p => (p.current_price ?? 0) <= 0);

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
          {positions.length} position{positions.length > 1 ? 's' : ''}
        </span>
        {hasValue ? (
          <>
            <span className="text-[13px] font-medium text-mm-text tabular-nums ml-4">
              {formatCurrency(sectionTotal, currency)}
            </span>
            {pnlPct != null && (
              <span className={`text-[12px] font-medium tabular-nums ml-2 ${
                pnlPct >= 0 ? 'text-mm-gain' : 'text-red-400'
              }`}>
                {pnlPct >= 0 ? '+' : ''}{pnlPct.toFixed(2)}%
              </span>
            )}
          </>
        ) : sectionInvested > 0 ? (
          <span className="text-[13px] text-mm-text-muted tabular-nums ml-4">
            Investi {formatCurrency(sectionInvested, currency)}
          </span>
        ) : null}
      </button>

      {open && (
        <table className="w-full">
          <thead>
            <tr className="bg-white/[0.01]">
              {['Nom', 'Qté', 'PRU', 'Cours', 'Valeur', 'Poids', '+/- val.', '+/- %'].map((h) => (
                <th key={h} className={`px-${h === 'Nom' ? '5' : '3'} py-1.5 text-[10px] font-medium uppercase tracking-wider text-mm-text-muted ${h === 'Nom' ? 'text-left' : 'text-right'}`}>
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
  const key = resolveAccountKey(account);
  const shortLabel = ACCOUNT_SHORT[key] ?? account.label;
  const longLabel = ACCOUNT_LABELS[key] ?? account.label;
  const Icon = ACCOUNT_ICONS[key] ?? Briefcase;
  const gradientClass = ACCOUNT_COLORS[key] ?? 'from-purple-500/10 to-transparent border-purple-500/20';
  const iconColor = ACCOUNT_ICON_COLORS[key] ?? 'text-purple-400';

  // Group positions by asset_class
  const byAssetClass = useMemo(() => {
    return account.positions.reduce<Record<string, Position[]>>((acc, pos) => {
      (acc[pos.asset_class] ??= []).push(pos);
      return acc;
    }, {});
  }, [account.positions]);

  const assetClasses = Object.keys(byAssetClass);
  const posCount = account.positions.length;

  // Compute account-level PnL from positions
  const totalPositionsValue = account.positions.reduce((s, p) => s + (p.value ?? 0), 0);
  const totalInvested = account.total_invested;
  const pnl = totalPositionsValue > 0 ? totalPositionsValue - totalInvested : 0;
  const pnlPct = totalInvested > 0 && totalPositionsValue > 0 ? (pnl / totalInvested) * 100 : 0;

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
              {totalInvested > 0
                ? formatCurrency(totalPositionsValue > 0 ? account.total_value : totalInvested, currency)
                : formatCurrency(account.total_value, currency)}
            </span>
            <div className="flex items-center gap-3 text-[12px]">
              {account.cash > 0 && (
                <span className="text-mm-text-muted">
                  Espèces <span className="text-mm-text-secondary tabular-nums">{formatCurrency(account.cash, currency)}</span>
                </span>
              )}
              {totalInvested > 0 && (
                <span className="text-mm-text-muted">
                  Investi <span className="text-mm-text-secondary tabular-nums">{formatCurrency(totalInvested, currency)}</span>
                </span>
              )}
              {totalPositionsValue > 0 && (
                <span className={`font-medium tabular-nums ${pnl >= 0 ? 'text-mm-gain' : 'text-red-400'}`}>
                  {pnl >= 0 ? '+' : ''}{formatCurrency(pnl, currency)} ({pnlPct >= 0 ? '+' : ''}{pnlPct.toFixed(2)}%)
                </span>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Asset class sections */}
      <div className="divide-y divide-mm-border/50">
        {assetClasses.map(assetClass => (
          <AssetClassSection
            key={assetClass}
            assetClass={assetClass}
            positions={byAssetClass[assetClass] ?? []}
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
  const { connectors } = useApp();
  const [portfolio, setPortfolio] = useState<PortfolioData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const fetchPortfolio = async () => {
    try {
      const data = await getPortfolio();
      setPortfolio(data);
    } catch (err: unknown) {
      setError((err as { detail?: string }).detail ?? 'Impossible de charger le portefeuille');
    }
  };

  useEffect(() => {
    setLoading(true);
    fetchPortfolio().finally(() => setLoading(false));
  }, []);

  // Auto-refresh while workers connected but portfolio empty
  const hasConnected = connectors.some(c => c.worker?.state === 'connected');
  const isEmpty = !portfolio || portfolio.accounts.length === 0;

  useEffect(() => {
    if (!hasConnected || !isEmpty) return;
    const interval = setInterval(fetchPortfolio, 5000);
    return () => clearInterval(interval);
  }, [hasConnected, isEmpty]);

  const totalPositions = useMemo(() => {
    if (!portfolio) return 0;
    return portfolio.accounts.reduce((s, a) => s + a.positions.length, 0);
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

  const currency = 'EUR';

  return (
    <div className="flex flex-col gap-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-mm-text">Portefeuille</h1>
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
          </div>
        </div>
      </div>

      {/* Account cards */}
      {portfolio.accounts.map(account => (
        <AccountCard key={account.account_id} account={account} currency={currency} />
      ))}
    </div>
  );
}
