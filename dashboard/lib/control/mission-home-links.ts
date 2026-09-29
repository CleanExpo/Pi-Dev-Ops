// The Mission Control home sidebar (components/control/MissionHomeShell.tsx).
// Plain data, so e2e-live/control-hub.spec.ts can check the nav the shell
// renders without importing a component that pulls in CSS modules.
export const MISSION_HOME_LINKS = [
  { href: "/control", label: "Mission Control", symbol: "⌂" },
  { href: "/projects", label: "Portfolio", symbol: "◇" },
  { href: "/control/build", label: "Work", symbol: "☷" },
  { href: "/control/health", label: "Evidence", symbol: "▤" },
  { href: "/command-centre/wall", label: "Machines", symbol: "▣" },
];
