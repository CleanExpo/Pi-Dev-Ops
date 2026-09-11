export interface SidebarNavItem {
  href: string;
  label: string;
  icon: string;
  key: string;
}

/** Sidebar only. Command-centre, /health, and /dashboard stay off this list. */
export const SIDEBAR_NAV: readonly SidebarNavItem[] = [
  { href: "/overview", label: "Overview", icon: "◈", key: "overview" },
  { href: "/brain", label: "Brain", icon: "◎", key: "brain" },
  { href: "/control", label: "Control", icon: "⊞", key: "control" },
  { href: "/loop", label: "Loop", icon: "∞", key: "loop" },
  { href: "/builds", label: "Builds", icon: "⚙", key: "builds" },
  { href: "/routines", label: "Routines", icon: "↻", key: "routines" },
  { href: "/projects", label: "Portfolio", icon: "◫", key: "projects" },
  { href: "/chat", label: "Chat", icon: "◉", key: "chat" },
  { href: "/history", label: "History", icon: "☰", key: "history" },
  { href: "/settings", label: "Settings", icon: "⊙", key: "settings" },
];

export const SIDEBAR_OFF_LIST = ["/command-centre", "/health", "/dashboard"] as const;

export function sidebarHrefs(): string[] {
  return SIDEBAR_NAV.map((item) => item.href);
}
