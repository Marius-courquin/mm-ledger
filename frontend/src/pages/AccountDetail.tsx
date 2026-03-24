import { useState, useEffect, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  ArrowLeft,
  Landmark,
  Download,
  Unplug,
  Plug,
  TrendingUp,
} from 'lucide-react';
import { MetricCard } from '@/components/MetricCard';
import { PerformanceChart } from '@/components/PerformanceChart';
import { useApp } from '@/context/AppContext';
import {
  getConnectorStatus,
  connectConnector,
  disconnectConnector,
} from '@/api/connectors';
import { getAccounts, getAccountBalance } from '@/api/accounts';
import { getSnapshots } from '@/api/snapshots';
import { getTransactions } from '@/api/transactions';
import {
  formatCurrency,
  formatPercent,
  formatShortDate,
} from '@/lib/format';
import type {
  Account,
  Balance,
  Snapshot,
  Transaction,
  WorkerInfo,
  WorkerState,
} from '@/lib/types';

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

const statusLabels: Record<WorkerState, string> = {
  connected: 'Connected',
  connecting: 'Connecting...',
  waiting_2fa: 'Awaiting 2FA',
  error: 'Error',
  disconnected: 'Disconnected',
};

const txTypeBadge: Record<string, { bg: string; text: string }> = {
  buy: { bg: 'bg-mm-chart-1/20', text: 'text-mm-chart-1' },
  sell: { bg: 'bg-mm-chart-5/20', text: 'text-mm-chart-5' },
  dividend: { bg: 'bg-mm-chart-3/20', text: 'text-mm-chart-3' },
  fee: { bg: 'bg-mm-chart-6/20', text: 'text-mm-chart-6' },
  transfer: { bg: 'bg-mm-chart-4/20', text: 'text-mm-chart-4' },
  interest: { bg: 'bg-mm-chart-2/20', text: 'text-mm-chart-2' },
};

export function AccountDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { connectors, refreshConnectors } = useApp();

  const connector = connectors.find((c) => c.id === id);

  const [workerInfo, setWorkerInfo] = useState<WorkerInfo | null>(null);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [balances, setBalances] = useState<Balance[]>([]);
  const [snapshots, setSnapshots] = useState<Snapshot[]>([]);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [activePeriod, setActivePeriod] = useState<string>('3M');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!id) return;
    let cancelled = false;

    async function fetchData() {
      setLoading(true);
      setError('');
      try {
        const [status, accts] = await Promise.all([
          getConnectorStatus(id!),
          getAccounts(id),
        ]);
        if (cancelled) return;

        setWorkerInfo(status);
        setAccounts(accts);

        const firstAccountId = accts[0]?.id;

        const [balanceResults, snapResults, txResults] = await Promise.all([
          Promise.allSettled(accts.map((a) => getAccountBalance(a.id))),
          firstAccountId
            ? getSnapshots({
                account_id: firstAccountId,
                from: new Date(Date.now() - 365 * 86400000).toISOString().split('T')[0],
              })
            : Promise.resolve([]),
          Promise.allSettled(
            accts.map((a) => getTransactions({ account_id: a.id, limit: 50 }))
          ),
        ]);

        if (cancelled) return;

        const bals: Balance[] = [];
        for (const r of balanceResults) {
          if (r.status === 'fulfilled') bals.push(r.value);
        }
        setBalances(bals);
        setSnapshots(snapResults);

        const txs: Transaction[] = [];
        for (const r of txResults) {
          if (r.status === 'fulfilled') txs.push(...r.value);
        }
        txs.sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime());
        setTransactions(txs);
      } catch (err: unknown) {
        if (!cancelled) {
          const detail = (err as { detail?: string }).detail ?? 'Failed to load account data';
          setError(detail);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    fetchData();
    return () => { cancelled = true; };
  }, [id]);

  const totalBalance = useMemo(() => {
    return balances.reduce((sum, b) => sum + b.total_value, 0);
  }, [balances]);

  const totalCash = useMemo(() => {
    return balances.reduce((sum, b) => sum + b.cash, 0);
  }, [balances]);

  const totalPositionsValue = useMemo(() => {
    return balances.reduce((sum, b) => sum + b.positions_value, 0);
  }, [balances]);

  const currency = balances[0]?.currency ?? 'EUR';

  const workerState: WorkerState = workerInfo?.state ?? connector?.worker?.state ?? 'disconnected';
  const isConnected = workerState === 'connected';

  // Chart data
  const chartData = useMemo(() => {
    const days = periodToDays(activePeriod);
    const cutoff = days ? Date.now() - days * 86400000 : 0;

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

  async function handleConnect() {
    if (!id) return;
    try {
      await connectConnector(id);
      refreshConnectors();
    } catch (err: unknown) {
      setError((err as { detail?: string }).detail ?? 'Failed to connect');
    }
  }

  async function handleDisconnect() {
    if (!id) return;
    try {
      await disconnectConnector(id);
      refreshConnectors();
    } catch (err: unknown) {
      setError((err as { detail?: string }).detail ?? 'Failed to disconnect');
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-mm-gold border-t-transparent" />
      </div>
    );
  }

  if (error && !connector) {
    return (
      <div className="flex items-center justify-center h-64">
        <p className="text-sm text-red-400">{error}</p>
      </div>
    );
  }

  const connectorLabel = connector?.label ?? id ?? 'Unknown';
  const connectorType = connector?.type ?? 'unknown';

  return (
    <div className="flex flex-col gap-8">
      {/* Back link */}
      <button
        onClick={() => navigate('/accounts')}
        className="flex items-center gap-1.5 text-sm text-mm-lavender hover:underline w-fit"
      >
        <ArrowLeft size={16} />
        Back to Accounts
      </button>

      {/* Header */}
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-4">
          <div className="flex h-[52px] w-[52px] items-center justify-center rounded-[12px] bg-mm-surface border border-mm-border">
            <Landmark size={24} className="text-mm-gold" />
          </div>
          <div className="flex flex-col gap-1">
            <div className="flex items-center gap-2">
              <h1 className="text-2xl font-semibold text-mm-text">{connectorLabel}</h1>
              <span className="rounded-[4px] bg-mm-lilac px-2 py-0.5 text-[11px] font-medium text-mm-text">
                {connectorType}
              </span>
            </div>
            <span className="text-[13px] text-mm-text-muted">
              {statusLabels[workerState]} &middot; {accounts.length} account{accounts.length !== 1 ? 's' : ''}
            </span>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button className="flex items-center gap-2 border border-mm-border text-mm-text-secondary rounded-[8px] px-4 py-2 text-sm hover:bg-mm-surface-elevated/30 transition-colors">
            <Download size={16} />
            Export
          </button>
          {isConnected ? (
            <button
              onClick={handleDisconnect}
              className="flex items-center gap-2 border border-mm-border text-mm-text-secondary rounded-[8px] px-4 py-2 text-sm hover:bg-mm-surface-elevated/30 transition-colors"
            >
              <Unplug size={16} />
              Disconnect
            </button>
          ) : (
            <button
              onClick={handleConnect}
              className="flex items-center gap-2 border border-mm-border text-mm-text-secondary rounded-[8px] px-4 py-2 text-sm hover:bg-mm-surface-elevated/30 transition-colors"
            >
              <Plug size={16} />
              Connect
            </button>
          )}
        </div>
      </div>

      {error && <p className="text-sm text-red-400">{error}</p>}

      {/* 3 Metric Cards */}
      <div className="grid grid-cols-3 gap-4">
        <MetricCard
          label="Account Balance"
          value={formatCurrency(totalBalance, currency)}
          valueClassName="text-[32px] font-bold text-mm-gold"
          sub={`${formatPercent(0)} all time`}
          icon={<TrendingUp size={12} className="text-mm-gain" />}
        />
        <MetricCard
          label="Cash Available"
          value={formatCurrency(totalCash, currency)}
          valueClassName="text-[32px] font-bold text-mm-text"
        />
        <MetricCard
          label="Positions Value"
          value={formatCurrency(totalPositionsValue, currency)}
          valueClassName="text-[32px] font-bold text-mm-text"
        />
      </div>

      {/* Balance History Chart */}
      <PerformanceChart
        data={chartData}
        periods={[...PERIODS]}
        activePeriod={activePeriod}
        onPeriodChange={setActivePeriod}
      />

      {/* Transactions Table */}
      <div className="bg-mm-surface border border-mm-border rounded-[12px] overflow-hidden">
        <div className="flex items-center justify-between px-5 py-4">
          <h3 className="text-base font-semibold text-mm-text">Recent Transactions</h3>
          <span className="text-xs text-mm-text-muted">{transactions.length} transactions</span>
        </div>

        {transactions.length === 0 ? (
          <div className="px-5 py-8 text-center text-sm text-mm-text-muted border-t border-mm-border">
            No transactions found.
          </div>
        ) : (
          <table className="w-full">
            <thead>
              <tr className="border-t border-mm-border">
                <th className="px-5 py-2.5 text-left text-[11px] font-semibold uppercase tracking-wide text-mm-text-muted">
                  Date
                </th>
                <th className="w-[90px] px-3 py-2.5 text-left text-[11px] font-semibold uppercase tracking-wide text-mm-text-muted">
                  Type
                </th>
                <th className="px-3 py-2.5 text-left text-[11px] font-semibold uppercase tracking-wide text-mm-text-muted">
                  Label
                </th>
                <th className="w-[120px] px-3 py-2.5 text-right text-[11px] font-semibold uppercase tracking-wide text-mm-text-muted">
                  Amount
                </th>
                <th className="w-[100px] px-3 py-2.5 text-left text-[11px] font-semibold uppercase tracking-wide text-mm-text-muted">
                  Instrument
                </th>
              </tr>
            </thead>
            <tbody>
              {transactions.map((tx) => {
                const badge = txTypeBadge[tx.type] ?? { bg: 'bg-mm-surface-elevated', text: 'text-mm-text-muted' };
                const isNegative = tx.amount < 0;
                return (
                  <tr key={tx.id} className="border-t border-mm-border">
                    <td className="px-5 py-3">
                      <span className="text-[13px] text-mm-text-secondary">
                        {formatShortDate(tx.date)}
                      </span>
                    </td>
                    <td className="w-[90px] px-3 py-3">
                      <span className={`inline-block rounded-[4px] px-2 py-0.5 text-[11px] font-medium ${badge.bg} ${badge.text}`}>
                        {tx.type}
                      </span>
                    </td>
                    <td className="px-3 py-3">
                      <span className="text-[13px] text-mm-text">{tx.label}</span>
                    </td>
                    <td className="w-[120px] px-3 py-3 text-right">
                      <span className={`text-[13px] font-medium tabular-nums ${isNegative ? 'text-mm-loss' : 'text-mm-gain'}`}>
                        {formatCurrency(tx.amount, tx.currency)}
                      </span>
                    </td>
                    <td className="w-[100px] px-3 py-3">
                      <span className="text-[13px] text-mm-text-muted">
                        {tx.instrument ?? '--'}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
