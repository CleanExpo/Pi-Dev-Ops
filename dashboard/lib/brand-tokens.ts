/** Dark-theme brand tokens for components that need literal hex (xterm, inline styles). */
export const BRAND_DARK = {
  accent: "#ff3b5c",
  onAccent: "#0e1014",
  success: "#00d97e",
  warning: "#ff8a1f",
  error: "#e5484d",
  info: "#22d3ee",
  text: "#f4f5f7",
  textMuted: "#a7adba",
} as const;

/** CSS variable references for React inline styles */
export const CSS = {
  accent: "var(--accent)",
  onAccent: "var(--on-accent)",
  success: "var(--success)",
  warning: "var(--warning)",
  error: "var(--error)",
  info: "var(--info)",
  text: "var(--text)",
  textMuted: "var(--text-muted)",
  panel: "var(--panel)",
} as const;
