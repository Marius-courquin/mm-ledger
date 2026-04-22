import { useState, useEffect, useMemo } from 'react';
import { TrendingUp, Wallet, BarChart3, Trophy, ArrowDownLeft, ArrowUpRight } from 'lucide-react';
import { MetricCard } from '@/components/MetricCard';
import { PortfolioPerfChart } from '@/components/PortfolioPerfChart';
import { getPerformanceHistory, type PerfHistory } from '@/api/performance';
import { AccountRow } from '@/components/AccountRow';
import { useApp } from '@/context/AppContext';
import { getAccounts, getAccountBalance } from '@/api/accounts';
import { getPortfolio } from '@/api/portfolio';
import { getNetWorth } from '@/api/networth';
import { getCashflow } from '@/api/cashflow';
import { formatCurrency, formatPercent, formatDate, getGreeting } from '@/lib/format';
import type { Account, Balance, Portfolio } from '@/lib/types';

const PERIODS = ['1W', '1M', '3M', '1Y', 'All'] as const;

function periodLabelFr(p: string): string {
  const map: Record<string, string> = {
    '1W': '7 jours', '1M': '1 mois', '3M': '3 mois', '1Y': '1 an', 'All': 'tout',
  };
  return map[p] ?? p;
}

const connectorIcons: Record<string, { icon: typeof TrendingUp; bg: string }> = {
  trade_republic: { icon: TrendingUp, bg: 'bg-[#1a3d4d]' },
  ibkr: { icon: BarChart3, bg: 'bg-[#2a1a4d]' },
  woob_bank: { icon: Wallet, bg: 'bg-[#1a4d3d]' },
};

function connectorSubtitle(type: string): string {
  switch (type) {
    case 'trade_republic': return 'Trade Republic';
    case 'ibkr': return 'Interactive Brokers';
    case 'woob_bank': return 'Banque';
    default: return type;
  }
}

interface NetWorthData {
  total: number;
  currency: string;
  bank_total: number;
  investments_total: number;
  investments_pnl: number;
  investments_pnl_pct: number;
  breakdown: { name: string; value: number; source: string; type: string }[];
}

const CASHFLOW_PERIODS = ['1W', '1M', '3M', '6M', '1Y', 'Max'] as const;

interface CashflowData {
  period: string;
  delta: number;
  income: number;
  expenses: number;
  sources: {
    source: string;
    label: string;
    delta: number;
    income: number;
    expenses: number;
    transactions: { date: string; label: string; amount: number; type: string }[];
  }[];
}

export function Dashboard() {
  const { connectors, user } = useApp();

  const [accounts, setAccounts] = useState<Account[]>([]);
  const [balances, setBalances] = useState<Record<string, Balance>>({});
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [netWorth, setNetWorth] = useState<NetWorthData | null>(null);
  const [perfHistory, setPerfHistory] = useState<PerfHistory | null>(null);
  const [cashflow, setCashflow] = useState<CashflowData | null>(null);
  const [cashflowPeriod, setCashflowPeriod] = useState<string>('1M');
  const [includeInvestments, setIncludeInvestments] = useState(true);
  const [activePeriod, setActivePeriod] = useState<string>('3M');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  // Fetch all dashboard data
  const fetchAllData = async () => {
    try {
      const [accts, port, nw] = await Promise.all([
        getAccounts(),
        getPortfolio(),
        getNetWorth() as Promise<NetWorthData>,
      ]);

      setAccounts(accts);
      setPortfolio(port);
      setNetWorth(nw);

      const balanceMap: Record<string, Balance> = {};
      const balanceResults = await Promise.allSettled(
        accts.map((a) => getAccountBalance(a.id))
      );
      for (const result of balanceResults) {
        if (result.status === 'fulfilled') {
          balanceMap[result.value.account_id] = result.value;
        }
      }
      setBalances(balanceMap);
    } catch (err: unknown) {
      setError((err as { detail?: string }).detail ?? 'Échec du chargement des données');
    }
  };

  // Initial fetch
  useEffect(() => {
    setLoading(true);
    fetchAllData().finally(() => setLoading(false));
  }, []);

  // Perf history fetch — refetch on period change
  useEffect(() => {
    getPerformanceHistory({ period: activePeriod })
      .then(setPerfHistory)
      .catch(() => setPerfHistory(null));
  }, [activePeriod]);

  // Auto-refresh: poll every 5s while any worker is connected but portfolio is empty
  const hasConnectedWorker = connectors.some(c => c.worker?.state === 'connected');
  const portfolioEmpty = !portfolio || portfolio.accounts.length === 0;

  useEffect(() => {
    if (!hasConnectedWorker || !portfolioEmpty) return;
    const interval = setInterval(() => { fetchAllData(); }, 5000);
    return () => clearInterval(interval);
  }, [hasConnectedWorker, portfolioEmpty]);

  // Cashflow fetch (separate, re-fetches on period/investment toggle change)
  useEffect(() => {
    let cancelled = false;
    getCashflow(cashflowPeriod, includeInvestments)
      .then((cf) => { if (!cancelled) setCashflow(cf as CashflowData); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [cashflowPeriod, includeInvestments]);

  const allPositions = useMemo(() => {
    if (!portfolio) return [];
    return portfolio.accounts.flatMap(acc =>
      acc.categories.flatMap(cat => cat.positions)
    );
  }, [portfolio]);

  const currency = useMemo(() => {
    return netWorth?.currency ?? Object.values(balances)[0]?.currency ?? 'EUR';
  }, [netWorth, balances]);

  const bestPerformer = useMemo(() => {
    if (allPositions.length === 0) return null;
    return allPositions.reduce((best, pos) =>
      pos.pnl_pct > best.pnl_pct ? pos : best
    );
  }, [allPositions]);


  // Group accounts by connector
  const connectorAccounts = useMemo(() => {
    const map = new Map<string, Account[]>();
    for (const acct of accounts) {
      const list = map.get(acct.connector_id) ?? [];
      list.push(acct);
      map.set(acct.connector_id, list);
    }
    return map;
  }, [accounts]);

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

  const cashflowPositive = (cashflow?.delta ?? 0) >= 0;

  return (
    <div className="flex flex-col gap-8">
      {/* En-tête de bienvenue */}
      <div className="flex flex-col gap-1">
        <h1 className="text-[28px] font-semibold text-mm-text">
          {getGreeting()}, {user?.username ?? ''}
        </h1>
        <p className="text-sm text-mm-text-muted">
          {formatDate(new Date().toISOString())}
        </p>
      </div>

      {/* 3 cartes de métriques */}
      <div className="grid grid-cols-3 gap-4">
        <MetricCard
          label="Capital NET"
          value={formatCurrency(netWorth?.total ?? 0, currency)}
          valueClassName="text-[32px] font-bold text-mm-gold"
          sub={`Banque: ${formatCurrency(netWorth?.bank_total ?? 0, currency)} · Invest.: ${formatCurrency(netWorth?.investments_total ?? 0, currency)}`}
          icon={<Wallet size={12} className="text-mm-text-muted" />}
        />
        <MetricCard
          label="Investissements"
          value={formatCurrency(netWorth?.investments_total ?? 0, currency)}
          valueClassName="text-[32px] font-bold text-mm-text"
          sub={`P&L: ${formatCurrency(netWorth?.investments_pnl ?? 0, currency)} (${formatPercent(netWorth?.investments_pnl_pct ?? 0)})`}
          icon={<TrendingUp size={12} className={netWorth && netWorth.investments_pnl >= 0 ? 'text-mm-gain' : 'text-mm-loss'} />}
        />
        <MetricCard
          label="Meilleure perf."
          value={bestPerformer?.name ?? '--'}
          valueClassName="text-[32px] font-bold text-mm-text"
          sub={bestPerformer ? `${formatPercent(bestPerformer.pnl_pct)}` : 'Aucune position'}
          icon={<Trophy size={12} className="text-mm-gold" />}
        />
      </div>

      {/* Cashflow avec sélecteur de période */}
      <div className="bg-mm-surface border border-mm-border rounded-[12px] p-5">
        <div className="flex items-center justify-between mb-4">
          <div className="flex flex-col gap-0.5">
            <h2 className="text-base font-semibold text-mm-text">Cashflow</h2>
            <div className="flex items-center gap-2">
              <span className={`text-[28px] font-bold tabular-nums ${cashflowPositive ? 'text-mm-gain' : 'text-red-400'}`}>
                {cashflow ? `${cashflow.delta >= 0 ? '+' : ''}${formatCurrency(cashflow.delta, currency)}` : '--'}
              </span>
            </div>
            <div className="flex items-center gap-3 text-[12px] text-mm-text-muted">
              {cashflow && (
                <>
                  <span className="flex items-center gap-1">
                    <ArrowUpRight size={10} className="text-mm-gain" />
                    <span className="text-mm-gain tabular-nums">{formatCurrency(cashflow.income, currency)}</span>
                  </span>
                  <span className="flex items-center gap-1">
                    <ArrowDownLeft size={10} className="text-red-400" />
                    <span className="text-red-400 tabular-nums">{formatCurrency(Math.abs(cashflow.expenses), currency)}</span>
                  </span>
                </>
              )}
            </div>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={() => setIncludeInvestments(v => !v)}
              className={`px-2.5 py-1 text-[11px] font-medium rounded-[6px] border transition-colors ${
                includeInvestments
                  ? 'border-mm-gold text-mm-gold'
                  : 'border-mm-border text-mm-text-muted'
              }`}
            >
              {includeInvestments ? '📈 Invest. inclus' : '📈 Invest. exclus'}
            </button>
            <div className="flex gap-1">
              {CASHFLOW_PERIODS.map((p) => (
                <button
                  key={p}
                  onClick={() => setCashflowPeriod(p)}
                  className={`px-2.5 py-1 text-[11px] font-medium rounded-[6px] transition-colors ${
                    cashflowPeriod === p
                      ? 'bg-mm-gold text-mm-bg'
                      : 'text-mm-text-muted hover:text-mm-text-secondary'
                  }`}
                >
                  {p}
                </button>
              ))}
            </div>
          </div>
        </div>
        {cashflow && cashflow.sources.length > 0 && (
          <div className="flex flex-col gap-2 border-t border-mm-border pt-3">
            {cashflow.sources.map((src) => (
              <div key={src.source} className="flex items-center justify-between text-[13px]">
                <span className="text-mm-text-secondary">{src.label}</span>
                <div className="flex items-center gap-3">
                  <span className="text-mm-gain tabular-nums text-[12px]">↑ {formatCurrency(src.income, currency)}</span>
                  <span className="text-red-400 tabular-nums text-[12px]">↓ {formatCurrency(Math.abs(src.expenses), currency)}</span>
                  <span className={`font-medium tabular-nums ${src.delta >= 0 ? 'text-mm-gain' : 'text-red-400'}`}>
                    {src.delta >= 0 ? '+' : ''}{formatCurrency(src.delta, currency)}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Courbe de performance */}
      <PortfolioPerfChart
        series={perfHistory?.series ?? []}
        totalPct={perfHistory?.total_pct ?? 0}
        valueNow={perfHistory?.value_now ?? 0}
        currency={perfHistory?.currency ?? currency}
        periods={[...PERIODS]}
        activePeriod={activePeriod}
        onPeriodChange={setActivePeriod}
        periodLabel={periodLabelFr(activePeriod)}
      />

      {/* Comptes connectés */}
      <div className="flex flex-col gap-3">
        <h2 className="text-base font-semibold text-mm-text">Comptes connectés</h2>
        <div className="bg-mm-surface border border-mm-border rounded-[12px] overflow-hidden">
          {connectors.length === 0 && (
            <div className="px-5 py-8 text-center text-sm text-mm-text-muted">
              Aucun connecteur configuré.
            </div>
          )}
          {connectors.map((connector) => {
            const accts = connectorAccounts.get(connector.id) ?? [];
            const iconInfo = connectorIcons[connector.type] ?? { icon: Wallet, bg: 'bg-mm-surface-elevated' };
            const IconComponent = iconInfo.icon;

            if (accts.length === 0) {
              const connectorBalance = Object.values(balances)
                .filter((b) => accounts.find((a) => a.id === b.account_id && a.connector_id === connector.id))
                .reduce((sum, b) => sum + b.total_value, 0);

              return (
                <AccountRow
                  key={connector.id}
                  name={connector.label}
                  subtitle={connectorSubtitle(connector.type)}
                  balance={formatCurrency(connectorBalance, currency)}
                  perf={formatPercent(0)}
                  iconBg={iconInfo.bg}
                  icon={<IconComponent size={16} className="text-mm-text" />}
                />
              );
            }

            return accts.map((acct) => {
              const bal = balances[acct.id];
              return (
                <AccountRow
                  key={acct.id}
                  name={acct.name}
                  subtitle={connectorSubtitle(connector.type)}
                  balance={bal ? formatCurrency(bal.total_value, bal.currency) : '--'}
                  perf={formatPercent(0)}
                  iconBg={iconInfo.bg}
                  icon={<IconComponent size={16} className="text-mm-text" />}
                />
              );
            });
          })}
        </div>
      </div>
    </div>
  );
}
