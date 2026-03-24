import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Landmark } from 'lucide-react';
import { unlockVault } from '@/api/vault';
import { useApp } from '@/context/AppContext';

export function VaultUnlock() {
  const navigate = useNavigate();
  const { setVaultState } = useApp();

  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function handleSubmit() {
    if (!password || loading) return;
    setError('');
    setLoading(true);

    try {
      await unlockVault(password);
      setVaultState('unlocked');
      navigate('/', { replace: true });
    } catch (err: unknown) {
      const apiErr = err as { status?: number; detail?: string };
      if (apiErr.status === 401) {
        setError('Wrong password. Please try again.');
      } else if (apiErr.status === 429) {
        setError('Too many attempts. Please wait a moment before retrying.');
      } else {
        setError(apiErr.detail ?? 'Failed to unlock vault');
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex h-screen items-center justify-center bg-mm-bg">
      <div className="w-full max-w-sm flex flex-col items-center gap-8">
        {/* Logo */}
        <div className="flex items-center gap-2">
          <Landmark size={28} className="text-mm-gold" />
          <span className="text-2xl font-bold text-mm-gold">mm-ledger</span>
        </div>

        {/* Card */}
        <div className="w-full bg-mm-surface border border-mm-border rounded-[12px] p-6 flex flex-col gap-5">
          <div className="flex flex-col gap-1 text-center">
            <h1 className="text-xl font-semibold text-mm-text">Welcome back</h1>
            <p className="text-sm text-mm-text-muted">
              Enter your master password to continue
            </p>
          </div>

          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-medium text-mm-text-secondary">Password</label>
            <input
              type="password"
              placeholder="Master password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleSubmit();
              }}
              autoFocus
              className="bg-mm-surface-elevated border border-mm-border rounded-[8px] px-3 py-2.5 text-sm text-mm-text placeholder:text-mm-text-muted outline-none focus:border-mm-gold transition-colors"
            />
          </div>

          {error && (
            <p className="text-sm text-red-400 text-center">{error}</p>
          )}

          <button
            onClick={handleSubmit}
            disabled={!password || loading}
            className="bg-mm-gold text-mm-bg font-semibold w-full py-2.5 rounded-[8px] text-sm disabled:opacity-50 transition-opacity"
          >
            {loading ? (
              <span className="flex items-center justify-center gap-2">
                <span className="h-4 w-4 animate-spin rounded-full border-2 border-mm-bg border-t-transparent" />
                Unlocking...
              </span>
            ) : (
              'Unlock'
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
