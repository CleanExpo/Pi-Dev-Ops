// RA-7898 — readers for Pi-CEO backend paths. Every one goes through
// `fetchProxyJSON` (lib/pi-ceo-fetch.ts), the only honest reader of the proxy:
// a 200 carrying `X-Upstream-Status` is the proxy's placeholder, and it comes
// back as `null`, never as data.
//
// The value is the raw payload (or null when the backend did not answer),
// exactly what each panel got from `fetchProxyJSON` before the move, called
// with the same arguments the panel used.

import { fetchProxyJSON } from "@/lib/pi-ceo-fetch";
import { errorText, record } from "./http";
import type { FeedDef, FeedRead } from "./types";

export const BACKEND_UNREACHABLE = "Pi-CEO backend unreachable";

export const INVALID_PAYLOAD = "invalid payload";

/** What each feed's panel reads, checked before a 200 may count as live. */
type Shape = (data: unknown) => boolean;
const isList: Shape = (data) => Array.isArray(data);
const anyShape: Shape = () => true;

async function readProxy(path: string, init: RequestInit | undefined, shape: Shape = anyShape): Promise<FeedRead<unknown>> {
  try {
    const data = await fetchProxyJSON<unknown>(path, init);
    if (data === null) return { kind: "unreachable", value: null, reason: BACKEND_UNREACHABLE };
    // A malformed 200 is a failed read, never empty data shown as live.
    if (!shape(data)) return { kind: "unreachable", value: null, reason: INVALID_PAYLOAD };
    return { kind: "live", value: data };
  } catch (exc) {
    return { kind: "unreachable", value: null, reason: exc instanceof Error ? exc.message : String(exc) };
  }
}

const NO_STORE: RequestInit = { cache: "no-store" };
// The poller's signal rides along with each panel's own options, so its 10 s
// timeout cancels the wire request instead of leaving it open.
const withSignal = (init: RequestInit | undefined, signal: AbortSignal | undefined): RequestInit | undefined =>
  signal ? { ...init, signal } : init;
const LIVE_INIT: RequestInit = { credentials: "include", cache: "no-store" };

/** mission-control/live: a body `error` is a failed read; `ts` is the server clock. */
export async function readMissionControlLive(signal?: AbortSignal): Promise<FeedRead<unknown>> {
  const read = await readProxy("/api/mission-control/live", withSignal(LIVE_INIT, signal));
  if (read.kind !== "live") return read;
  const body = record(read.value);
  if (!body) return { ...read, kind: "unreachable", value: null, reason: INVALID_PAYLOAD };
  const error = errorText(body.error, INVALID_PAYLOAD);
  // A non-text error is a malformed body: dropped, so no panel renders an object.
  if (error === INVALID_PAYLOAD) return { ...read, kind: "unreachable", value: null, reason: INVALID_PAYLOAD };
  if (error) return { ...read, kind: "unreachable", reason: error };
  // The backend always stamps `ts`; a body without it is not a live payload.
  if (typeof body.ts !== "string") return { ...read, kind: "unreachable", value: null, reason: INVALID_PAYLOAD };
  return { ...read, serverTs: body.ts };
}

// Arguments are the ones each panel passed before the move: HealthGrid read
// projects/health with no init (pinned by __tests__/health-grid.test.tsx),
// IdeaPipelinePanel and LiveActivityFeed sent credentials, the rest no-store.
const proxied = (path: string, init: RequestInit | undefined, shape: Shape) =>
  (signal: AbortSignal) => readProxy(path, withSignal(init, signal), shape);
const isHealth: Shape = (data) => typeof record(data)?.status === "string";
const isIdeaPipeline: Shape = (data) => record(record(data)?.snapshot) !== null;

export const PROXY_FEEDS: FeedDef<unknown>[] = [
  { id: "pi-health", url: "Pi-CEO /health (proxy)", intervalMs: 15_000, read: proxied("/health", NO_STORE, isHealth) },
  { id: "sessions", url: "Pi-CEO /api/sessions (proxy)", intervalMs: 15_000, read: proxied("/api/sessions", NO_STORE, isList) },
  { id: "projects-health", url: "Pi-CEO /api/projects/health (proxy)", intervalMs: 30_000, read: proxied("/api/projects/health", undefined, isList) },
  { id: "mc-live", url: "Pi-CEO /api/mission-control/live (proxy)", intervalMs: 5_000, read: readMissionControlLive, serverClock: true },
  { id: "idea-pipeline", url: "Pi-CEO /api/idea-pipeline (proxy)", intervalMs: 60_000, read: proxied("/api/idea-pipeline", LIVE_INIT, isIdeaPipeline) },
  { id: "pipelines", url: "Pi-CEO /api/pipelines (proxy)", intervalMs: 30_000, read: proxied("/api/pipelines", NO_STORE, isList) },
];
