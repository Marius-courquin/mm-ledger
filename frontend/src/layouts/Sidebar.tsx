import { NavLink } from 'react-router-dom';
import { Landmark, LayoutDashboard, PieChart, Wallet, Settings } from 'lucide-react';

const navItems = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/portfolio', label: 'Portfolio', icon: PieChart },
  { to: '/accounts', label: 'Accounts', icon: Wallet },
  { to: '/settings', label: 'Settings', icon: Settings },
];

export function Sidebar() {
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
      </nav>

      {/* Spacer */}
      <div className="flex-1" />

      {/* User section */}
      <div className="border-t border-mm-border px-5 py-4 flex items-center gap-3">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-mm-lilac">
          <span className="text-[13px] font-semibold text-mm-text">MM</span>
        </div>
        <div className="flex flex-col">
          <span className="text-[13px] font-medium text-mm-text">Marius &amp; Magni</span>
          <span className="text-[11px] text-mm-text-muted">Pro Account</span>
        </div>
      </div>
    </aside>
  );
}
