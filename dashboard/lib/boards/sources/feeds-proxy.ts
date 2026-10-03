// RA-7898 — readers for Pi-CEO backend paths. Every one goes through
// `fetchProxyJSON` (lib/pi-ceo-fetch.ts), the only honest reader of the proxy:
// a 200 carrying `X-Upstream-Status` is the proxy's placeholder, and it comes
// back as `null`, never as data.
//
// The value is the raw payload (or null when the backend did not answer),
// exactly what each panel got from `fetchProxyJSON` before the move, called
// with the same arguments the panel used.

import { fetchProxyJSON } from "@/lib/pi-ceo-fetch";
import { record } from "./http";
import type { FeedDef, FeedRead } from "./types";

export const BACKEND_UNREACHABLE = "Pi-CEO backend unreachable";

async function readProxy(path: string, init: RequestInit | undefined): Promise<FeedRead<unknown>> {
  try {
    const data = await fetchProxyJSON<unknown>(path, init);
    if (data === null) return { kind: "unreachable", value: null, reason: BACKEND_UNREACHABLE };
    return { kind: "live", value: data };
  } catch (exc) {
    return { kind: "unreachable", value: null, reason: exc instanceof Error ? exc.message : String(exc) };
  }
}

const NO_STORE: RequestInit = { cache: "no-store" };
const LIVE_INIT: RequestInit = { credentials: "include", cache: "no-store" };

/** mission-control/live: a body `error` is a failed read; `ts` is the server clock. */
export async function readMissionControlLive(): Promise<FeedRead<unknown>> {
  const read = await readProxy("/api/mission-control/live", LIVE_INIT);
  if (read.kind !== "live") return read;
  const body = record(read.value);
  if (!body) return { ...read, kind: "unreachable", reason: "invalid payload" };
  if (typeof body.error === "string" && body.error) return { ...read, kind: "unreachable", reason: body.error };
  return { ...read, serverTs: typeof body.ts === "string" ? body.ts : null };
}

// Arguments are the ones each panel passed before the move: HealthGrid read
// projects/health with no init (pinned by __tests__/health-grid.test.tsx),
// IdeaPipelinePanel and LiveActivityFeed sent credentials, the rest no-store.
const proxied = (path: string, init?: RequestInit) => () => readProxy(path, init);

export const PROXY_FEEDS: FeedDef<unknown>[] = [
  { id: "pi-health", url: "Pi-CEO /health (proxy)", intervalMs: 15_000, read: proxied("/health", NO_STORE) },
  { id: "sessions", url: "Pi-CEO /api/sessions (proxy)", intervalMs: 15_000, read: proxied("/api/sessions", NO_STORE) },
  { id: "projects-health", url: "Pi-CEO /api/projects/health (proxy)", intervalMs: 30_000, read: proxied("/api/projects/health") },
  { id: "mc-live", url: "Pi-CEO /api/mission-control/live (proxy)", intervalMs: 5_000, read: readMissionControlLive, serverClock: true },
  { id: "idea-pipeline", url: "Pi-CEO /api/idea-pipeline (proxy)", intervalMs: 60_000, read: proxied("/api/idea-pipeline", LIVE_INIT) },
  { id: "pipelines", url: "Pi-CEO /api/pipelines (proxy)", intervalMs: 30_000, read: proxied("/api/pipelines", NO_STORE) },
];
