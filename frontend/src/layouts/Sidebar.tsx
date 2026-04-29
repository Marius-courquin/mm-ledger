import { NavLink, useNavigate } from 'react-router-dom';
import { Landmark, LayoutDashboard, PieChart, Wallet, Settings, Users, LogOut, ShieldCheck, User, Target, Banknote, LineChart } from 'lucide-react';
import { useApp } from '@/context/AppContext';
import { logout } from '@/api/auth';

const navItems = [
  { to: '/', label: 'Tableau de bord', icon: LayoutDashboard },
  { to: '/portfolio', label: 'Portfolio', icon: PieChart },
  { to: '/objectifs', label: 'Objectifs', icon: Target },
  { to: '/prets', label: 'Prêts', icon: Banknote },
  { to: '/projection', label: 'Projection', icon: LineChart },
  { to: '/accounts', label: 'Comptes', icon: Wallet },
  { to: '/settings', label: 'Paramètres', icon: Settings },
];

export function Sidebar() {
  const { user, setAuthState, setUser } = useApp();
  const navigate = useNavigate();

  async function handleLogout() {
    await logout();
    setAuthState('logged_out');
    setUser(null);
    navigate('/', { replace: true });
  }

  const initial = user?.username?.[0]?.toUpperCase() ?? 'U';

  return (
    <aside className="flex h-full w-[240px] flex-col bg-mm-surface border-r border-mm-border">
      {/* Logo */}
      <div className="flex items-center gap-2 px-5 py-5">
        <Landmark size={22} className="text-mm-gold" />
        <span className="text-lg font-bold text-mm-gold">mm-ledger</span>
      </div>

      {/* Navigation */}
      <nav className="flex flex-col gap-1 px-3 mt-2">
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === '/'}
            className={({ isActive }) =>
              [
                'flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition-colors',
                isActive
                  ? 'bg-mm-surface-elevated font-medium text-mm-gold'
                  : 'font-normal text-mm-text-muted hover:bg-mm-surface-elevated/50',
              ].join(' ')
            }
          >
            {({ isActive }) => (
              <>
                <item.icon
                  size={18}
                  className={isActive ? 'text-mm-gold' : 'text-mm-text-muted'}
                />
                <span>{item.label}</span>
              </>
            )}
          </NavLink>
        ))}

        {/* Admin-only link */}
        {user?.role === 'admin' && (
          <NavLink
            to="/admin/users"
            className={({ isActive }) =>
              [
                'flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition-colors',
                isActive
                  ? 'bg-mm-surface-elevated font-medium text-mm-gold'
                  : 'font-normal text-mm-text-muted hover:bg-mm-surface-elevated/50',
              ].join(' ')
            }
          >
            {({ isActive }) => (
              <>
                <Users size={18} className={isActive ? 'text-mm-gold' : 'text-mm-text-muted'} />
                <span>Gestion des utilisateurs</span>
              </>
            )}
          </NavLink>
        )}
      </nav>

      {/* Spacer */}
      <div className="flex-1" />

      {/* User section */}
      <div className="border-t border-mm-border px-4 py-4 flex flex-col gap-3">
        {/* User info */}
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-mm-lilac">
            <span className="text-[13px] font-semibold text-mm-text">{initial}</span>
          </div>
          <div className="flex flex-col min-w-0">
            <span className="text-[13px] font-medium text-mm-text truncate">
              {user?.username ?? '—'}
            </span>
            <span
              className={`inline-flex items-center gap-1 text-[11px] font-medium ${
                user?.role === 'admin' ? 'text-mm-gold' : 'text-mm-text-muted'
              }`}
            >
              {user?.role === 'admin' ? (
                <>
                  <ShieldCheck size={10} />
                  Administrateur
                </>
              ) : (
                <>
                  <User size={10} />
                  Utilisateur
                </>
              )}
            </span>
          </div>
        </div>

        {/* Logout button */}
        <button
          onClick={handleLogout}
          className="flex items-center gap-2 text-sm text-mm-text-muted hover:text-mm-text transition-colors px-1 py-1 rounded-[6px] hover:bg-mm-surface-elevated/50 w-full"
        >
          <LogOut size={15} />
          Se déconnecter
        </button>
      </div>
    </aside>
  );
}
