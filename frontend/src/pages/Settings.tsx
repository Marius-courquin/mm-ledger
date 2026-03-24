import { useState, useEffect } from 'react';
import {
  Pencil,
  Trash2,
  Plus,
  Lock,
  Activity,
  Clock,
  CheckCircle2,
  XCircle,
} from 'lucide-react';
import { ConnectorForm } from '@/components/ConnectorForm';
import { useApp } from '@/context/AppContext';
import {
  getConnectorTypes,
  createConnector,
  connectConnector,
  updateConnector,
  deleteConnector,
} from '@/api/connectors';
import { lockVault, changePassword } from '@/api/vault';
import { getHealth, getSchedulerStatus } from '@/api/system';
import type {
  ConnectorTypeInfo,
  ConnectorType,
  Connector,
  HealthCheck,
  SchedulerStatus,
  WorkerState,
} from '@/lib/types';
import { formatRelativeTime } from '@/lib/format';

const statusColors: Record<WorkerState, string> = {
  connected: 'text-green-400',
  connecting: 'text-yellow-400',
  waiting_2fa: 'text-yellow-400',
  error: 'text-red-400',
  disconnected: 'text-gray-400',
};

export function Settings() {
  const { connectors, refreshConnectors, setVaultState } = useApp();

  // Connector form state
  const [connectorTypes, setConnectorTypes] = useState<ConnectorTypeInfo[]>([]);
  const [formOpen, setFormOpen] = useState(false);
  const [editingConnector, setEditingConnector] = useState<Connector | undefined>(undefined);
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null);
  const [connectorError, setConnectorError] = useState('');

  // Vault state
  const [oldPassword, setOldPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmNewPassword, setConfirmNewPassword] = useState('');
  const [passwordLoading, setPasswordLoading] = useState(false);
  const [passwordError, setPasswordError] = useState('');
  const [passwordSuccess, setPasswordSuccess] = useState('');

  // System state
  const [health, setHealth] = useState<HealthCheck | null>(null);
  const [scheduler, setScheduler] = useState<SchedulerStatus | null>(null);
  const [systemLoading, setSystemLoading] = useState(true);

  // Fetch connector types on mount
  useEffect(() => {
    getConnectorTypes()
      .then(setConnectorTypes)
      .catch(() => { /* ignore */ });
  }, []);

  // Fetch system info
  useEffect(() => {
    let cancelled = false;

    async function fetchSystem() {
      setSystemLoading(true);
      try {
        const [h, s] = await Promise.all([getHealth(), getSchedulerStatus()]);
        if (!cancelled) {
          setHealth(h);
          setScheduler(s);
        }
      } catch {
        // ignore
      } finally {
        if (!cancelled) setSystemLoading(false);
      }
    }

    fetchSystem();
    return () => { cancelled = true; };
  }, []);

  // Connector handlers
  async function handleConnectorSubmit(data: {
    type: ConnectorType;
    label: string;
    credentials: Record<string, string>;
    config: Record<string, string>;
  }) {
    setConnectorError('');
    try {
      if (editingConnector) {
        await updateConnector(editingConnector.id, {
          label: data.label,
          credentials: data.credentials,
          config: data.config,
        });
      } else {
        const created = await createConnector({
          type: data.type,
          label: data.label,
          credentials: data.credentials,
          config: data.config,
        });
        await connectConnector(created.id);
      }
      refreshConnectors();
    } catch (err: unknown) {
      const detail = (err as { detail?: string }).detail ?? 'Operation failed';
      setConnectorError(detail);
      throw err;
    }
  }

  async function handleDelete(id: string) {
    setConnectorError('');
    try {
      await deleteConnector(id);
      refreshConnectors();
      setDeleteConfirm(null);
    } catch (err: unknown) {
      const detail = (err as { detail?: string }).detail ?? 'Failed to delete connector';
      setConnectorError(detail);
    }
  }

  // Vault handlers
  async function handleLockVault() {
    try {
      await lockVault();
      setVaultState('locked');
    } catch {
      // handled by vault-locked event
    }
  }

  async function handleChangePassword() {
    setPasswordError('');
    setPasswordSuccess('');

    if (newPassword.length < 4) {
      setPasswordError('New password must be at least 4 characters');
      return;
    }
    if (newPassword !== confirmNewPassword) {
      setPasswordError('New passwords do not match');
      return;
    }

    setPasswordLoading(true);
    try {
      await changePassword(oldPassword, newPassword);
      setPasswordSuccess('Password changed successfully');
      setOldPassword('');
      setNewPassword('');
      setConfirmNewPassword('');
    } catch (err: unknown) {
      const detail = (err as { detail?: string }).detail ?? 'Failed to change password';
      setPasswordError(detail);
    } finally {
      setPasswordLoading(false);
    }
  }

  function formatUptime(seconds: number): string {
    const days = Math.floor(seconds / 86400);
    const hours = Math.floor((seconds % 86400) / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    if (days > 0) return `${days}d ${hours}h ${mins}m`;
    if (hours > 0) return `${hours}h ${mins}m`;
    return `${mins}m`;
  }

  return (
    <div className="flex flex-col gap-8">
      {/* -- Connectors Section ------------------------------------------------- */}
      <div className="flex flex-col gap-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-medium text-mm-text">Connectors</h2>
          <button
            onClick={() => {
              setEditingConnector(undefined);
              setFormOpen(true);
            }}
            className="flex items-center gap-1.5 border border-mm-border text-mm-text rounded-[8px] px-3 py-1.5 text-sm hover:bg-mm-surface-elevated/30 transition-colors"
          >
            <Plus size={14} />
            Add Connector
          </button>
        </div>

        {connectorError && (
          <p className="text-sm text-red-400">{connectorError}</p>
        )}

        <div className="bg-mm-surface border border-mm-border rounded-[12px] overflow-hidden">
          {connectors.length === 0 ? (
            <div className="px-5 py-8 text-center text-sm text-mm-text-muted">
              No connectors configured.
            </div>
          ) : (
            connectors.map((connector) => {
              const workerState = connector.worker?.state ?? 'disconnected';

              return (
                <div key={connector.id}>
                  <div className="flex items-center gap-3 px-5 py-3 border-b border-mm-border">
                    <div className="flex flex-col flex-1 min-w-0">
                      <span className="text-sm font-medium text-mm-text truncate">
                        {connector.label}
                      </span>
                      <span className="text-[11px] text-mm-text-muted">
                        {connector.type}
                      </span>
                    </div>
                    <span className={`text-xs font-medium ${statusColors[workerState]}`}>
                      {workerState}
                    </span>
                    <button
                      aria-label="Edit connector"
                      onClick={() => {
                        setEditingConnector(connector);
                        setFormOpen(true);
                      }}
                      className="p-1.5 rounded-[6px] text-mm-text-muted hover:text-mm-text hover:bg-mm-surface-elevated/30 transition-colors"
                    >
                      <Pencil size={14} />
                    </button>

                    {deleteConfirm === connector.id ? (
                      <div className="flex items-center gap-1">
                        <button
                          onClick={() => handleDelete(connector.id)}
                          className="text-red-400 text-xs h-7 px-2 rounded-[6px] hover:bg-red-400/10 transition-colors"
                        >
                          Confirm
                        </button>
                        <button
                          onClick={() => setDeleteConfirm(null)}
                          className="text-mm-text-muted text-xs h-7 px-2 rounded-[6px] hover:bg-mm-surface-elevated/30 transition-colors"
                        >
                          Cancel
                        </button>
                      </div>
                    ) : (
                      <button
                        aria-label="Delete connector"
                        onClick={() => setDeleteConfirm(connector.id)}
                        className="p-1.5 rounded-[6px] text-mm-text-muted hover:text-red-400 hover:bg-red-400/10 transition-colors"
                      >
                        <Trash2 size={14} />
                      </button>
                    )}
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>

      {/* -- Vault Section ------------------------------------------------------ */}
      <div className="flex flex-col gap-4">
        <h2 className="text-lg font-medium text-mm-text">Vault</h2>

        <div className="bg-mm-surface border border-mm-border rounded-[12px] p-5 flex flex-col gap-5">
          <button
            onClick={handleLockVault}
            className="flex items-center gap-2 border border-mm-border text-mm-text-secondary w-fit rounded-[8px] px-4 py-2 text-sm hover:bg-mm-surface-elevated/30 transition-colors"
          >
            <Lock size={16} />
            Lock Vault
          </button>

          <div className="border-t border-mm-border pt-5 flex flex-col gap-4">
            <h3 className="text-sm font-medium text-mm-text">Change Password</h3>

            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-medium text-mm-text-secondary">Current password</label>
              <input
                type="password"
                value={oldPassword}
                onChange={(e) => setOldPassword(e.target.value)}
                className="bg-mm-surface-elevated border border-mm-border rounded-[8px] px-3 py-2 text-sm text-mm-text outline-none focus:border-mm-gold transition-colors"
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-medium text-mm-text-secondary">New password</label>
              <input
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                className="bg-mm-surface-elevated border border-mm-border rounded-[8px] px-3 py-2 text-sm text-mm-text outline-none focus:border-mm-gold transition-colors"
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-medium text-mm-text-secondary">Confirm new password</label>
              <input
                type="password"
                value={confirmNewPassword}
                onChange={(e) => setConfirmNewPassword(e.target.value)}
                className="bg-mm-surface-elevated border border-mm-border rounded-[8px] px-3 py-2 text-sm text-mm-text outline-none focus:border-mm-gold transition-colors"
              />
            </div>

            {passwordError && (
              <p className="text-sm text-red-400">{passwordError}</p>
            )}
            {passwordSuccess && (
              <p className="text-sm text-green-400">{passwordSuccess}</p>
            )}

            <button
              onClick={handleChangePassword}
              disabled={!oldPassword || !newPassword || !confirmNewPassword || passwordLoading}
              className="bg-mm-gold text-mm-bg font-semibold w-fit px-4 py-2 rounded-[8px] text-sm disabled:opacity-50 transition-opacity"
            >
              {passwordLoading ? (
                <span className="flex items-center gap-2">
                  <span className="h-4 w-4 animate-spin rounded-full border-2 border-mm-bg border-t-transparent" />
                  Changing...
                </span>
              ) : (
                'Change Password'
              )}
            </button>
          </div>
        </div>
      </div>

      {/* -- System Section ----------------------------------------------------- */}
      <div className="flex flex-col gap-4">
        <h2 className="text-lg font-medium text-mm-text">System</h2>

        {systemLoading ? (
          <div className="flex items-center justify-center h-24">
            <div className="h-6 w-6 animate-spin rounded-full border-2 border-mm-gold border-t-transparent" />
          </div>
        ) : (
          <div className="flex flex-col gap-4">
            {/* Health Status */}
            {health && (
              <div className="bg-mm-surface border border-mm-border rounded-[12px] p-5 flex flex-col gap-3">
                <div className="flex items-center gap-2">
                  <Activity size={16} className="text-mm-gold" />
                  <h3 className="text-sm font-medium text-mm-text">Health Status</h3>
                </div>

                <div className="grid grid-cols-3 gap-4">
                  <div className="flex flex-col gap-1">
                    <span className="text-[11px] text-mm-text-muted">Status</span>
                    <span className={`text-sm font-medium ${health.status === 'ok' ? 'text-green-400' : 'text-yellow-400'}`}>
                      {health.status}
                    </span>
                  </div>
                  <div className="flex flex-col gap-1">
                    <span className="text-[11px] text-mm-text-muted">Vault</span>
                    <span className="text-sm font-medium text-mm-text">{health.vault}</span>
                  </div>
                  <div className="flex flex-col gap-1">
                    <span className="text-[11px] text-mm-text-muted">Scheduler</span>
                    <span className={`text-sm font-medium ${health.scheduler === 'running' ? 'text-green-400' : 'text-gray-400'}`}>
                      {health.scheduler}
                    </span>
                  </div>
                  <div className="flex flex-col gap-1">
                    <span className="text-[11px] text-mm-text-muted">Database</span>
                    <span className={`text-sm font-medium ${health.db === 'ok' ? 'text-green-400' : 'text-red-400'}`}>
                      {health.db}
                    </span>
                  </div>
                  <div className="flex flex-col gap-1">
                    <span className="text-[11px] text-mm-text-muted">Uptime</span>
                    <span className="text-sm font-medium text-mm-text tabular-nums">
                      {formatUptime(health.uptime_seconds)}
                    </span>
                  </div>
                </div>

                {/* Worker states */}
                {Object.keys(health.workers).length > 0 && (
                  <div className="border-t border-mm-border pt-3 flex flex-col gap-2">
                    <span className="text-[11px] text-mm-text-muted">Workers</span>
                    {Object.entries(health.workers).map(([name, state]) => (
                      <div key={name} className="flex items-center gap-2">
                        <span className="text-xs text-mm-text-secondary flex-1">{name}</span>
                        <span className={`text-xs font-medium ${statusColors[state]}`}>
                          {state}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Scheduler */}
            {scheduler && scheduler.jobs.length > 0 && (
              <div className="bg-mm-surface border border-mm-border rounded-[12px] p-5 flex flex-col gap-3">
                <div className="flex items-center gap-2">
                  <Clock size={16} className="text-mm-gold" />
                  <h3 className="text-sm font-medium text-mm-text">Scheduled Jobs</h3>
                </div>

                <div className="flex flex-col gap-2">
                  {scheduler.jobs.map((job) => (
                    <div key={job.id} className="flex items-center gap-3 py-1.5">
                      <div className="flex-1 min-w-0">
                        <span className="text-sm text-mm-text">{job.id}</span>
                        <span className="text-[11px] text-mm-text-muted ml-2">
                          ({job.schedule})
                        </span>
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                        <span className="text-xs text-mm-text-muted">
                          Next: {formatRelativeTime(job.next_run)}
                        </span>
                        {job.last_result && (
                          <span className="flex items-center gap-1">
                            {job.last_result === 'ok' ? (
                              <CheckCircle2 size={12} className="text-green-400" />
                            ) : (
                              <XCircle size={12} className="text-red-400" />
                            )}
                            <span className={`text-xs ${job.last_result === 'ok' ? 'text-green-400' : 'text-red-400'}`}>
                              {job.last_result}
                            </span>
                          </span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Connector Form Modal */}
      <ConnectorForm
        isOpen={formOpen}
        onClose={() => {
          setFormOpen(false);
          setEditingConnector(undefined);
        }}
        connectorTypes={connectorTypes}
        onSubmit={handleConnectorSubmit}
        initial={editingConnector}
      />
    </div>
  );
}
