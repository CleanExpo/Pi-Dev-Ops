// RA-7898 — readers for Pi-CEO backend paths. Every one goes through
// `fetchProxy` (lib/pi-ceo-fetch.ts), the only honest reader of the proxy: a
// 200 carrying `X-Upstream-Status` is the proxy's placeholder, not data.
//
// The value is the raw payload (or null when the backend did not answer),
// exactly what each panel got from `fetchProxyJSON` before the move.

import { fetchProxy, type ProxyResult } from "@/lib/pi-ceo-fetch";
import { record } from "./http";
import type { FeedDef, FeedRead } from "./types";

function why(result: Extract<ProxyResult<unknown>, { ok: false }>): string {
  if (result.reason === "unreachable") return `Pi-CEO backend unreachable (upstream ${result.upstreamStatus ?? "?"})`;
  if (result.reason === "http") return `HTTP ${result.upstreamStatus ?? "?"}`;
  return "network error";
}

async function readProxy(path: string, signal: AbortSignal): Promise<FeedRead<unknown>> {
  const result = await fetchProxy<unknown>(path, { cache: "no-store", credentials: "include", signal });
  if (!result.ok) {
    return { kind: "unreachable", value: null, reason: why(result), httpStatus: result.upstreamStatus };
  }
  return { kind: "live", value: result.data, httpStatus: 200 };
}

/** mission-control/live: a body `error` is a failed read; `ts` is the server clock. */
export async function readMissionControlLive(signal: AbortSignal): Promise<FeedRead<unknown>> {
  const read = await readProxy("/api/mission-control/live", signal);
  const body = record(read.value);
  if (read.kind !== "live" || !body) return read.kind === "live" ? { ...read, kind: "unreachable", reason: "invalid payload" } : read;
  if (typeof body.error === "string" && body.error) return { ...read, kind: "unreachable", reason: body.error };
  return { ...read, serverTs: typeof body.ts === "string" ? body.ts : null };
}

const proxied = (path: string) => (signal: AbortSignal) => readProxy(path, signal);

export const PROXY_FEEDS: FeedDef<unknown>[] = [
  { id: "pi-health", url: "/api/pi-ceo/health", intervalMs: 15_000, read: proxied("/health") },
  { id: "sessions", url: "/api/pi-ceo/api/sessions", intervalMs: 15_000, read: proxied("/api/sessions") },
  { id: "projects-health", url: "/api/pi-ceo/api/projects/health", intervalMs: 30_000, read: proxied("/api/projects/health") },
  { id: "mc-live", url: "/api/pi-ceo/api/mission-control/live", intervalMs: 5_000, read: readMissionControlLive, serverClock: true },
  { id: "idea-pipeline", url: "/api/pi-ceo/api/idea-pipeline", intervalMs: 60_000, read: proxied("/api/idea-pipeline") },
  { id: "pipelines", url: "/api/pi-ceo/api/pipelines", intervalMs: 30_000, read: proxied("/api/pipelines") },
];
