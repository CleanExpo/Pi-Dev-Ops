// RA-7898 — readers for the dashboard's own routes (not the Pi-CEO proxy).
//
// Each reader returns the value its panel used to build for itself, plus the
// normalised kind. Failure shapes are the ones in docs/specs/modular-boards.md
// §3.3; each is pinned by __tests__/boards-feed-readers.test.ts.

import type { FleetView } from "@/lib/control/mesh-fleet";
import type { WallSnapshot } from "@/lib/wall/snapshot";
import { getJson, isNotConfigured, record } from "./http";
import type {
  CuratorValue, FabricStatus, KillSwitchStatus, ProviderUsageValue, SwarmValue, WikiGraphSummary,
} from "./shapes";
import type { FeedDef, FeedRead } from "./types";

const FLEET_NOT_CONFIGURED = new Set(["mesh secret not configured", "Pi-CEO URL not configured"]);

export async function readMeshFleet(signal: AbortSignal): Promise<FeedRead<FleetView>> {
  const r = await getJson("/api/mesh-fleet", signal);
  const body = record(r.body) as FleetView | null;
  if (body && body.status === "ok") {
    return { kind: r.ok === false ? "unreachable" : "live", value: body, serverTs: body.checkedAt, httpStatus: r.status };
  }
  if (body && body.status === "unavailable") {
    const kind = FLEET_NOT_CONFIGURED.has(body.reason) ? "no_source" : "unreachable";
    return { kind, value: body, reason: body.reason, httpStatus: r.status };
  }
  const value: FleetView = { status: "unavailable", checkedAt: new Date().toISOString(), reason: "fleet read failed" };
  return { kind: "unreachable", value, reason: r.error ?? `HTTP ${r.status ?? "?"}`, httpStatus: r.status };
}

export async function readWall(signal: AbortSignal): Promise<FeedRead<WallSnapshot | null>> {
  const r = await getJson("/api/mesh-fleet/wall", signal);
  const body = record(r.body) as WallSnapshot | null;
  if (!r.ok || !body || !Array.isArray(body.stations)) {
    return { kind: "unreachable", value: null, reason: r.error ?? `HTTP ${r.status ?? "?"}`, httpStatus: r.status };
  }
  const fleet = body.fleet?.status;
  if (fleet === "no_source") return { kind: "no_source", value: body, reason: body.fleet.reason, httpStatus: r.status };
  if (fleet === "broken") return { kind: "unreachable", value: body, reason: body.fleet.reason, httpStatus: r.status };
  return { kind: "live", value: body, serverTs: body.generated_at, httpStatus: r.status };
}

export async function readModelFabric(signal: AbortSignal): Promise<FeedRead<FabricStatus>> {
  const r = await getJson("/api/model-fabric", signal);
  if (r.error !== undefined) {
    return { kind: "unreachable", value: { enabled: false, healthy: false, error: r.message ?? r.error }, reason: r.error };
  }
  if (r.body === null) {
    const error = r.ok ? "invalid JSON from /api/model-fabric" : `HTTP ${r.status}`;
    return { kind: "unreachable", value: { enabled: false, healthy: false, error }, reason: error, httpStatus: r.status };
  }
  const body = (record(r.body) ?? {}) as FabricStatus;
  // A non-2xx without an `error` field would otherwise render as "DISABLED" (ModelFabricPanel).
  if (!r.ok && !body.error) body.error = `HTTP ${r.status}`;
  return r.ok && !body.error
    ? { kind: "live", value: body, httpStatus: r.status }
    : { kind: "unreachable", value: body, reason: body.error ?? `HTTP ${r.status}`, httpStatus: r.status };
}

export async function readSwarmStatus(signal: AbortSignal): Promise<FeedRead<SwarmValue>> {
  const r = await getJson("/api/swarm-status", signal);
  if (r.error !== undefined) return { kind: "unreachable", value: { data: null, error: r.message ?? r.error }, reason: r.error };
  if (!r.ok) return { kind: "unreachable", value: { data: null, error: `HTTP ${r.status}` }, reason: `HTTP ${r.status}`, httpStatus: r.status };
  const data = record(r.body) as SwarmValue["data"];
  if (!data) return { kind: "unreachable", value: { data: null, error: "invalid JSON from /api/swarm-status" }, reason: "invalid JSON", httpStatus: r.status };
  // The route's own fallback is 200 with state UNKNOWN: a failed read, shown as the panel always showed it.
  const unknown = data.state === "UNKNOWN";
  return {
    kind: unknown ? "unreachable" : "live", value: { data, error: null },
    reason: unknown ? "swarm state unknown" : undefined, httpStatus: r.status,
  };
}

export const SIGNED_OUT_REASON = "Signed out — sign in again (401)";

export async function readKillSwitch(signal: AbortSignal): Promise<FeedRead<KillSwitchStatus>> {
  const r = await getJson("/api/kill-switch?op=status", signal);
  if (r.error !== undefined) return { kind: "unreachable", value: { error: r.error }, reason: r.error };
  const body = (record(r.body) ?? {}) as KillSwitchStatus;
  if (r.status === 401) return { kind: "unreachable", value: body, reason: SIGNED_OUT_REASON, httpStatus: 401 };
  if (body.error) {
    const kind = isNotConfigured(body.error) ? "no_source" : "unreachable";
    return { kind, value: body, reason: body.error, httpStatus: r.status };
  }
  if (r.ok === false) return { kind: "unreachable", value: body, reason: `HTTP ${r.status}`, httpStatus: r.status };
  return { kind: "live", value: body, httpStatus: r.status };
}

export async function readProviderUsage(signal: AbortSignal): Promise<FeedRead<ProviderUsageValue>> {
  const r = await getJson("/api/command-centre/provider-usage", signal);
  const body = record(r.body);
  if (!r.ok || !body) return { kind: "unreachable", value: null, reason: r.error ?? `provider_usage_http_${r.status}`, httpStatus: r.status };
  const payload = body as unknown as NonNullable<ProviderUsageValue>;
  return { kind: "live", value: payload, serverTs: payload.generatedAt, httpStatus: r.status };
}

export async function readWikiGraph(signal: AbortSignal): Promise<FeedRead<WikiGraphSummary | null>> {
  const r = await getJson("/api/command-centre/wiki-graph", signal);
  const body = record(r.body);
  if (!r.ok || !body) return { kind: "unreachable", value: null, reason: r.error ?? `HTTP ${r.status}`, httpStatus: r.status };
  const value: WikiGraphSummary = {
    pageCount: typeof body.pageCount === "number" ? body.pageCount : null,
    edgeCount: typeof body.edgeCount === "number" ? body.edgeCount : null,
    lastSync: typeof body.lastSync === "string" ? body.lastSync : null,
    source: typeof body.source === "string" ? body.source : null,
    reason: typeof body.reason === "string" ? body.reason : null,
  };
  if (value.source === "unconfigured") return { kind: "no_source", value, reason: value.reason ?? "wiki graph not configured", httpStatus: r.status };
  return { kind: "live", value, httpStatus: r.status };
}

export const CURATOR_URL = "/api/curator-proposals?status=pending&limit=10";

export async function readCurator(signal: AbortSignal): Promise<FeedRead<CuratorValue>> {
  const r = await getJson(CURATOR_URL, signal);
  if (r.error !== undefined) return { kind: "unreachable", value: { error: r.error }, reason: r.error };
  const body = (record(r.body) ?? {}) as CuratorValue;
  // A failed read must never render as "No pending proposals" (CuratorProposalsPanel).
  if (!r.ok && !body.error) body.error = `HTTP ${r.status}`;
  if (body.error) {
    const kind = isNotConfigured(body.error) ? "no_source" : "unreachable";
    return { kind, value: body, reason: body.error, httpStatus: r.status };
  }
  return { kind: "live", value: body, httpStatus: r.status };
}

export const DIRECT_FEEDS: FeedDef<unknown>[] = [
  { id: "mesh-fleet", url: "/api/mesh-fleet", intervalMs: 20_000, read: readMeshFleet, serverClock: true },
  { id: "wall", url: "/api/mesh-fleet/wall", intervalMs: 5_000, read: readWall, serverClock: true },
  { id: "model-fabric", url: "/api/model-fabric", intervalMs: 15_000, read: readModelFabric },
  { id: "swarm-status", url: "/api/swarm-status", intervalMs: 30_000, read: readSwarmStatus },
  { id: "kill-switch", url: "/api/kill-switch?op=status", intervalMs: 10_000, read: readKillSwitch },
  { id: "provider-usage", url: "/api/command-centre/provider-usage", intervalMs: 30_000, read: readProviderUsage, serverClock: true },
  { id: "wiki-graph", url: "/api/command-centre/wiki-graph", intervalMs: 300_000, read: readWikiGraph },
  { id: "curator", url: CURATOR_URL, intervalMs: 30_000, read: readCurator },
] as FeedDef<unknown>[];
