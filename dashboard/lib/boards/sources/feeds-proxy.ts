// RA-7898 — readers for Pi-CEO backend paths. Every one goes through
// `fetchProxyJSON` (lib/pi-ceo-fetch.ts), the only honest reader of the proxy:
// a 200 carrying `X-Upstream-Status` is the proxy's placeholder, and it comes
// back as `null`, never as data.
//
// The value is the raw payload (or null when the backend did not answer),
// exactly what each panel got from `fetchProxyJSON` before the move, called
// with the same arguments the panel used.

import { projectLanes, type LanesView } from "@/lib/control/mesh-lanes";
import { fetchProxyJSON } from "@/lib/pi-ceo-fetch";
import { errorText, record } from "./http";
import { defineFeed, type FeedDef, type FeedRead } from "./types";
import { isHealth, isIdeaPipeline, isMissionControlLive, isPipelineList, isProjectList, isSessionList } from "./validate-proxy";

export const BACKEND_UNREACHABLE = "Pi-CEO backend unreachable";

export const INVALID_PAYLOAD = "invalid payload";

/** What each feed's panel reads, checked before a 200 may count as live. */
type Shape = (data: unknown) => boolean;
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
  // Every row and field the panels read (validate-proxy.ts): a partial body
  // would show missing counts as a quiet, empty live feed, or crash a row.
  if (!isMissionControlLive(body)) return { ...read, kind: "unreachable", value: null, reason: INVALID_PAYLOAD };
  return { ...read, serverTs: body.ts as string };
}

/**
 * Claude lanes: the newest mc-lane events (Pi-CEO /api/mission-control/lane-events,
 * session-gated upstream), folded into one row per session. A backend that did
 * not answer, or an events body that is not a list, is unreachable — never an
 * empty lane list (lib/control/mesh-lanes.ts).
 */
export async function readMeshLanes(signal?: AbortSignal): Promise<FeedRead<LanesView | null>> {
  const read = await readProxy("/api/mission-control/lane-events", withSignal(NO_STORE, signal));
  if (read.kind !== "live") return { ...read, value: null };
  const view = projectLanes(read.value, new Date().toISOString());
  if (view.status !== "ok") return { kind: "unreachable", value: null, reason: view.reason };
  return { kind: "live", value: view, serverTs: view.checkedAt };
}

// Arguments are the ones each panel passed before the move: HealthGrid read
// projects/health with no init (pinned by __tests__/health-grid.test.tsx),
// IdeaPipelinePanel and LiveActivityFeed sent credentials, the rest no-store.
const proxied = (path: string, init: RequestInit | undefined, shape: Shape) =>
  (signal: AbortSignal) => readProxy(path, withSignal(init, signal), shape);

export const PROXY_FEEDS: FeedDef<unknown>[] = [
  { id: "pi-health", url: "Pi-CEO /health (proxy)", intervalMs: 15_000, read: proxied("/health", NO_STORE, isHealth) },
  { id: "sessions", url: "Pi-CEO /api/sessions (proxy)", intervalMs: 15_000, read: proxied("/api/sessions", NO_STORE, isSessionList) },
  { id: "projects-health", url: "Pi-CEO /api/projects/health (proxy)", intervalMs: 30_000, read: proxied("/api/projects/health", undefined, isProjectList) },
  { id: "mc-live", url: "Pi-CEO /api/mission-control/live (proxy)", intervalMs: 5_000, read: readMissionControlLive, serverClock: true },
  { id: "idea-pipeline", url: "Pi-CEO /api/idea-pipeline (proxy)", intervalMs: 60_000, read: proxied("/api/idea-pipeline", LIVE_INIT, isIdeaPipeline) },
  { id: "pipelines", url: "Pi-CEO /api/pipelines (proxy)", intervalMs: 30_000, read: proxied("/api/pipelines", NO_STORE, isPipelineList) },
  defineFeed({ id: "mesh-lanes", url: "Pi-CEO /api/mission-control/lane-events (proxy)", intervalMs: 15_000, read: readMeshLanes, serverClock: true }),
];
