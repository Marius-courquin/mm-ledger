import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Landmark } from 'lucide-react';
import { setupVault } from '@/api/vault';
import { useApp } from '@/context/AppContext';

export function VaultSetup() {
  const navigate = useNavigate();
  const { setVaultState } = useApp();

  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const passwordTooShort = password.length > 0 && password.length < 4;
  const mismatch = confirm.length > 0 && password !== confirm;
  const canSubmit = password.length >= 4 && password === confirm && !loading;

  async function handleSubmit() {
    setError('');
    if (!canSubmit) return;

    setLoading(true);
    try {
      await setupVault(password);
      setVaultState('unlocked');
      navigate('/', { replace: true });
    } catch (err: unknown) {
      const detail = (err as { detail?: string }).detail ?? 'Impossible de créer le coffre-fort';
      setError(detail);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex h-screen items-center justify-center bg-mm-bg">
      <div className="w-full max-w-sm flex flex-col items-center gap-8">
        <div className="flex items-center gap-2">
          <Landmark size={28} className="text-mm-gold" />
          <span className="text-2xl font-bold text-mm-gold">mm-ledger</span>
        </div>

        <div className="w-full bg-mm-surface border border-mm-border rounded-[12px] p-6 flex flex-col gap-5">
          <div className="flex flex-col gap-1 text-center">
            <h1 className="text-xl font-semibold text-mm-text">Créer votre coffre-fort</h1>
            <p className="text-sm text-mm-text-muted">
              Ce mot de passe chiffre vos identifiants bancaires
            </p>
          </div>

          <div className="flex flex-col gap-4">
            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-medium text-mm-text-secondary">Mot de passe</label>
              <input
                type="password"
                placeholder="Mot de passe coffre-fort"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') handleSubmit(); }}
                className={`bg-mm-surface-elevated border rounded-[8px] px-3 py-2.5 text-sm text-mm-text placeholder:text-mm-text-muted outline-none transition-colors ${
                  passwordTooShort ? 'border-red-400 focus:border-red-400' : 'border-mm-border focus:border-mm-gold'
                }`}
              />
              {passwordTooShort && (
                <span className="text-xs text-red-400">4 caractères minimum</span>
              )}
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-medium text-mm-text-secondary">Confirmer le mot de passe</label>
              <input
                type="password"
                placeholder="Répétez le mot de passe"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') handleSubmit(); }}
                className={`bg-mm-surface-elevated border rounded-[8px] px-3 py-2.5 text-sm text-mm-text placeholder:text-mm-text-muted outline-none transition-colors ${
                  mismatch ? 'border-red-400 focus:border-red-400' : 'border-mm-border focus:border-mm-gold'
                }`}
              />
              {mismatch && (
                <span className="text-xs text-red-400">Les mots de passe ne correspondent pas</span>
              )}
            </div>
          </div>

          {error && (
            <p className="text-sm text-red-400 text-center">{error}</p>
          )}

          <button
            onClick={handleSubmit}
            disabled={!canSubmit}
            className="bg-mm-gold text-mm-bg font-semibold w-full py-2.5 rounded-[8px] text-sm disabled:opacity-50 transition-opacity"
          >
            {loading ? (
              <span className="flex items-center justify-center gap-2">
                <span className="h-4 w-4 animate-spin rounded-full border-2 border-mm-bg border-t-transparent" />
                Création...
              </span>
            ) : (
              'Créer le coffre-fort'
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
