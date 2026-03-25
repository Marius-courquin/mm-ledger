import React, { createContext, useContext, useState, useCallback } from 'react';
import { useVault } from '@/hooks/useVault';
import { useConnectors } from '@/hooks/useConnectors';
import { useSSE } from '@/hooks/useSSE';
import type { Connector } from '@/lib/types';

type VaultState = 'loading' | 'uninitialized' | 'locked' | 'unlocked';

type TwoFARequest = {
  connectorId: string;
  detail: string;
  method: 'sms' | 'app';
} | null;

type AuthState = 'loading' | 'no_admin' | 'logged_out' | 'logged_in';

interface AuthUser {
  id: string;
  username: string;
  role: 'admin' | 'user';
}

interface AppContextType {
  vaultState: VaultState;
  setVaultState: (state: VaultState) => void;
  connectors: Connector[];
  updateConnectorState: (id: string, state: string, detail?: string) => void;
  refreshConnectors: () => void;
  twoFARequest: TwoFARequest;
  setTwoFARequest: (req: TwoFARequest) => void;
  authState: AuthState;
  setAuthState: (state: AuthState) => void;
  user: AuthUser | null;
  setUser: (user: AuthUser | null) => void;
}

const AppContext = createContext<AppContextType | null>(null);

export function AppProvider({ children }: { children: React.ReactNode }) {
  const [authState, setAuthState] = useState<AuthState>('loading');
  const [user, setUser] = useState<AuthUser | null>(null);

  const loggedIn = authState === 'logged_in';
  const { vaultState, setVaultState, isLoading } = useVault(loggedIn);
  const vaultUnlocked = vaultState === 'unlocked';
  const { connectors, updateConnectorState, refreshConnectors } = useConnectors(vaultUnlocked);
  const [twoFARequest, setTwoFARequest] = useState<TwoFARequest>(null);

  const handleWorkerStatus = useCallback(
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (data: any) => {
      const connectorId: string | undefined = data.connector_id ?? data.connectorId ?? data.id;
      const state: string = data.state;
      const detail: string | undefined = data.detail;

      if (!connectorId) {
        console.warn('[SSE] worker_status event missing connector_id:', data);
        return;
      }

      updateConnectorState(connectorId, state, detail);

      if (state === 'waiting_2fa') {
        const method = data.method ?? 'sms';
        setTwoFARequest({ connectorId, detail: detail ?? 'Vérification requise', method });
      }
    },
    [updateConnectorState],
  );

  useSSE(vaultUnlocked, {
    onWorkerStatus: handleWorkerStatus,
  });

  if (isLoading && loggedIn) {
    return (
      <div className="flex h-screen items-center justify-center bg-mm-bg">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-mm-gold border-t-transparent" />
      </div>
    );
  }

  return (
    <AppContext.Provider
      value={{
        vaultState,
        setVaultState,
        connectors,
        updateConnectorState,
        refreshConnectors,
        twoFARequest,
        setTwoFARequest,
        authState,
        setAuthState,
        user,
        setUser,
      }}
    >
      {children}
    </AppContext.Provider>
  );
}

export function useApp() {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error('useApp must be used within AppProvider');
  return ctx;
}
