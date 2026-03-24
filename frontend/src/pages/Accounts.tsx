import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Plus, Plug, Unplug, Landmark, TrendingUp, BarChart3, Wallet } from 'lucide-react';
import { ConnectorForm } from '@/components/ConnectorForm';
import { useApp } from '@/context/AppContext';
import {
  getConnectorTypes,
  createConnector,
  connectConnector,
  disconnectConnector,
} from '@/api/connectors';
import { getAccounts } from '@/api/accounts';
import type { ConnectorTypeInfo, ConnectorType, WorkerState, Account } from '@/lib/types';

const statusConfig: Record<WorkerState, { color: string; label: string }> = {
  connected: { color: 'bg-green-500', label: 'Connected' },
  connecting: { color: 'bg-yellow-500', label: 'Connecting' },
  waiting_2fa: { color: 'bg-yellow-500', label: 'Waiting 2FA' },
  error: { color: 'bg-red-500', label: 'Error' },
  disconnected: { color: 'bg-gray-500', label: 'Disconnected' },
};

const connectorIconMap: Record<string, { icon: typeof Landmark; bg: string }> = {
  trade_republic: { icon: TrendingUp, bg: 'bg-[#1a3d4d]' },
  ibkr: { icon: BarChart3, bg: 'bg-[#2a1a4d]' },
  woob_bank: { icon: Landmark, bg: 'bg-[#1a4d3d]' },
};

export function Accounts() {
  const navigate = useNavigate();
  const { connectors, refreshConnectors } = useApp();

  const [connectorTypes, setConnectorTypes] = useState<ConnectorTypeInfo[]>([]);
  const [accountsByConnector, setAccountsByConnector] = useState<Record<string, Account[]>>({});
  const [formOpen, setFormOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;

    async function fetchData() {
      setLoading(true);
      setError('');
      try {
        const [types, accts] = await Promise.all([
          getConnectorTypes(),
          getAccounts(),
        ]);
        if (cancelled) return;
        setConnectorTypes(types);

        const grouped: Record<string, Account[]> = {};
        for (const acct of accts) {
          const cid = acct.connector_id;
          if (cid) {
            if (!grouped[cid]) {
              grouped[cid] = [];
            }
            grouped[cid].push(acct);
          }
        }
        setAccountsByConnector(grouped);
      } catch (err: unknown) {
        if (!cancelled) {
          const detail = (err as { detail?: string }).detail ?? 'Failed to load data';
          setError(detail);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    fetchData();
    return () => { cancelled = true; };
  }, [connectors]);

  async function handleCreateConnector(data: {
    type: ConnectorType;
    label: string;
    credentials: Record<string, string>;
    config: Record<string, string>;
  }) {
    const created = await createConnector({
      type: data.type,
      label: data.label,
      credentials: data.credentials,
      config: data.config,
    });
    await connectConnector(created.id);
    refreshConnectors();
  }

  async function handleConnect(id: string) {
    try {
      await connectConnector(id);
      refreshConnectors();
    } catch (err: unknown) {
      const detail = (err as { detail?: string }).detail ?? 'Failed to connect';
      setError(detail);
    }
  }

  async function handleDisconnect(id: string) {
    try {
      await disconnectConnector(id);
      refreshConnectors();
    } catch (err: unknown) {
      const detail = (err as { detail?: string }).detail ?? 'Failed to disconnect';
      setError(detail);
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-mm-gold border-t-transparent" />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-8">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div className="flex flex-col gap-1">
          <h1 className="text-2xl font-semibold text-mm-text">Accounts</h1>
          <p className="text-[13px] text-mm-text-muted">Manage your connected accounts</p>
        </div>
        <button
          onClick={() => setFormOpen(true)}
          className="flex items-center gap-2 border border-mm-border text-mm-text rounded-[8px] px-4 py-2 text-sm hover:bg-mm-surface-elevated/30 transition-colors"
        >
          <Plus size={16} />
          Add Connector
        </button>
      </div>

      {error && (
        <p className="text-sm text-red-400">{error}</p>
      )}

      {/* Connector Cards Grid */}
      <div className="grid grid-cols-2 gap-4">
        {connectors.length === 0 && (
          <div className="col-span-2 bg-mm-surface border border-mm-border rounded-[12px] p-8 text-center text-sm text-mm-text-muted">
            No connectors configured. Click "Add Connector" to get started.
          </div>
        )}

        {connectors.map((connector) => {
          const workerState: WorkerState = connector.worker?.state ?? 'disconnected';
          const status = statusConfig[workerState];
          const iconInfo = connectorIconMap[connector.type] ?? { icon: Wallet, bg: 'bg-mm-surface-elevated' };
          const IconComponent = iconInfo.icon;
          const accts = accountsByConnector[connector.id] ?? [];
          const isConnected = workerState === 'connected';

          return (
            <div
              key={connector.id}
              className="bg-mm-surface border border-mm-border rounded-[12px] p-4 flex flex-col gap-3 cursor-pointer hover:bg-mm-surface-elevated/30 transition-colors"
              onClick={() => navigate(`/accounts/${connector.id}`)}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => {
                if (e.key === 'Enter') navigate(`/accounts/${connector.id}`);
              }}
            >
              {/* Top row: icon + label + status */}
              <div className="flex items-center gap-3">
                <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-[12px] ${iconInfo.bg}`}>
                  <IconComponent size={20} className="text-mm-text" />
                </div>
                <div className="flex flex-col flex-1 min-w-0">
                  <span className="text-sm font-medium text-mm-text truncate">{connector.label}</span>
                  <span className="text-[11px] text-mm-text-muted">{connector.type}</span>
                </div>
                <div className="flex items-center gap-1.5 shrink-0">
                  <div className={`h-2 w-2 rounded-full ${status.color}`} />
                  <span className="text-xs text-mm-text-secondary">{status.label}</span>
                </div>
              </div>

              {/* Middle: account count */}
              <div className="text-xs text-mm-text-muted">
                {accts.length} account{accts.length !== 1 ? 's' : ''}
              </div>

              {/* Bottom: actions */}
              <div className="flex items-center justify-between pt-1">
                <span
                  className="text-xs font-medium text-mm-lavender hover:underline"
                  onClick={(e) => {
                    e.stopPropagation();
                    navigate(`/accounts/${connector.id}`);
                  }}
                  role="link"
                  tabIndex={0}
                >
                  View Details
                </span>
                {isConnected ? (
                  <button
                    className="flex items-center gap-1.5 border border-mm-border text-mm-text-secondary text-xs rounded-[6px] px-3 h-7 hover:bg-mm-surface-elevated/30 transition-colors"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleDisconnect(connector.id);
                    }}
                  >
                    <Unplug size={14} />
                    Disconnect
                  </button>
                ) : (
                  <button
                    className="flex items-center gap-1.5 border border-mm-border text-mm-text-secondary text-xs rounded-[6px] px-3 h-7 hover:bg-mm-surface-elevated/30 transition-colors"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleConnect(connector.id);
                    }}
                  >
                    <Plug size={14} />
                    Connect
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* ConnectorForm Modal */}
      <ConnectorForm
        isOpen={formOpen}
        onClose={() => setFormOpen(false)}
        connectorTypes={connectorTypes}
        onSubmit={handleCreateConnector}
      />

      {/* 2FA Dialog handled globally in App.tsx */}
    </div>
  );
}
