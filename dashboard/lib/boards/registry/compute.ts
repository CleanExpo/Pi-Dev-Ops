// RA-7898 — Compute sector.
import { ModelBars, ModelRing, ModelTable } from "@/components/boards/views/metrics";
import { ModelFabricView, ProviderUsageView } from "@/components/boards/views/panels";
import type { ModuleDef } from "./types";

export const COMPUTE_MODULES: ModuleDef[] = [
  {
    id: "models", name: "Model routing", sector: "Compute", sources: ["model-fabric"], minSize: { w: 3, h: 4 }, action: false,
    blurb: "Model fabric lanes, last call and totals.",
    views: {
      panel: { label: "Fabric panel", size: { w: 6, h: 8 }, component: ModelFabricView },
      bars: { label: "Bars", size: { w: 5, h: 4 }, component: ModelBars },
      ring: { label: "Ring", size: { w: 5, h: 4 }, component: ModelRing },
      table: { label: "Table", size: { w: 5, h: 5 }, component: ModelTable },
    },
  },
  {
    id: "provider-usage", name: "Provider usage", sector: "Compute", sources: ["provider-usage"], minSize: { w: 4, h: 6 }, action: false,
    blurb: "Each provider's usage against its limit, and routing hints.",
    views: { cockpit: { label: "Cockpit", size: { w: 8, h: 10 }, component: ProviderUsageView } },
  },
];
