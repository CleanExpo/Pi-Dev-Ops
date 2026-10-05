// RA-7898 — the module registry: the only modules a board may reference.

import { BUSINESS_MODULES } from "./businesses";
import { COMPUTE_MODULES } from "./compute";
import { DELIVERY_MODULES } from "./delivery";
import { FOUNDER_MODULES } from "./founder";
import { KNOWLEDGE_MODULES } from "./knowledge";
import { MACHINE_MODULES } from "./machines";
import { SAFETY_MODULES } from "./safety";
import type { ModuleDef } from "./types";

export const MODULE_LIST: readonly ModuleDef[] = [
  ...FOUNDER_MODULES, ...MACHINE_MODULES, ...DELIVERY_MODULES, ...BUSINESS_MODULES,
  ...COMPUTE_MODULES, ...SAFETY_MODULES, ...KNOWLEDGE_MODULES,
];

export const MODULES: ReadonlyMap<string, ModuleDef> = new Map(MODULE_LIST.map((m) => [m.id, m]));

export function firstView(def: ModuleDef): string {
  return Object.keys(def.views)[0];
}

export * from "./types";
