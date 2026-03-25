import { useState, useEffect, useCallback } from 'react';

type AuthState = 'loading' | 'no_admin' | 'logged_out' | 'logged_in';

interface AuthUser {
  id: string;
  username: string;
  role: 'admin' | 'user';
}

export function useAuth() {
  const [authState, setAuthState] = useState<AuthState>('loading');
  const [user, setUser] = useState<AuthUser | null>(null);

  const checkAuth = useCallback(async () => {
    try {
      const res = await fetch('/api/auth/status', { credentials: 'same-origin' });
      const data = await res.json();
      setAuthState(data.state);
      setUser(data.user ?? null);
    } catch {
      setAuthState('logged_out');
    }
  }, []);

  useEffect(() => { checkAuth(); }, [checkAuth]);

  return { authState, setAuthState, user, setUser, checkAuth };
}
