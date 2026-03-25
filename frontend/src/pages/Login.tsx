import { useState } from 'react';
import { Landmark } from 'lucide-react';
import { login } from '@/api/auth';

interface LoginProps {
  onLogin: () => void;
}

export function Login({ onLogin }: LoginProps) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const canSubmit = username.trim().length > 0 && password.length > 0 && !loading;

  async function handleSubmit() {
    setError('');
    if (!canSubmit) return;

    setLoading(true);
    try {
      await login(username.trim(), password);
      onLogin();
    } catch (err: unknown) {
      setError((err as Error).message || 'Erreur de connexion');
    } finally {
      setLoading(false);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Enter') handleSubmit();
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
            <h1 className="text-xl font-semibold text-mm-text">Connexion</h1>
            <p className="text-sm text-mm-text-muted">
              Connectez-vous à votre compte
            </p>
          </div>

          <div className="flex flex-col gap-4">
            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-medium text-mm-text-secondary">
                Nom d'utilisateur
              </label>
              <input
                type="text"
                placeholder="Nom d'utilisateur"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                onKeyDown={handleKeyDown}
                autoComplete="username"
                className="bg-mm-surface-elevated border border-mm-border rounded-[8px] px-3 py-2.5 text-sm text-mm-text placeholder:text-mm-text-muted outline-none transition-colors focus:border-mm-gold"
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-medium text-mm-text-secondary">
                Mot de passe
              </label>
              <input
                type="password"
                placeholder="Mot de passe"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                onKeyDown={handleKeyDown}
                autoComplete="current-password"
                className="bg-mm-surface-elevated border border-mm-border rounded-[8px] px-3 py-2.5 text-sm text-mm-text placeholder:text-mm-text-muted outline-none transition-colors focus:border-mm-gold"
              />
            </div>
          </div>

          {error && (
            <p className="text-sm text-red-400 text-center">{error}</p>
          )}

          <button
            onClick={handleSubmit}
            disabled={!canSubmit}
            className="bg-mm-gold text-mm-bg font-semibold w-full py-2.5 rounded-[8px] text-sm disabled:opacity-50 transition-opacity hover:opacity-90"
          >
            {loading ? (
              <span className="flex items-center justify-center gap-2">
                <span className="h-4 w-4 animate-spin rounded-full border-2 border-mm-bg border-t-transparent" />
                Connexion...
              </span>
            ) : (
              'Se connecter'
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
