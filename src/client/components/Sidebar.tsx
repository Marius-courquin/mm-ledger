import React from "react";
import { NavLink } from "react-router-dom";
import {
  Landmark,
  LayoutDashboard,
  PieChart,
  Wallet,
  Settings,
} from "lucide-react";
import { theme } from "../theme";

interface NavItem {
  to: string;
  label: string;
  icon: React.ReactNode;
}

const navItems: NavItem[] = [
  { to: "/", label: "Dashboard", icon: <LayoutDashboard size={20} /> },
  { to: "/portfolio", label: "Portfolio", icon: <PieChart size={20} /> },
  { to: "/accounts", label: "Accounts", icon: <Wallet size={20} /> },
  { to: "/settings", label: "Settings", icon: <Settings size={20} /> },
];

const Sidebar: React.FC = () => {
  return (
    <aside
      style={{
        width: 260,
        minWidth: 260,
        height: "100vh",
        background: theme.colors.surface,
        borderRight: `1px solid ${theme.colors.border}`,
        display: "flex",
        flexDirection: "column",
        padding: `${theme.spacing.lg}px 0`,
      }}
    >
      {/* Logo */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: theme.spacing.sm,
          padding: `0 ${theme.spacing.lg}px`,
          marginBottom: theme.spacing["2xl"],
        }}
      >
        <Landmark size={24} color={theme.colors.accentGold} />
        <span
          style={{
            fontSize: 18,
            fontWeight: 700,
            color: theme.colors.accentGold,
            letterSpacing: "-0.02em",
          }}
        >
          mm-ledger
        </span>
      </div>

      {/* Navigation */}
      <nav style={{ flex: 1, display: "flex", flexDirection: "column", gap: 2 }}>
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === "/"}
            style={({ isActive }) => ({
              display: "flex",
              alignItems: "center",
              gap: theme.spacing.sm,
              padding: `${theme.spacing.sm + 2}px ${theme.spacing.lg}px`,
              margin: `0 ${theme.spacing.sm}px`,
              borderRadius: theme.radius.md,
              fontSize: 14,
              fontWeight: isActive ? 600 : 400,
              color: isActive
                ? theme.colors.accentGold
                : theme.colors.textSecondary,
              background: isActive ? theme.colors.surfaceElevated : "transparent",
              transition: "all 0.15s ease",
              textDecoration: "none",
            })}
          >
            {item.icon}
            {item.label}
          </NavLink>
        ))}
      </nav>

      {/* User section */}
      <div
        style={{
          padding: `${theme.spacing.md}px ${theme.spacing.lg}px`,
          borderTop: `1px solid ${theme.colors.border}`,
          display: "flex",
          alignItems: "center",
          gap: theme.spacing.sm,
        }}
      >
        <div
          style={{
            width: 36,
            height: 36,
            borderRadius: "50%",
            background: `linear-gradient(135deg, ${theme.colors.accentLilac}, ${theme.colors.accentLavender})`,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: 13,
            fontWeight: 700,
            color: theme.colors.textPrimary,
            flexShrink: 0,
          }}
        >
          MM
        </div>
        <div style={{ minWidth: 0 }}>
          <div
            style={{
              fontSize: 13,
              fontWeight: 600,
              color: theme.colors.textPrimary,
              whiteSpace: "nowrap",
              overflow: "hidden",
              textOverflow: "ellipsis",
            }}
          >
            Marius & Magni
          </div>
          <div
            style={{
              fontSize: 11,
              color: theme.colors.textMuted,
            }}
          >
            Pro Account
          </div>
        </div>
      </div>
    </aside>
  );
};

export default Sidebar;
