// RA-7898 — module registry types (docs/specs/modular-boards.md §4).

import type { ComponentType } from "react";

export type Sector = "Machines" | "Delivery" | "Compute" | "Businesses" | "Safety" | "Knowledge" | "Founder" | "Utility";

export const SECTORS: readonly Sector[] = ["Founder", "Machines", "Delivery", "Businesses", "Compute", "Safety", "Knowledge", "Utility"];

export interface GridSize {
  w: number;
  h: number;
}

/** Props every view receives. View #1 panels ignore them. */
export interface ViewProps {
  /** The kiosk's own host, when a board is shown on a wall screen. */
  kioskHost?: string | null;
}

export interface ViewDef {
  label: string;
  size: GridSize;
  component: ComponentType<ViewProps>;
  /** An action view renders in every state except loading (spec §4). */
  action?: boolean;
}

export interface ModuleDef {
  /** The only thing a board may reference. */
  id: string;
  /** Sentence case. */
  name: string;
  sector: Sector;
  /** Feed ids from lib/boards/sources/feeds.ts, at least one. */
  sources: readonly string[];
  minSize: GridSize;
  /** True when any view can trigger a write. */
  action: boolean;
  /** One line for the library. */
  blurb: string;
  /** Ordered: the first view is the default. */
  views: Readonly<Record<string, ViewDef>>;
}
