import { useState, useEffect, useCallback } from 'react';
import { UserPlus, Trash2, KeyRound, ShieldCheck, User } from 'lucide-react';
import { getUsers, createUser, deleteUser, resetPassword } from '@/api/auth';

interface AppUser {
  id: string;
  username: string;
  role: 'admin' | 'user';
  created_at: string;
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString('fr-FR', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  });
}

export function AdminUsers() {
  const [users, setUsers] = useState<AppUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  // Create user form
  const [showCreate, setShowCreate] = useState(false);
  const [newUsername, setNewUsername] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [newRole, setNewRole] = useState<'admin' | 'user'>('user');
  const [createError, setCreateError] = useState('');
  const [createLoading, setCreateLoading] = useState(false);

  // Reset password form
  const [resetId, setResetId] = useState<string | null>(null);
  const [resetPwd, setResetPwd] = useState('');
  const [resetError, setResetError] = useState('');
  const [resetLoading, setResetLoading] = useState(false);

  // Delete confirm
  const [deleteId, setDeleteId] = useState<string | null>(null);
  const [deleteLoading, setDeleteLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const data = await getUsers();
      setUsers(data);
    } catch {
      setError('Impossible de charger les utilisateurs');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  async function handleCreate() {
    setCreateError('');
    if (!newUsername.trim() || newPassword.length < 4) return;
    setCreateLoading(true);
    try {
      await createUser(newUsername.trim(), newPassword, newRole);
      setShowCreate(false);
      setNewUsername('');
      setNewPassword('');
      setNewRole('user');
      await load();
    } catch (err: unknown) {
      setCreateError((err as Error).message || 'Erreur lors de la création');
    } finally {
      setCreateLoading(false);
    }
  }

  async function handleDelete(id: string) {
    setDeleteLoading(true);
    try {
      await deleteUser(id);
      setDeleteId(null);
      await load();
    } catch {
      // ignore
    } finally {
      setDeleteLoading(false);
    }
  }

  async function handleResetPassword() {
    if (!resetId || resetPwd.length < 4) return;
    setResetError('');
    setResetLoading(true);
    try {
      await resetPassword(resetId, resetPwd);
      setResetId(null);
      setResetPwd('');
    } catch (err: unknown) {
      setResetError((err as Error).message || 'Erreur');
    } finally {
      setResetLoading(false);
    }
  }

  return (
    <div className="flex flex-col gap-6 p-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-mm-text">Gestion des utilisateurs</h1>
          <p className="text-sm text-mm-text-muted mt-0.5">
            Gérez les comptes ayant accès à mm-ledger
          </p>
        </div>
        <button
          onClick={() => { setShowCreate(true); setCreateError(''); }}
          className="flex items-center gap-2 bg-mm-gold text-mm-bg font-semibold px-4 py-2 rounded-[8px] text-sm hover:opacity-90 transition-opacity"
        >
          <UserPlus size={16} />
          Ajouter un utilisateur
        </button>
      </div>

      {error && (
        <p className="text-sm text-red-400">{error}</p>
      )}

      {/* Table */}
      <div className="bg-mm-surface border border-mm-border rounded-[12px] overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <div className="h-6 w-6 animate-spin rounded-full border-2 border-mm-gold border-t-transparent" />
          </div>
        ) : users.length === 0 ? (
          <div className="py-12 text-center text-sm text-mm-text-muted">
            Aucun utilisateur
          </div>
        ) : (
          <table className="w-full">
            <thead>
              <tr className="border-b border-mm-border">
                <th className="text-left text-xs font-medium text-mm-text-muted px-5 py-3">
                  Utilisateur
                </th>
                <th className="text-left text-xs font-medium text-mm-text-muted px-5 py-3">
                  Rôle
                </th>
                <th className="text-left text-xs font-medium text-mm-text-muted px-5 py-3">
                  Créé le
                </th>
                <th className="px-5 py-3" />
              </tr>
            </thead>
            <tbody>
              {users.map((u, i) => (
                <tr
                  key={u.id}
                  className={i < users.length - 1 ? 'border-b border-mm-border' : ''}
                >
                  <td className="px-5 py-3.5">
                    <div className="flex items-center gap-2.5">
                      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-mm-surface-elevated">
                        <span className="text-xs font-semibold text-mm-text">
                          {u.username[0]?.toUpperCase() ?? '?'}
                        </span>
                      </div>
                      <span className="text-sm font-medium text-mm-text">{u.username}</span>
                    </div>
                  </td>
                  <td className="px-5 py-3.5">
                    <span
                      className={`inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full ${
                        u.role === 'admin'
                          ? 'bg-mm-gold/15 text-mm-gold'
                          : 'bg-mm-surface-elevated text-mm-text-muted'
                      }`}
                    >
                      {u.role === 'admin' ? (
                        <ShieldCheck size={11} />
                      ) : (
                        <User size={11} />
                      )}
                      {u.role === 'admin' ? 'Administrateur' : 'Utilisateur'}
                    </span>
                  </td>
                  <td className="px-5 py-3.5 text-sm text-mm-text-muted">
                    {formatDate(u.created_at)}
                  </td>
                  <td className="px-5 py-3.5">
                    <div className="flex items-center justify-end gap-2">
                      <button
                        onClick={() => { setResetId(u.id); setResetPwd(''); setResetError(''); }}
                        className="flex items-center gap-1.5 text-xs text-mm-text-muted hover:text-mm-text transition-colors px-2 py-1.5 rounded-[6px] hover:bg-mm-surface-elevated"
                        title="Réinitialiser le mot de passe"
                      >
                        <KeyRound size={13} />
                        Réinit. MDP
                      </button>
                      <button
                        onClick={() => setDeleteId(u.id)}
                        className="flex items-center gap-1.5 text-xs text-red-400/70 hover:text-red-400 transition-colors px-2 py-1.5 rounded-[6px] hover:bg-red-400/10"
                        title="Supprimer l'utilisateur"
                      >
                        <Trash2 size={13} />
                        Supprimer
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Create user modal */}
      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="w-full max-w-sm bg-mm-surface border border-mm-border rounded-[12px] p-6 flex flex-col gap-5 mx-4">
            <h2 className="text-base font-semibold text-mm-text">Ajouter un utilisateur</h2>

            <div className="flex flex-col gap-4">
              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-medium text-mm-text-secondary">
                  Nom d'utilisateur
                </label>
                <input
                  type="text"
                  placeholder="Nom d'utilisateur"
                  value={newUsername}
                  onChange={(e) => setNewUsername(e.target.value)}
                  autoComplete="off"
                  className="bg-mm-surface-elevated border border-mm-border rounded-[8px] px-3 py-2.5 text-sm text-mm-text placeholder:text-mm-text-muted outline-none focus:border-mm-gold transition-colors"
                />
              </div>

              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-medium text-mm-text-secondary">
                  Mot de passe
                </label>
                <input
                  type="password"
                  placeholder="Mot de passe"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  autoComplete="new-password"
                  className="bg-mm-surface-elevated border border-mm-border rounded-[8px] px-3 py-2.5 text-sm text-mm-text placeholder:text-mm-text-muted outline-none focus:border-mm-gold transition-colors"
                />
              </div>

              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-medium text-mm-text-secondary">Rôle</label>
                <select
                  value={newRole}
                  onChange={(e) => setNewRole(e.target.value as 'admin' | 'user')}
                  className="bg-mm-surface-elevated border border-mm-border rounded-[8px] px-3 py-2.5 text-sm text-mm-text outline-none focus:border-mm-gold transition-colors"
                >
                  <option value="user">Utilisateur</option>
                  <option value="admin">Administrateur</option>
                </select>
              </div>
            </div>

            {createError && (
              <p className="text-sm text-red-400">{createError}</p>
            )}

            <div className="flex gap-3">
              <button
                onClick={() => { setShowCreate(false); setCreateError(''); }}
                className="flex-1 border border-mm-border text-mm-text-muted text-sm py-2.5 rounded-[8px] hover:bg-mm-surface-elevated transition-colors"
              >
                Annuler
              </button>
              <button
                onClick={handleCreate}
                disabled={!newUsername.trim() || newPassword.length < 4 || createLoading}
                className="flex-1 bg-mm-gold text-mm-bg font-semibold text-sm py-2.5 rounded-[8px] disabled:opacity-50 hover:opacity-90 transition-opacity"
              >
                {createLoading ? (
                  <span className="flex items-center justify-center gap-2">
                    <span className="h-4 w-4 animate-spin rounded-full border-2 border-mm-bg border-t-transparent" />
                    Création...
                  </span>
                ) : (
                  'Créer'
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Reset password modal */}
      {resetId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="w-full max-w-sm bg-mm-surface border border-mm-border rounded-[12px] p-6 flex flex-col gap-5 mx-4">
            <h2 className="text-base font-semibold text-mm-text">
              Réinitialiser le mot de passe
            </h2>

            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-medium text-mm-text-secondary">
                Nouveau mot de passe
              </label>
              <input
                type="password"
                placeholder="Nouveau mot de passe"
                value={resetPwd}
                onChange={(e) => setResetPwd(e.target.value)}
                autoComplete="new-password"
                className="bg-mm-surface-elevated border border-mm-border rounded-[8px] px-3 py-2.5 text-sm text-mm-text placeholder:text-mm-text-muted outline-none focus:border-mm-gold transition-colors"
              />
            </div>

            {resetError && (
              <p className="text-sm text-red-400">{resetError}</p>
            )}

            <div className="flex gap-3">
              <button
                onClick={() => { setResetId(null); setResetPwd(''); setResetError(''); }}
                className="flex-1 border border-mm-border text-mm-text-muted text-sm py-2.5 rounded-[8px] hover:bg-mm-surface-elevated transition-colors"
              >
                Annuler
              </button>
              <button
                onClick={handleResetPassword}
                disabled={resetPwd.length < 4 || resetLoading}
                className="flex-1 bg-mm-gold text-mm-bg font-semibold text-sm py-2.5 rounded-[8px] disabled:opacity-50 hover:opacity-90 transition-opacity"
              >
                {resetLoading ? (
                  <span className="flex items-center justify-center gap-2">
                    <span className="h-4 w-4 animate-spin rounded-full border-2 border-mm-bg border-t-transparent" />
                    Enregistrement...
                  </span>
                ) : (
                  'Enregistrer'
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Delete confirm modal */}
      {deleteId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="w-full max-w-sm bg-mm-surface border border-mm-border rounded-[12px] p-6 flex flex-col gap-5 mx-4">
            <div>
              <h2 className="text-base font-semibold text-mm-text">Supprimer l'utilisateur</h2>
              <p className="text-sm text-mm-text-muted mt-1">
                Cette action est irréversible.
              </p>
            </div>

            <div className="flex gap-3">
              <button
                onClick={() => setDeleteId(null)}
                className="flex-1 border border-mm-border text-mm-text-muted text-sm py-2.5 rounded-[8px] hover:bg-mm-surface-elevated transition-colors"
              >
                Annuler
              </button>
              <button
                onClick={() => handleDelete(deleteId)}
                disabled={deleteLoading}
                className="flex-1 bg-red-500 text-white font-semibold text-sm py-2.5 rounded-[8px] disabled:opacity-50 hover:opacity-90 transition-opacity"
              >
                {deleteLoading ? (
                  <span className="flex items-center justify-center gap-2">
                    <span className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
                    Suppression...
                  </span>
                ) : (
                  'Supprimer'
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
