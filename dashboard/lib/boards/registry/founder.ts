// RA-7898 — Founder and Utility sectors.
import { ClockAnalog, ClockDigital, NorthStarBanner, NorthStarCompact, NORTH_STAR } from "@/components/boards/views/founder";
import { WallBannerView } from "@/components/boards/views/wall";
import type { ModuleDef } from "./types";

export const FOUNDER_MODULES: ModuleDef[] = [
  {
    id: "wall-banner", name: "Attention banner", sector: "Founder", sources: ["wall"], minSize: { w: 4, h: 2 }, action: false,
    blurb: "Red and grey counts from the wall snapshot, and a stale warning.",
    views: { banner: { label: "Banner", size: { w: 12, h: 3 }, component: WallBannerView } },
  },
  {
    id: "north-star", name: "North Star", sector: "Founder", sources: ["static"], minSize: { w: 3, h: 2 }, action: false,
    blurb: `The line every board starts from (${NORTH_STAR.source}).`,
    views: {
      banner: { label: "Banner", size: { w: 12, h: 3 }, component: NorthStarBanner },
      compact: { label: "Compact", size: { w: 4, h: 2 }, component: NorthStarCompact },
    },
  },
  {
    id: "clock", name: "Brisbane time", sector: "Utility", sources: ["local-clock"], minSize: { w: 2, h: 3 }, action: false,
    blurb: "Local time for a wall screen, from this screen's clock.",
    views: {
      digital: { label: "Digital", size: { w: 3, h: 3 }, component: ClockDigital },
      analog: { label: "Analog", size: { w: 3, h: 4 }, component: ClockAnalog },
    },
  },
];
