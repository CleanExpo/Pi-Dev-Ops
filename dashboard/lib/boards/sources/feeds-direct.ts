// RA-7898 — readers for the dashboard's own routes (not the Pi-CEO proxy).
//
// Each reader returns the value its panel used to build for itself, plus the
// normalised kind. Failure shapes are the ones in docs/specs/modular-boards.md
// §3.3; each is pinned by __tests__/boards-feed-readers.test.ts.

import type { FleetView } from "@/lib/control/mesh-fleet";
import type { WallSnapshot } from "@/lib/wall/snapshot";
import { errorText, getJson, isNotConfigured, record } from "./http";
import type {
  CuratorValue, FabricStatus, KillSwitchStatus, ProviderUsageValue, SwarmValue, WikiGraphSummary,
} from "./shapes";
import { defineFeed, type FeedDef, type FeedRead } from "./types";

const isText = (v: unknown) => typeof v === "string";
const isTextOrNull = (v: unknown) => v === null || typeof v === "string";
const isChip = (v: unknown) => v === "GREEN" || v === "RED" || v === "GREY";
/** A row field a panel renders as text: absent, null, text or a number - never an object. */
const isRenderable = (v: unknown) => v === undefined || v === null || typeof v === "string" || typeof v === "number";

const isFleetMachine = (m: unknown) => {
  const r = record(m);
  return r !== null && isText(r.host) && typeof r.stale === "boolean"
    && isTextOrNull(r.revision) && isTextOrNull(r.lastHeartbeat) && isTextOrNull(r.currentClaim);
};
const isWallTile = (m: unknown) => {
  const r = record(m);
  return r !== null && isText(r.host) && isChip(r.chip) && isText(r.reason) && Array.isArray(r.agents);
};
const isStation = (s: unknown) => {
  const r = record(s);
  return r !== null && isText(r.id) && isText(r.name) && isChip(r.chip) && isText(r.reason);
};

const FLEET_NOT_CONFIGURED = new Set(["mesh secret not configured", "Pi-CEO URL not configured"]);

export async function readMeshFleet(signal: AbortSignal): Promise<FeedRead<FleetView>> {
  const r = await getJson("/api/mesh-fleet", signal);
  const body = record(r.body) as FleetView | null;
  // "ok" counts only with the machine list and clock FleetTile reads.
  // A non-2xx is never shown as a fleet, even with an "ok" body: FleetTile
  // would render its machines (or "No machines enrolled") as fact.
  if (r.ok && body && body.status === "ok" && typeof body.checkedAt === "string" && Array.isArray(body.machines)
    && body.machines.every(isFleetMachine)) {
    return { kind: "live", value: body, serverTs: body.checkedAt, httpStatus: r.status };
  }
  if (body && body.status === "unavailable" && typeof body.reason === "string") {
    const kind = FLEET_NOT_CONFIGURED.has(body.reason) ? "no_source" : "unreachable";
    return { kind, value: body, reason: body.reason, httpStatus: r.status };
  }
  const value: FleetView = { status: "unavailable", checkedAt: new Date().toISOString(), reason: "fleet read failed" };
  return { kind: "unreachable", value, reason: r.error ?? `HTTP ${r.status ?? "?"}`, httpStatus: r.status };
}

export async function readWall(signal: AbortSignal): Promise<FeedRead<WallSnapshot | null>> {
  const r = await getJson("/api/mesh-fleet/wall", signal);
  const body = record(r.body) as WallSnapshot | null;
  if (!r.ok || !body || !Array.isArray(body.stations) || !body.stations.every(isStation)
    || (Array.isArray(body.fleet?.machines) && !body.fleet.machines.every(isWallTile))) {
    return { kind: "unreachable", value: null, reason: r.error ?? `HTTP ${r.status ?? "?"}`, httpStatus: r.status };
  }
  const fleet = body.fleet?.status;
  // A live wall needs its clock and the fleet's machine list.
  if (fleet === "ok" && (typeof body.generated_at !== "string" || !Array.isArray(body.fleet.machines))) {
    return { kind: "unreachable", value: null, reason: "invalid wall payload", httpStatus: r.status };
  }
  // A failed wall still renders its fleet panel: it needs a text reason and a machine list.
  if (fleet !== "ok" && (typeof body.fleet?.reason !== "string" || !Array.isArray(body.fleet?.machines))) {
    return { kind: "unreachable", value: null, reason: "invalid wall payload", httpStatus: r.status };
  }
  if (fleet === "no_source") return { kind: "no_source", value: body, reason: body.fleet.reason, httpStatus: r.status };
  if (fleet !== "ok") return { kind: "unreachable", value: body, reason: body.fleet?.reason || "wall snapshot has no fleet status", httpStatus: r.status };
  return { kind: "live", value: body, serverTs: body.generated_at, httpStatus: r.status };
}

function isFabricStatus(b: FabricStatus): boolean {
  const t = b.totals;
  return typeof b.enabled === "boolean" && typeof b.healthy === "boolean" && Number.isFinite(b.models_available)
    && record(b.lanes) !== null && record(t) !== null
    && Number.isFinite(t?.calls) && Number.isFinite(t?.failures) && Number.isFinite(t?.fallbacks) && Number.isFinite(t?.strengthened);
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
  body.error = errorText(body.error, "invalid error field from /api/model-fabric");
  // A 200 without every field the panel shows (model_fabric.status_snapshot
  // always sends them) would render missing flags and counts as "DISABLED" and 0.
  if (r.ok && !body.error && !isFabricStatus(body)) {
    const error = "invalid model-fabric status payload";
    return { kind: "unreachable", value: { enabled: false, healthy: false, error }, reason: error, httpStatus: r.status };
  }
  // A non-2xx without an `error` field would otherwise render as "DISABLED" (ModelFabricPanel).
  if (!r.ok && !body.error) body.error = `HTTP ${r.status}`;
  return r.ok && !body.error
    ? { kind: "live", value: body, httpStatus: r.status }
    : { kind: "unreachable", value: body, reason: body.error ?? `HTTP ${r.status}`, httpStatus: r.status };
}

const SWARM_STATES = new Set<unknown>(["SHADOW", "ACTIVE", "RATE_LIMITED", "OFF", "UNKNOWN"]);
const countOrNull = (v: unknown) => v === null || (typeof v === "number" && Number.isFinite(v) && v >= 0);
const textOrNull = (v: unknown) => v === null || typeof v === "string";

function isSwarmStatus(d: NonNullable<SwarmValue["data"]>): boolean {
  return SWARM_STATES.has(d.state) && countOrNull(d.autonomous_prs_today) && countOrNull(d.autonomous_prs_limit)
    && countOrNull(d.green_merges) && countOrNull(d.green_merges_target)
    && textOrNull(d.last_pr_ts) && textOrNull(d.last_pr_url);
}

export async function readSwarmStatus(signal: AbortSignal): Promise<FeedRead<SwarmValue>> {
  const r = await getJson("/api/swarm-status", signal);
  if (r.error !== undefined) return { kind: "unreachable", value: { data: null, error: r.message ?? r.error }, reason: r.error };
  if (!r.ok) return { kind: "unreachable", value: { data: null, error: `HTTP ${r.status}` }, reason: `HTTP ${r.status}`, httpStatus: r.status };
  const data = record(r.body) as SwarmValue["data"];
  if (!data) return { kind: "unreachable", value: { data: null, error: "invalid JSON from /api/swarm-status" }, reason: "invalid JSON", httpStatus: r.status };
  // A 200 without a known state, or without every counter the panel shows
  // (app/api/swarm-status/route.ts always sends all seven), is a failed read.
  if (!isSwarmStatus(data)) {
    const error = "invalid swarm status payload";
    return { kind: "unreachable", value: { data: null, error }, reason: error, httpStatus: r.status };
  }
  // The route's own fallback is 200 with state UNKNOWN: a failed read, shown as the panel always showed it.
  const unknown = data.state === "UNKNOWN";
  return {
    kind: unknown ? "unreachable" : "live", value: { data, error: null },
    reason: unknown ? "swarm state unknown" : undefined, httpStatus: r.status,
  };
}

const isStringList = (v: unknown) => Array.isArray(v) && v.every((x) => typeof x === "string");

function isKillSwitchStatus(b: KillSwitchStatus): boolean {
  return typeof b.kill_switch_active === "boolean" && typeof b.swarm_enabled_env === "boolean"
    && typeof b.escalation_lock_active === "boolean" && Number.isFinite(b.panic_count_last_hour)
    && isStringList(b.approver_allowlist) && isStringList(b.approver_totp_configured);
}

export const SIGNED_OUT_REASON = "Signed out — sign in again (401)";

export async function readKillSwitch(signal: AbortSignal): Promise<FeedRead<KillSwitchStatus>> {
  const r = await getJson("/api/kill-switch?op=status", signal);
  if (r.error !== undefined) return { kind: "unreachable", value: { error: r.error }, reason: r.error };
  const body = (record(r.body) ?? {}) as KillSwitchStatus;
  body.error = errorText(body.error, "invalid error field from /api/kill-switch");
  // Every failed read carries an `error`, so the panel shows UNKNOWN, never a
  // "DISABLED" read off an empty or default body.
  if (!r.ok && !body.error) body.error = `HTTP ${r.status}`;
  if (r.status === 401) return { kind: "unreachable", value: body, reason: SIGNED_OUT_REASON, httpStatus: 401 };
  if (body.error) {
    const kind = isNotConfigured(body.error) ? "no_source" : "unreachable";
    return { kind, value: body, reason: body.error, httpStatus: r.status };
  }
  if (r.ok === false) return { kind: "unreachable", value: body, reason: `HTTP ${r.status}`, httpStatus: r.status };
  // A 200 that is not JSON, or lacks any field the panel shows (the backend,
  // routes/swarm.py, always sends all six), is a failed read: shown as
  // UNKNOWN, never as an invented "DISABLED", "no" lock or "0 / 0" approvers.
  if (!isKillSwitchStatus(body)) {
    const error = "invalid kill-switch status payload";
    return { kind: "unreachable", value: { error }, reason: error, httpStatus: r.status };
  }
  return { kind: "live", value: body, httpStatus: r.status };
}

export async function readProviderUsage(signal: AbortSignal): Promise<FeedRead<ProviderUsageValue>> {
  const r = await getJson("/api/command-centre/provider-usage", signal);
  const body = record(r.body);
  if (!r.ok || !body) return { kind: "unreachable", value: null, reason: r.error ?? `provider_usage_http_${r.status}`, httpStatus: r.status };
  if (typeof body.generatedAt !== "string" || !Array.isArray(body.providers)) {
    return { kind: "unreachable", value: null, reason: "provider usage payload is not in the expected shape", httpStatus: r.status };
  }
  const payload = body as unknown as NonNullable<ProviderUsageValue>;
  return { kind: "live", value: payload, serverTs: payload.generatedAt, httpStatus: r.status };
}

export async function readWikiGraph(signal: AbortSignal): Promise<FeedRead<WikiGraphSummary | null>> {
  const r = await getJson("/api/command-centre/wiki-graph", signal);
  const body = record(r.body);
  if (!r.ok || !body) return { kind: "unreachable", value: null, reason: r.error ?? `HTTP ${r.status}`, httpStatus: r.status };
  // The route always sends both counts and a source; without them the tile would show zeros as live.
  if (!Number.isFinite(body.pageCount) || !Number.isFinite(body.edgeCount) || typeof body.source !== "string") {
    return { kind: "unreachable", value: null, reason: "invalid wiki graph payload", httpStatus: r.status };
  }
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

const PROPOSAL_TEXT_FIELDS = ["proposal_id", "cluster_id", "cluster_summary", "trigger_source", "proposed_skill_name", "draft_id", "evidence_count"] as const;

function isCuratorList(b: CuratorValue): boolean {
  const counts = record(b.by_status);
  return Array.isArray(b.proposals) && counts !== null && Object.values(counts).every((n) => Number.isFinite(n))
    && b.proposals.every((p) => {
      const row = record(p);
      return row !== null && isText(row.ts) && PROPOSAL_TEXT_FIELDS.every((k) => isRenderable(row[k]));
    });
}

export const CURATOR_URL = "/api/curator-proposals?status=pending&limit=10";

export async function readCurator(signal: AbortSignal): Promise<FeedRead<CuratorValue>> {
  const r = await getJson(CURATOR_URL, signal);
  if (r.error !== undefined) return { kind: "unreachable", value: { error: r.error }, reason: r.error };
  const body = (record(r.body) ?? {}) as CuratorValue;
  body.error = errorText(body.error, "invalid error field from /api/curator-proposals");
  // A failed read must never render as "No pending proposals" (CuratorProposalsPanel).
  if (!r.ok && !body.error) body.error = `HTTP ${r.status}`;
  if (body.error) {
    const kind = isNotConfigured(body.error) ? "no_source" : "unreachable";
    return { kind, value: body, reason: body.error, httpStatus: r.status };
  }
  // A 200 without a proposals list, or with counts or rows the panel cannot
  // render, must never show as "No pending proposals" (routes/swarm.py always
  // sends by_status counts and rows with a ts).
  if (!isCuratorList(body)) {
    const error = "invalid curator proposals payload";
    return { kind: "unreachable", value: { error }, reason: error, httpStatus: r.status };
  }
  return { kind: "live", value: body, httpStatus: r.status };
}

export const DIRECT_FEEDS: FeedDef<unknown>[] = [
  defineFeed({ id: "mesh-fleet", url: "/api/mesh-fleet", intervalMs: 20_000, read: readMeshFleet, serverClock: true,
    failed: (reason): FleetView => ({ status: "unavailable", checkedAt: new Date().toISOString(), reason }) }),
  defineFeed({ id: "wall", url: "/api/mesh-fleet/wall", intervalMs: 5_000, read: readWall, serverClock: true }),
  defineFeed({ id: "model-fabric", url: "/api/model-fabric", intervalMs: 15_000, read: readModelFabric,
    failed: (error): FabricStatus => ({ enabled: false, healthy: false, error }) }),
  defineFeed({ id: "swarm-status", url: "/api/swarm-status", intervalMs: 30_000, read: readSwarmStatus,
    failed: (error): SwarmValue => ({ data: null, error }) }),
  defineFeed({ id: "kill-switch", url: "/api/kill-switch?op=status", intervalMs: 10_000, read: readKillSwitch,
    failed: (error): KillSwitchStatus => ({ error }) }),
  defineFeed({ id: "provider-usage", url: "/api/command-centre/provider-usage", intervalMs: 30_000, read: readProviderUsage, serverClock: true }),
  defineFeed({ id: "wiki-graph", url: "/api/command-centre/wiki-graph", intervalMs: 300_000, read: readWikiGraph }),
  defineFeed({ id: "curator", url: CURATOR_URL, intervalMs: 30_000, read: readCurator,
    failed: (error): CuratorValue => ({ error }) }),
];
