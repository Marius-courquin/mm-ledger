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
import { TwoFADialog } from "@/components/TwoFADialog";
import { submit2FA } from "@/api/connectors";

function AppRoutes() {
  const { vaultState, twoFARequest, setTwoFARequest, refreshConnectors } =
    useApp();

  if (vaultState === "loading") {
    return (
      <div className="flex h-screen items-center justify-center bg-mm-bg">
        <div className="text-mm-text-muted text-sm">Loading...</div>
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
              <Route path="/accounts" element={<Accounts />} />
              <Route path="/accounts/:id" element={<AccountDetail />} />
              <Route path="/settings" element={<Settings />} />
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
