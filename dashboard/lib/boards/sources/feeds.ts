// RA-7898 — the feed catalogue: every source id a module may name.

import { DIRECT_FEEDS } from "./feeds-direct";
import { PROXY_FEEDS } from "./feeds-proxy";
import type { FeedDef } from "./types";

/** Local feeds never touch the network; they exist so every module names a source. */
const LOCAL_FEEDS: FeedDef<unknown>[] = [
  { id: "local-clock", url: "this screen's clock", intervalMs: 60_000, local: true,
    read: async () => ({ kind: "live", value: null }) },
  { id: "static", url: "text in the bundle", intervalMs: 3_600_000, local: true,
    read: async () => ({ kind: "live", value: null }) },
];

export const FEEDS: ReadonlyMap<string, FeedDef<unknown>> = new Map(
  [...DIRECT_FEEDS, ...PROXY_FEEDS, ...LOCAL_FEEDS].map((def) => [def.id, def]),
);

export function feed(id: string): FeedDef<unknown> {
  const def = FEEDS.get(id);
  if (!def) throw new Error(`unknown feed: ${id}`);
  return def;
}
