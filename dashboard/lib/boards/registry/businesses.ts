// RA-7898 — Businesses sector.
import { HealthGridView, PortfolioFocusView } from "@/components/boards/views/panels";
import type { ModuleDef } from "./types";

export const BUSINESS_MODULES: ModuleDef[] = [
  {
    id: "portfolio", name: "Business health", sector: "Businesses",
    sources: ["projects-health", "mc-live", "pipelines"], minSize: { w: 4, h: 6 }, action: false,
    blurb: "Scan score per business, observed work and pathway stages, kept separate.",
    views: { focus: { label: "Portfolio focus", size: { w: 8, h: 10 }, component: PortfolioFocusView } },
  },
  {
    id: "health", name: "Project health", sector: "Businesses", sources: ["projects-health"], minSize: { w: 4, h: 5 }, action: true,
    blurb: "Health grid with drill-down and Fix with Claude (the existing build route).",
    views: { grid: { label: "Health grid", size: { w: 8, h: 8 }, component: HealthGridView, action: true } },
  },
];
