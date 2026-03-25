import { useEffect, useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { getVaultStatus } from '@/api/vault';

type VaultState = 'loading' | 'uninitialized' | 'locked' | 'unlocked';

export function useVault(enabled = true) {
  const [vaultState, setVaultState] = useState<VaultState>('loading');
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    if (!enabled) return;

    let cancelled = false;

    async function checkStatus() {
      try {
        const { state } = await getVaultStatus();
        if (!cancelled) {
          setVaultState(state);
        }
      } catch {
        if (!cancelled) {
          setVaultState('locked');
        }
      }
    }

    checkStatus();

    return () => {
      cancelled = true;
    };
  }, [enabled]);

  // Redirect based on vault state
  useEffect(() => {
    if (!enabled) return;
    if (vaultState === 'loading') return;

    const path = location.pathname;

    if (vaultState === 'uninitialized' && path !== '/setup') {
      navigate('/setup', { replace: true });
    } else if (vaultState === 'locked' && path !== '/unlock') {
      navigate('/unlock', { replace: true });
    } else if (vaultState === 'unlocked' && (path === '/setup' || path === '/unlock')) {
      navigate('/', { replace: true });
    }
  }, [enabled, vaultState, location.pathname, navigate]);

  // Listen for vault-locked events dispatched by the API client on 423 responses
  useEffect(() => {
    function handleVaultLocked() {
      setVaultState('locked');
    }

    window.addEventListener('vault-locked', handleVaultLocked);
    return () => {
      window.removeEventListener('vault-locked', handleVaultLocked);
    };
  }, []);

  return {
    vaultState,
    setVaultState: setVaultState as (state: VaultState) => void,
    isLoading: vaultState === 'loading',
  };
}
