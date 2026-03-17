import React, { useState, useEffect } from "react";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { Wallet, Trophy, TrendingUp, Loader2 } from "lucide-react";
import { theme } from "../theme";

// ── Types ───────────────────────────────────────────────────────────────────────

interface CashEntry {
  accountNumber: string;
  currencyId: string;
  amount: number;
  label: string;
  secAccNo: string | null;
}

interface Account {
  securitiesAccountNumber: string;
  cashAccountNumber: string;
  productType: string;
  label: string;
  currency: string;
}

interface Position {
  name: string;
  isin: string;
  netSize: string;
  averageBuyIn: string;
  instrumentType: string;
  derivativeInfo?: { underlying: { shortName: string } } | null;
}

interface PortfolioEntry {
  label: string;
  secAccNo: string;
  categories: { categoryType: string; positions: Position[] }[];
}

// ── Helpers ────────────────────────────────────────────────────────────────────

function getGreeting(): string {
  const h = new Date().getHours();
  if (h < 12) return "Good morning";
  if (h < 18) return "Good afternoon";
  return "Good evening";
}

function formatDate(): string {
  return new Date().toLocaleDateString("en-US", {
    weekday: "long",
    year: "numeric",
    month: "long",
    day: "numeric",
  });
}

function fmt(n: number | undefined | null): string {
  if (n == null || isNaN(n)) return "0,00";
  return n.toLocaleString("fr-FR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

// ── Styles ─────────────────────────────────────────────────────────────────────

const card: React.CSSProperties = {
  background: theme.colors.surface,
  border: `1px solid ${theme.colors.border}`,
  borderRadius: theme.radius.lg,
  padding: theme.spacing.lg,
};

// ── Component ──────────────────────────────────────────────────────────────────

// (periods removed — charts are now per-section)

interface HistoryEntry {
  name: string;
  categoryType: string;
  accountLabel: string;
  netSize: string;
  averageBuyIn: string;
  history: { time: number; open: number; close: number; high: number; low: number }[];
}

const Dashboard: React.FC = () => {
  const [cash, setCash] = useState<CashEntry[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [portfolios, setPortfolios] = useState<PortfolioEntry[]>([]);
  const [sectionCharts, setSectionCharts] = useState<Record<string, { date: string; value: number }[]>>({});
  const [expandedSections, setExpandedSections] = useState<Record<string, boolean>>({});
  const [prices, setPrices] = useState<Record<string, number>>({});
  const [bpAccounts, setBpAccounts] = useState<{ id: string; label: string; balance: number; currency: string }[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const toggleSection = (name: string) =>
    setExpandedSections((prev) => ({ ...prev, [name]: !prev[name] }));

  // Load portfolio data
  useEffect(() => {
    async function load() {
      try {
        const [cashRes, accountsRes, portfolioRes] = await Promise.all([
          fetch("/api/cash"),
          fetch("/api/accounts"),
          fetch("/api/portfolio"),
        ]);

        if (!cashRes.ok || !accountsRes.ok || !portfolioRes.ok) {
          setError("Backend not connected. Start the server and configure Trade Republic in Settings.");
          setLoading(false);
          return;
        }

        setCash(await cashRes.json());
        setAccounts((await accountsRes.json()).accounts);
        setPortfolios(await portfolioRes.json());

        // Load BP accounts (non-blocking)
        fetch("/api/bp/accounts")
          .then(r => r.ok ? r.json() : null)
          .then(data => { if (data?.accounts) setBpAccounts(data.accounts); })
          .catch(() => {});

        // Load live prices
        const pricesRes = await fetch("/api/prices");
        if (pricesRes.ok) {
          const pricesData = await pricesRes.json();
          const priceMap: Record<string, number> = {};
          for (const p of pricesData) {
            if (p.price != null) {
              priceMap[p.isin] = parseFloat(p.price);
            }
          }
          setPrices(priceMap);
        }

        // Load history for per-section charts
        const histRes = await fetch("/api/history?range=max");
        if (histRes.ok) {
          const histData: HistoryEntry[] = await histRes.json();
          // Group by section and aggregate values over time
          const SECTION_MAP: Record<string, string> = {
            stocksAndETFs: "CTO",
            cryptos: "Crypto",
            privateMarkets: "Private Equity",
          };

          const bySection: Record<string, HistoryEntry[]> = {};
          for (const entry of histData) {
            const section =
              entry.accountLabel === "PEA" ? "PEA" : SECTION_MAP[entry.categoryType] ?? entry.accountLabel;
            (bySection[section] ??= []).push(entry);
          }

          // For each section, build a time series of total value
          const charts: Record<string, { date: string; value: number }[]> = {};
          for (const [section, entries] of Object.entries(bySection)) {
            // Collect all timestamps across entries
            const timeMap = new Map<number, number>();
            for (const entry of entries) {
              const qty = parseFloat(entry.netSize) || 0;
              const aggs = Array.isArray(entry.history) ? entry.history : [];
              for (const pt of aggs) {
                const t = pt.time;
                const close = typeof pt.close === "string" ? parseFloat(pt.close) : (pt.close ?? 0);
                const val = close * qty;
                timeMap.set(t, (timeMap.get(t) || 0) + val);
              }
            }
            if (timeMap.size === 0) continue;

            const sorted = [...timeMap.entries()].sort((a, b) => a[0] - b[0]);
            // Timestamps are in milliseconds
            charts[section] = sorted.map(([t, v]) => ({
              date: new Date(t).toLocaleDateString("fr-FR", { day: "2-digit", month: "short" }),
              value: v,
            }));
          }
          setSectionCharts(charts);

          // P&L charts removed — not meaningful without transaction history
        }
      } catch {
        setError("Cannot reach backend. Run: bun run server");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  // (charts are loaded per-section in the main useEffect)

  const totalCash = cash.reduce((sum, c) => sum + c.amount, 0) + bpAccounts.reduce((sum, a) => sum + a.balance, 0);
  // Helper to get current value of a position
  const posValue = (pos: Position) => {
    const qty = parseFloat(pos.netSize) || 0;
    const isin = (pos as any).isin;
    const livePrice = isin ? prices[isin] : undefined;
    const price = livePrice ?? (parseFloat(pos.averageBuyIn) || 0);
    return qty * price;
  };

  const totalPositions = portfolios.reduce((sum, p) => {
    return (
      sum +
      (p.categories || []).reduce(
        (catSum, cat) =>
          catSum + cat.positions.reduce((posSum, pos) => posSum + posValue(pos), 0),
        0
      )
    );
  }, 0);
  const totalBalance = totalCash + totalPositions;

  // Group positions into logical sections
  const CATEGORY_SECTIONS: Record<string, string> = {
    stocks: "CTO",
    etfs: "CTO",
    bonds: "CTO",
    cryptos: "Crypto",
    privateMarkets: "Private Equity",
  };

  type DisplayPosition = Position & { displayName: string; section: string; accountLabel: string };

  const allPositions: DisplayPosition[] = portfolios.flatMap((p) =>
    (p.categories || []).flatMap((cat) =>
      cat.positions.map((pos) => {
        // PEA keeps its own label, CTO categories get split
        const section =
          p.label === "PEA"
            ? "PEA"
            : CATEGORY_SECTIONS[cat.categoryType] ?? p.label;
        return {
          ...pos,
          accountLabel: p.label,
          section,
          displayName: pos.derivativeInfo?.underlying?.shortName || pos.name,
        };
      })
    )
  );

  // Group by section
  const sections = allPositions.reduce<Record<string, DisplayPosition[]>>((acc, pos) => {
    (acc[pos.section] ??= []).push(pos);
    return acc;
  }, {});

  // Ordered display
  const sectionOrder = ["CTO", "PEA", "Crypto", "Private Equity"];
  const orderedSections = [
    ...sectionOrder.filter((s) => sections[s]),
    ...Object.keys(sections).filter((s) => !sectionOrder.includes(s)),
  ];

  const metrics = [
    {
      label: "Total Balance",
      value: `€${fmt(totalBalance)}`,
      sub: `${accounts.length} account${accounts.length > 1 ? "s" : ""}`,
      color: theme.colors.accentGold,
      icon: <Wallet size={18} />,
      highlight: true,
    },
    {
      label: "Total Cash",
      value: `€${fmt(totalCash)}`,
      sub: "Available liquidity",
      color: theme.colors.gain,
      icon: <TrendingUp size={18} />,
    },
    {
      label: "Total Accounts",
      value: `${accounts.length}`,
      sub: "Trade Republic",
      color: theme.colors.textPrimary,
      icon: <Wallet size={18} />,
    },
    (() => {
      // Find best performer by P&L%
      let bestName = "—";
      let bestPct = 0;
      for (const pos of allPositions) {
        const qty = parseFloat(pos.netSize) || 0;
        const avg = parseFloat(pos.averageBuyIn) || 0;
        const live = prices[pos.isin];
        if (live && avg > 0 && qty > 0) {
          const pct = ((live - avg) / avg) * 100;
          if (pct > bestPct) {
            bestPct = pct;
            bestName = pos.displayName;
          }
        }
      }
      return {
        label: "Best Performer",
        value: bestName,
        sub: bestPct > 0 ? `+${bestPct.toFixed(1)}%` : `${allPositions.length} positions`,
        color: theme.colors.accentGold,
        icon: <Trophy size={18} />,
      };
    })(),
  ];

  if (loading) {
    return (
      <div style={{ display: "flex", alignItems: "center", gap: 12, padding: 48, color: theme.colors.textMuted }}>
        <Loader2 size={20} style={{ animation: "spin 1s linear infinite" }} />
        Loading...
        <style>{`@keyframes spin { to { transform: rotate(360deg) } }`}</style>
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ padding: 48 }}>
        <div style={{ ...card, color: theme.colors.loss, fontSize: 14 }}>{error}</div>
      </div>
    );
  }

  return (
    <div style={{ maxWidth: 1200 }}>
      {/* Welcome header */}
      <div style={{ marginBottom: theme.spacing.xl }}>
        <h1
          style={{
            fontSize: 28,
            fontWeight: 700,
            color: theme.colors.textPrimary,
            marginBottom: theme.spacing.xs,
          }}
        >
          {getGreeting()}, Marius
        </h1>
        <p style={{ fontSize: 14, color: theme.colors.textMuted }}>{formatDate()}</p>
      </div>

      {/* Metric cards */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(4, 1fr)",
          gap: theme.spacing.md,
          marginBottom: theme.spacing.xl,
        }}
      >
        {metrics.map((m) => (
          <div
            key={m.label}
            style={{
              ...card,
              ...(m.highlight
                ? {
                    borderColor: `${theme.colors.accentGold}40`,
                    background: `linear-gradient(135deg, ${theme.colors.surface}, ${theme.colors.surfaceElevated})`,
                  }
                : {}),
            }}
          >
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: theme.spacing.xs,
                marginBottom: theme.spacing.sm,
                color: theme.colors.textMuted,
                fontSize: 12,
                fontWeight: 500,
                textTransform: "uppercase",
                letterSpacing: "0.05em",
              }}
            >
              {m.icon}
              {m.label}
            </div>
            <div
              className="tabular-nums"
              style={{
                fontSize: m.highlight ? 28 : 22,
                fontWeight: 700,
                color: m.color,
                marginBottom: theme.spacing.xs,
              }}
            >
              {m.value}
            </div>
            <div
              className="tabular-nums"
              style={{ fontSize: 12, color: theme.colors.textMuted }}
            >
              {m.sub}
            </div>
          </div>
        ))}
      </div>

      {/* Total portfolio chart */}
      {(() => {
        // Merge all section charts into one total
        const totalMap = new Map<string, number>();
        for (const points of Object.values(sectionCharts)) {
          for (const pt of points) {
            totalMap.set(pt.date, (totalMap.get(pt.date) || 0) + pt.value);
          }
        }
        const totalPoints = [...totalMap.entries()]
          .map(([date, value]) => ({ date, value }));

        if (totalPoints.length === 0) return null;

        const totalPnl = totalBalance - totalCash;
        const totalInvested = portfolios.reduce((sum, p) =>
          sum + (p.categories || []).reduce((cs, cat) =>
            cs + cat.positions.reduce((ps, pos) =>
              ps + (parseFloat(pos.netSize) || 0) * (parseFloat(pos.averageBuyIn) || 0), 0), 0), 0);
        const totalPnlPct = totalInvested > 0 ? ((totalPnl - totalInvested) / totalInvested) * 100 : 0;

        return (
          <div style={{ ...card, marginBottom: theme.spacing.xl }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: theme.spacing.lg }}>
              <h2 style={{ fontSize: 16, fontWeight: 600, color: theme.colors.textPrimary }}>
                Total Portfolio
              </h2>
              <div style={{ display: "flex", alignItems: "center", gap: theme.spacing.sm }}>
                <span className="tabular-nums" style={{ fontSize: 18, fontWeight: 700, color: theme.colors.accentGold }}>
                  €{fmt(totalBalance - totalCash)}
                </span>
                <span className="tabular-nums" style={{ fontSize: 13, fontWeight: 600, color: totalPnlPct >= 0 ? theme.colors.gain : theme.colors.loss }}>
                  {totalPnlPct >= 0 ? "+" : ""}{totalPnlPct.toFixed(1)}%
                </span>
              </div>
            </div>
            <div style={{ width: "100%", height: 250 }}>
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={totalPoints} margin={{ top: 5, right: 5, left: 5, bottom: 5 }}>
                  <defs>
                    <linearGradient id="grad-total" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor={theme.colors.accentGold} stopOpacity={0.3} />
                      <stop offset="100%" stopColor={theme.colors.accentGold} stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke={theme.colors.border} vertical={false} />
                  <XAxis dataKey="date" axisLine={false} tickLine={false} tick={{ fill: theme.colors.textMuted, fontSize: 10 }} />
                  <YAxis axisLine={false} tickLine={false} tick={{ fill: theme.colors.textMuted, fontSize: 10 }} tickFormatter={(v: number) => `€${v.toFixed(0)}`} />
                  <Tooltip
                    contentStyle={{ background: theme.colors.surfaceElevated, border: `1px solid ${theme.colors.border}`, borderRadius: theme.radius.md, color: theme.colors.textPrimary, fontSize: 13 }}
                    formatter={(value: number) => [`€${fmt(value)}`, "Total"]}
                  />
                  <Area type="monotone" dataKey="value" stroke={theme.colors.accentGold} strokeWidth={2} fill="url(#grad-total)" />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>
        );
      })()}

      {/* Connected accounts with cash */}
      <div style={{ ...card, marginBottom: theme.spacing.xl }}>
        <h2
          style={{
            fontSize: 16,
            fontWeight: 600,
            color: theme.colors.textPrimary,
            marginBottom: theme.spacing.md,
          }}
        >
          Connected Accounts
        </h2>
        <div style={{ display: "flex", flexDirection: "column", gap: theme.spacing.sm }}>
          {cash.map((c, i) => (
            <div
              key={i}
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                padding: theme.spacing.md,
                background: theme.colors.surfaceElevated,
                borderRadius: theme.radius.md,
                border: `1px solid ${theme.colors.border}`,
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: theme.spacing.sm }}>
                <div
                  style={{
                    width: 36,
                    height: 36,
                    borderRadius: theme.radius.sm,
                    background: `linear-gradient(135deg, ${theme.colors.accentLilac}, ${theme.colors.accentLavender})`,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontSize: 12,
                    fontWeight: 700,
                    color: "#fff",
                  }}
                >
                  TR
                </div>
                <div>
                  <div style={{ fontSize: 14, fontWeight: 600 }}>Trade Republic</div>
                  <div style={{ fontSize: 12, color: theme.colors.textMuted }}>{c.label}</div>
                </div>
              </div>
              <div style={{ textAlign: "right" }}>
                <div className="tabular-nums" style={{ fontSize: 14, fontWeight: 600 }}>
                  €{fmt(c.amount)}
                </div>
                <div style={{ fontSize: 12, color: theme.colors.textMuted }}>
                  {c.currencyId}
                </div>
              </div>
            </div>
          ))}
          {bpAccounts.map((a, i) => (
            <div
              key={`bp-${i}`}
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                padding: theme.spacing.md,
                background: theme.colors.surfaceElevated,
                borderRadius: theme.radius.md,
                border: `1px solid ${theme.colors.border}`,
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: theme.spacing.sm }}>
                <div
                  style={{
                    width: 36,
                    height: 36,
                    borderRadius: theme.radius.sm,
                    background: "linear-gradient(135deg, #0066b2, #00a3e0)",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontSize: 12,
                    fontWeight: 700,
                    color: "#fff",
                  }}
                >
                  BP
                </div>
                <div>
                  <div style={{ fontSize: 14, fontWeight: 600 }}>Banque Populaire</div>
                  <div style={{ fontSize: 12, color: theme.colors.textMuted }}>{a.label}</div>
                </div>
              </div>
              <div style={{ textAlign: "right" }}>
                <div className="tabular-nums" style={{ fontSize: 14, fontWeight: 600 }}>
                  €{fmt(a.balance)}
                </div>
                <div style={{ fontSize: 12, color: theme.colors.textMuted }}>
                  {a.currency}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Positions grouped by section with collapsible charts */}
      {orderedSections.map((sectionName) => {
        const positions = sections[sectionName];
        if (!positions?.length) return null;

        const sectionIcons: Record<string, string> = {
          CTO: "📈",
          PEA: "🇫🇷",
          Crypto: "₿",
          "Private Equity": "🏦",
        };

        const isExpanded = expandedSections[sectionName] ?? false;
        const chartPoints = sectionCharts[sectionName] || [];
        const sectionValue = positions.reduce((sum, p) => {
          const qty = parseFloat(p.netSize) || 0;
          const livePrice = prices[p.isin];
          const price = livePrice ?? (parseFloat(p.averageBuyIn) || 0);
          return sum + qty * price;
        }, 0);
        const sectionInvested = positions.reduce(
          (sum, p) => sum + (parseFloat(p.netSize) || 0) * (parseFloat(p.averageBuyIn) || 0),
          0
        );
        const sectionPnl = sectionValue - sectionInvested;
        const sectionPnlPct = sectionInvested > 0 ? (sectionPnl / sectionInvested) * 100 : 0;

        return (
          <div key={sectionName} style={{ ...card, marginBottom: theme.spacing.xl }}>
            {/* Section header — clickable to expand chart */}
            <div
              onClick={() => toggleSection(sectionName)}
              style={{
                display: "flex",
                alignItems: "center",
                gap: theme.spacing.sm,
                marginBottom: theme.spacing.md,
                cursor: "pointer",
                userSelect: "none",
              }}
            >
              <span style={{ fontSize: 18 }}>{sectionIcons[sectionName] ?? "📊"}</span>
              <h2 style={{ fontSize: 16, fontWeight: 600, color: theme.colors.textPrimary, flex: 1 }}>
                {sectionName}
              </h2>
              <span className="tabular-nums" style={{ fontSize: 16, fontWeight: 700, color: theme.colors.accentGold, marginRight: theme.spacing.xs }}>
                €{fmt(sectionValue)}
              </span>
              <span
                className="tabular-nums"
                style={{
                  fontSize: 13,
                  fontWeight: 600,
                  color: sectionPnl >= 0 ? theme.colors.gain : theme.colors.loss,
                  marginRight: theme.spacing.sm,
                }}
              >
                {sectionPnl >= 0 ? "+" : ""}{sectionPnlPct.toFixed(1)}%
              </span>
              <span
                style={{
                  fontSize: 12,
                  color: theme.colors.textMuted,
                  marginRight: theme.spacing.sm,
                }}
              >
                {positions.length} position{positions.length > 1 ? "s" : ""}
              </span>
              <span style={{ color: theme.colors.textMuted, fontSize: 14, transition: "transform 0.2s", transform: isExpanded ? "rotate(180deg)" : "rotate(0)" }}>
                ▼
              </span>
            </div>

            {/* Collapsible chart */}
            {isExpanded && chartPoints.length > 0 && (
              <div style={{ width: "100%", height: 200, marginBottom: theme.spacing.lg }}>
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={chartPoints} margin={{ top: 5, right: 5, left: 5, bottom: 5 }}>
                    <defs>
                      <linearGradient id={`grad-${sectionName}`} x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor={theme.colors.accentGold} stopOpacity={0.3} />
                        <stop offset="100%" stopColor={theme.colors.accentGold} stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke={theme.colors.border} vertical={false} />
                    <XAxis dataKey="date" axisLine={false} tickLine={false} tick={{ fill: theme.colors.textMuted, fontSize: 10 }} />
                    <YAxis axisLine={false} tickLine={false} tick={{ fill: theme.colors.textMuted, fontSize: 10 }} tickFormatter={(v: number) => `€${v.toFixed(0)}`} />
                    <Tooltip
                      contentStyle={{ background: theme.colors.surfaceElevated, border: `1px solid ${theme.colors.border}`, borderRadius: theme.radius.md, color: theme.colors.textPrimary, fontSize: 13 }}
                      formatter={(value: number) => [`€${fmt(value)}`, sectionName]}
                    />
                    <Area type="monotone" dataKey="value" stroke={theme.colors.accentGold} strokeWidth={2} fill={`url(#grad-${sectionName})`} />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            )}

            {isExpanded && chartPoints.length === 0 && (
              <div style={{ textAlign: "center", padding: theme.spacing.md, color: theme.colors.textMuted, fontSize: 13, marginBottom: theme.spacing.md }}>
                No chart data available
              </div>
            )}

            {/* Positions list */}
            <div style={{ display: "flex", flexDirection: "column", gap: theme.spacing.sm }}>
              {positions.map((pos, i) => {
                const qty = parseFloat(pos.netSize) || 0;
                const avgBuy = parseFloat(pos.averageBuyIn) || 0;
                const livePrice = prices[pos.isin];
                const currentPrice = livePrice ?? avgBuy;
                const currentValue = qty * currentPrice;
                const invested = qty * avgBuy;
                const pnl = currentValue - invested;
                const pnlPct = invested > 0 ? (pnl / invested) * 100 : 0;

                return (
                  <div
                    key={i}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      padding: theme.spacing.md,
                      background: theme.colors.surfaceElevated,
                      borderRadius: theme.radius.md,
                      border: `1px solid ${theme.colors.border}`,
                    }}
                  >
                    <div>
                      <div style={{ fontSize: 14, fontWeight: 600 }}>{pos.displayName}</div>
                      <div style={{ fontSize: 12, color: theme.colors.textMuted }}>
                        {qty} × €{fmt(currentPrice)}
                      </div>
                    </div>
                    <div style={{ textAlign: "right" }}>
                      <div className="tabular-nums" style={{ fontSize: 14, fontWeight: 600 }}>
                        €{fmt(currentValue)}
                      </div>
                      <div
                        className="tabular-nums"
                        style={{
                          fontSize: 12,
                          color: pnl >= 0 ? theme.colors.gain : theme.colors.loss,
                        }}
                      >
                        {pnl >= 0 ? "+" : ""}€{fmt(pnl)} ({pnl >= 0 ? "+" : ""}{pnlPct.toFixed(1)}%)
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
};

export default Dashboard;
