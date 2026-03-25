import { useState, useEffect, useMemo } from 'react';
import { TrendingUp, Wallet, BarChart3, Trophy } from 'lucide-react';
import { MetricCard } from '@/components/MetricCard';
import { PerformanceChart } from '@/components/PerformanceChart';
import { AccountRow } from '@/components/AccountRow';
import { useApp } from '@/context/AppContext';
import { getAccounts, getAccountBalance } from '@/api/accounts';
import { getPortfolio } from '@/api/portfolio';
import { getSnapshots } from '@/api/snapshots';
import { getPerformance } from '@/api/performance';
import { formatCurrency, formatPercent, formatDate, formatShortDate, getGreeting } from '@/lib/format';
import type { Account, Balance, Portfolio, Snapshot, Performance } from '@/lib/types';

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

export function Dashboard() {
  const { connectors, user } = useApp();

  const [accounts, setAccounts] = useState<Account[]>([]);
  const [balances, setBalances] = useState<Record<string, Balance>>({});
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [snapshots, setSnapshots] = useState<Snapshot[]>([]);
  const [perfData, setPerfData] = useState<Performance[]>([]);
  const [activePeriod, setActivePeriod] = useState<string>('3M');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;

    async function fetchData() {
      setLoading(true);
      setError('');
      try {
        const [accts, port, snaps, perf] = await Promise.all([
          getAccounts(),
          getPortfolio(),
          getSnapshots({ from: new Date(Date.now() - 365 * 86400000).toISOString().split('T')[0] }),
          getPerformance(),
        ]);

        if (cancelled) return;

        setAccounts(accts);
        setPortfolio(port);
        setSnapshots(snaps);
        setPerfData(perf);

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
          const detail = (err as { detail?: string }).detail ?? 'Failed to load dashboard data';
          setError(detail);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    fetchData();
    return () => { cancelled = true; };
  }, []);

  // Compute metrics
  const allPositions = useMemo(() => {
    if (!portfolio) return [];
    return portfolio.accounts.flatMap(acc =>
      acc.categories.flatMap(cat => cat.positions)
    );
  }, [portfolio]);

  const totalBalance = useMemo(() => {
    return portfolio?.total_value ?? Object.values(balances).reduce((sum, b) => sum + b.total_value, 0);
  }, [portfolio, balances]);

  const totalCurrency = useMemo(() => {
    const currencies = Object.values(balances).map((b) => b.currency);
    return currencies[0] ?? 'EUR';
  }, [balances]);

  const monthlyPnl = useMemo(() => {
    if (perfData.length === 0) return { pnl: 0, pnl_pct: 0 };
    const totals = perfData.reduce(
      (acc, p) => ({ pnl: acc.pnl + p.pnl, invested: acc.invested + p.total_invested }),
      { pnl: 0, invested: 0 }
    );
    const pct = totals.invested > 0 ? (totals.pnl / totals.invested) * 100 : 0;
    return { pnl: totals.pnl, pnl_pct: pct };
  }, [perfData]);

  const connectedCount = useMemo(() => {
    return connectors.filter((c) => c.worker?.state === 'connected').length;
  }, [connectors]);

  const bestPerformer = useMemo(() => {
    if (allPositions.length === 0) return null;
    return allPositions.reduce((best, pos) =>
      pos.pnl_pct > best.pnl_pct ? pos : best
    );
  }, [allPositions]);

  // Chart data filtered by period
  const chartData = useMemo(() => {
    const days = periodToDays(activePeriod);
    const cutoff = days ? Date.now() - days * 86400000 : 0;

    // Aggregate snapshots by date
    const dateMap = new Map<string, number>();
    for (const snap of snapshots) {
      const snapTime = new Date(snap.date).getTime();
      if (snapTime >= cutoff) {
        const dateKey = snap.date.split('T')[0] ?? snap.date;
        dateMap.set(dateKey, (dateMap.get(dateKey) ?? 0) + snap.total_value);
      }
    }

    return Array.from(dateMap.entries())
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([date, value]) => ({
        date: formatShortDate(date),
        value: Math.round(value * 100) / 100,
      }));
  }, [snapshots, activePeriod]);

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

  return (
    <div className="flex flex-col gap-8">
      {/* Welcome Header */}
      <div className="flex flex-col gap-1">
        <h1 className="text-[28px] font-semibold text-mm-text">
          {getGreeting()}, {user?.username ?? ''}
        </h1>
        <p className="text-sm text-mm-text-muted">
          {formatDate(new Date().toISOString())}
        </p>
      </div>

      {/* 4 Metric Cards */}
      <div className="grid grid-cols-4 gap-4">
        <MetricCard
          label="Solde total"
          value={formatCurrency(totalBalance, totalCurrency)}
          valueClassName="text-[32px] font-bold text-mm-gold"
          sub="Tous les comptes"
          icon={<Wallet size={12} className="text-mm-text-muted" />}
        />
        <MetricCard
          label="P&L mensuel"
          value={formatCurrency(monthlyPnl.pnl, totalCurrency)}
          valueClassName="text-[32px] font-bold text-mm-gain"
          sub={`${formatPercent(monthlyPnl.pnl_pct)} ce mois`}
          icon={<TrendingUp size={12} className="text-mm-gain" />}
        />
        <MetricCard
          label="Comptes"
          value={String(accounts.length)}
          valueClassName="text-[32px] font-bold text-mm-text"
          sub={`${connectedCount} connecté${connectedCount > 1 ? 's' : ''}`}
        />
        <MetricCard
          label="Meilleure perf."
          value={bestPerformer?.name ?? '--'}
          valueClassName="text-[32px] font-bold text-mm-text"
          sub={bestPerformer ? `${formatPercent(bestPerformer.pnl_pct)}` : 'Aucune position'}
          icon={<Trophy size={12} className="text-mm-gold" />}
        />
      </div>

      {/* Performance Chart */}
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
                  balance={formatCurrency(connectorBalance, totalCurrency)}
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
