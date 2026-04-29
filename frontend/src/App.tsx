import { useEffect } from 'react';
import { Routes, Route, Navigate } from "react-router-dom";
import { AppProvider, useApp } from "@/context/AppContext";
import { AppLayout } from "@/layouts/AppLayout";
import { VaultSetup } from "@/pages/VaultSetup";
import { VaultUnlock } from "@/pages/VaultUnlock";
import { Dashboard } from "@/pages/Dashboard";
import { Portfolio } from "@/pages/Portfolio";
import { Accounts } from "@/pages/Accounts";
import { AccountDetail } from "@/pages/AccountDetail";
import { Settings } from "@/pages/Settings";
import { Objectifs } from "@/pages/Objectifs";
import { ObjectifDetail } from "@/pages/ObjectifDetail";
import { Prets } from "@/pages/Prets";
import { Projection } from "@/pages/Projection";
import { Budget } from "@/pages/Budget";
import { Login } from "@/pages/Login";
import { AdminSetup } from "@/pages/AdminSetup";
import { AdminUsers } from "@/pages/AdminUsers";
import { TwoFADialog } from "@/components/TwoFADialog";
import { submit2FA } from "@/api/connectors";
import { getAuthStatus } from "@/api/auth";

function AppRoutes() {
  const {
    authState, setAuthState, setUser,
    vaultState,
    twoFARequest, setTwoFARequest, refreshConnectors,
  } = useApp();

  // Check auth status on mount
  useEffect(() => {
    async function check() {
      try {
        const data = await getAuthStatus();
        setAuthState(data.state);
        setUser(data.user ?? null);
      } catch {
        setAuthState('logged_out');
      }
    }
    check();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Auth loading spinner
  if (authState === 'loading') {
    return (
      <div className="flex h-screen items-center justify-center bg-mm-bg">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-mm-gold border-t-transparent" />
      </div>
    );
  }

  // No admin yet — first launch
  if (authState === 'no_admin') {
    return (
      <AdminSetup
        onSetup={() => {
          setAuthState('logged_in');
        }}
      />
    );
  }

  // Not logged in
  if (authState === 'logged_out') {
    return (
      <Login
        onLogin={async () => {
          const data = await getAuthStatus();
          setAuthState(data.state);
          setUser(data.user ?? null);
        }}
      />
    );
  }

  // Logged in — check vault state
  if (vaultState === 'loading') {
    return (
      <div className="flex h-screen items-center justify-center bg-mm-bg">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-mm-gold border-t-transparent" />
      </div>
    );
  }

  return (
    <>
      <Routes>
        {vaultState === "uninitialized" && (
          <>
            <Route path="/setup" element={<VaultSetup />} />
            <Route path="*" element={<Navigate to="/setup" replace />} />
          </>
        )}
        {vaultState === "locked" && (
          <>
            <Route path="/unlock" element={<VaultUnlock />} />
            <Route path="*" element={<Navigate to="/unlock" replace />} />
          </>
        )}
        {vaultState === "unlocked" && (
          <>
            <Route element={<AppLayout />}>
              <Route path="/" element={<Dashboard />} />
              <Route path="/portfolio" element={<Portfolio />} />
              <Route path="/objectifs" element={<Objectifs />} />
              <Route path="/objectifs/:id" element={<ObjectifDetail />} />
              <Route path="/prets" element={<Prets />} />
              <Route path="/projection" element={<Projection />} />
              <Route path="/budget" element={<Budget />} />
              <Route path="/accounts" element={<Accounts />} />
              <Route path="/accounts/:id" element={<AccountDetail />} />
              <Route path="/settings" element={<Settings />} />
              <Route path="/admin/users" element={<AdminUsers />} />
            </Route>
            <Route path="/setup" element={<Navigate to="/" replace />} />
            <Route path="/unlock" element={<Navigate to="/" replace />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </>
        )}
      </Routes>

      {twoFARequest && (
        <TwoFADialog
          connectorId={twoFARequest.connectorId}
          detail={twoFARequest.detail}
          method={twoFARequest.method}
          onSubmit={async (code) => {
            await submit2FA(twoFARequest.connectorId, code);
            setTwoFARequest(null);
            refreshConnectors();
          }}
          onClose={() => setTwoFARequest(null)}
        />
      )}
    </>
  );
}

export function App() {
  return (
    <AppProvider>
      <AppRoutes />
    </AppProvider>
  );
}
