export const theme = {
  colors: {
    background: "#102b3f",
    surface: "#062726",
    surfaceElevated: "#143a42",
    accentGold: "#C9A84C",
    accentLavender: "#a06cd5",
    accentLilac: "#6247aa",
    textPrimary: "#f0ece4",
    textSecondary: "#e2cfea",
    textMuted: "#e2cfea80",
    gain: "#C9A84C",
    loss: "#e2cfea70",
    border: "#1a3d4d",
    dataViz: ["#2c7ce5", "#f8c421", "#49cc5c", "#6434e9", "#fb6640", "#f82553"],
  },
  font: {
    family: "'Inter', sans-serif",
  },
  spacing: {
    xs: 4,
    sm: 8,
    md: 16,
    lg: 24,
    xl: 32,
    "2xl": 48,
  },
  radius: {
    sm: 4,
    md: 8,
    lg: 12,
    xl: 16,
  },
} as const;

export type Theme = typeof theme;
