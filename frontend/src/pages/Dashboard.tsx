import { useState, useEffect, useMemo } from 'react';
import { TrendingUp, Wallet, BarChart3, Trophy, ArrowDownLeft, ArrowUpRight } from 'lucide-react';
import { MetricCard } from '@/components/MetricCard';
import { PerformanceChart } from '@/components/PerformanceChart';
import { AccountRow } from '@/components/AccountRow';
import { useApp } from '@/context/AppContext';
import { getAccounts, getAccountBalance } from '@/api/accounts';
import { getPortfolio } from '@/api/portfolio';
import { getNetWorth, getNetWorthHistory } from '@/api/networth';
import { getCashflow } from '@/api/cashflow';
import { formatCurrency, formatPercent, formatDate, formatShortDate, getGreeting } from '@/lib/format';
import type { Account, Balance, Portfolio } from '@/lib/types';

const PERIODS = ['1W', '1M', '3M', '1Y', 'All'] as const;

function periodToDays(period: string): number | null {
  switch (period) {
    case '1W': return 7;
    case '1M': return 30;
    case '3M': return 90;
    case '1Y': return 365;
    case 'All': return null;
    default: return 90;
  }
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
    case 'woob_bank': return 'Bank (Woob)';
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

interface NetWorthHistoryPoint {
  date: string;
  total: number;
  bank_total: number;
  investments_total: number;
}

interface CashflowData {
  month: string;
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
  const [netWorthHistory, setNetWorthHistory] = useState<NetWorthHistoryPoint[]>([]);
  const [cashflow, setCashflow] = useState<CashflowData | null>(null);
  const [activePeriod, setActivePeriod] = useState<string>('3M');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;

    async function fetchData() {
      setLoading(true);
      setError('');
      try {
        const fromDate = new Date(Date.now() - 365 * 86400000).toISOString().split('T')[0];
        const currentMonth = new Date().toISOString().slice(0, 7);

        const [accts, port, nw, nwHistory, cf] = await Promise.all([
          getAccounts(),
          getPortfolio(),
          getNetWorth() as Promise<NetWorthData>,
          getNetWorthHistory(fromDate) as Promise<NetWorthHistoryPoint[]>,
          getCashflow(currentMonth) as Promise<CashflowData>,
        ]);

        if (cancelled) return;

        setAccounts(accts);
        setPortfolio(port);
        setNetWorth(nw);
        setNetWorthHistory(nwHistory);
        setCashflow(cf);

        const balanceMap: Record<string, Balance> = {};
        const balanceResults = await Promise.allSettled(
          accts.map((a) => getAccountBalance(a.id))
        );
        for (const result of balanceResults) {
          if (result.status === 'fulfilled') {
            balanceMap[result.value.account_id] = result.value;
          }
        }
        if (!cancelled) {
          setBalances(balanceMap);
        }
      } catch (err: unknown) {
        if (!cancelled) {
          const detail = (err as { detail?: string }).detail ?? 'Échec du chargement des données';
          setError(detail);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    fetchData();
    return () => { cancelled = true; };
  }, []);

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

  // Chart data from net worth history, filtered by period
  const chartData = useMemo(() => {
    const days = periodToDays(activePeriod);
    const cutoff = days ? Date.now() - days * 86400000 : 0;

    return netWorthHistory
      .filter((pt) => new Date(pt.date).getTime() >= cutoff)
      .sort((a, b) => a.date.localeCompare(b.date))
      .map((pt) => ({
        date: formatShortDate(pt.date),
        value: Math.round(pt.total * 100) / 100,
      }));
  }, [netWorthHistory, activePeriod]);

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

      {/* 4 cartes de métriques */}
      <div className="grid grid-cols-4 gap-4">
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
          label="Cashflow du mois"
          value={cashflow ? formatCurrency(cashflow.delta, currency) : '--'}
          valueClassName={`text-[32px] font-bold ${cashflowPositive ? 'text-mm-gain' : 'text-mm-loss'}`}
          sub={cashflow
            ? `↑ ${formatCurrency(cashflow.income, currency)} ↓ ${formatCurrency(cashflow.expenses, currency)}`
            : 'Aucune donnée'}
          icon={cashflowPositive
            ? <ArrowUpRight size={12} className="text-mm-gain" />
            : <ArrowDownLeft size={12} className="text-mm-loss" />}
        />
        <MetricCard
          label="Meilleure perf."
          value={bestPerformer?.name ?? '--'}
          valueClassName="text-[32px] font-bold text-mm-text"
          sub={bestPerformer ? `${formatPercent(bestPerformer.pnl_pct)}` : 'Aucune position'}
          icon={<Trophy size={12} className="text-mm-gold" />}
        />
      </div>

      {/* Courbe de performance */}
      <PerformanceChart
        data={chartData}
        periods={[...PERIODS]}
        activePeriod={activePeriod}
        onPeriodChange={setActivePeriod}
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
