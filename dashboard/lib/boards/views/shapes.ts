// RA-7898 — pure shaping for the second views. No fetch, no React. Every
// function returns null when the payload is not the expected shape, so a
// view can say "unexpected payload" instead of drawing zeros.

import type { FleetView } from "@/lib/control/mesh-fleet";
import type { IdeaPacket, IdeaPipelinePayload } from "@/lib/control/idea-pipeline";
import { completed24h, type MissionControlLive } from "@/lib/control/mission-control-live";
import type { FabricStatus } from "@/lib/boards/sources/shapes";
import type { Station } from "@/lib/wall/snapshot";
import { toEpochMs } from "@/lib/boards/sources/types";

export type Tone = "ok" | "warn" | "bad" | "idle" | "none";

export interface FleetRow { host: string; heardMs: number | null; stale: boolean; claim: string | null; revision: string | null }

export function fleetRows(view: FleetView | null): FleetRow[] | null {
  if (!view || view.status !== "ok" || !Array.isArray(view.machines)) return null;
  return view.machines.map((m) => ({
    host: m.host, heardMs: toEpochMs(m.lastHeartbeat), stale: m.stale, claim: m.currentClaim, revision: m.revision,
  }));
}

export const CHIP_TONE: Record<Station["chip"], Tone> = { GREEN: "ok", RED: "bad", GREY: "none" };

export function stationCounts(stations: readonly Station[]): { green: number; red: number; grey: number } {
  return {
    green: stations.filter((s) => s.chip === "GREEN").length,
    red: stations.filter((s) => s.chip === "RED").length,
    grey: stations.filter((s) => s.chip === "GREY").length,
  };
}

export interface ActivityEvent { key: string; text: string; atMs: number | null; tone: Tone; meta: string }

export function activityEvents(live: MissionControlLive | null): ActivityEvent[] | null {
  if (!live || live.error) return null;
  const running = (live.active_sessions ?? []).map((s) => ({
    key: `run-${s.id}`, text: `${s.repo ?? "unknown repo"} — ${s.phase ?? s.status ?? "running"}`,
    atMs: typeof s.elapsed_s === "number" ? Date.now() - s.elapsed_s * 1000 : null, tone: "warn" as Tone,
    meta: s.issue_id ?? "running",
  }));
  const done = (live.recent_completions ?? []).map((c) => ({
    key: `done-${c.id}`, text: `${c.repo ?? "unknown repo"} completed${c.score != null ? ` · score ${c.score}` : ""}`,
    atMs: toEpochMs(c.completed_at ?? null), tone: "ok" as Tone, meta: c.issue_id ?? c.branch ?? "completed",
  }));
  return [...running, ...done].sort((a, b) => (b.atMs ?? 0) - (a.atMs ?? 0));
}

export function pulse(live: MissionControlLive | null): { total: number; hourly: number[] } | null {
  const hourly = live?.throughput?.hourly;
  if (!live || live.error || !Array.isArray(hourly)) return null;
  return { total: completed24h(hourly), hourly: hourly.map((n) => (Number.isFinite(n) ? n : 0)) };
}

export interface FabricBar { label: string; value: number }

export function fabricTotals(status: FabricStatus | null): FabricBar[] | null {
  const t = status?.totals;
  if (!status || status.error || !t || typeof t.calls !== "number") return null;
  return [
    { label: "Calls", value: t.calls },
    { label: "Failures", value: t.failures ?? 0 },
    { label: "Fallbacks", value: t.fallbacks ?? 0 },
    { label: "Strengthened", value: t.strengthened ?? 0 },
  ];
}

export function fabricLanes(status: FabricStatus | null): { lane: string; model: string; banned: boolean }[] | null {
  if (!status || status.error || !status.lanes) return null;
  return Object.entries(status.lanes).map(([lane, l]) => ({ lane, model: l.model, banned: l.banned }));
}

export interface ScoredProject { id: string; repo: string; score: number | null }

/** A project's scan score, or null when no scan produced one (never the scanner's default). */
export function scoredProjects(value: unknown): ScoredProject[] | null {
  if (!Array.isArray(value)) return null;
  const out: ScoredProject[] = [];
  for (const raw of value) {
    const p = raw as { project_id?: unknown; repo?: unknown; overall_health?: unknown; scores?: unknown };
    if (typeof p?.project_id !== "string" || typeof p.repo !== "string") continue;
    const scores = p.scores && typeof p.scores === "object" ? Object.values(p.scores as Record<string, unknown>) : [];
    const measured = scores.some((v) => typeof v === "number" && Number.isFinite(v));
    const score = measured && typeof p.overall_health === "number" && Number.isFinite(p.overall_health) ? p.overall_health : null;
    out.push({ id: p.project_id, repo: p.repo, score });
  }
  return out.sort((a, b) => (b.score ?? -1) - (a.score ?? -1));
}

export const WEAK_SCORE = 65;

function packetsOf(payload: IdeaPipelinePayload | null): IdeaPacket[] | null {
  if (!payload || !payload.snapshot) return null;
  if (Array.isArray(payload.packets)) return payload.packets;
  return payload.snapshot.packet ? [payload.snapshot.packet] : [];
}

export function ideaFunnel(payload: IdeaPipelinePayload | null): { stage: string; count: number }[] | null {
  const packets = packetsOf(payload);
  if (!packets) return null;
  return [
    { stage: "Captured", count: packets.length },
    { stage: "Decided", count: packets.filter((p) => p.verdict).length },
    { stage: "Promoted", count: packets.filter((p) => p.verdict === "PROMOTE").length },
    { stage: "GO given", count: packets.filter((p) => p.go_at).length },
    { stage: "Executed", count: packets.filter((p) => p.executed).length },
  ];
}

export function ideaInbox(payload: IdeaPipelinePayload | null): { id: string; text: string; source: string }[] | null {
  const packets = packetsOf(payload);
  if (!packets) return null;
  return packets.filter((p) => !p.verdict).map((p) => ({ id: p.idea_id, text: p.text, source: p.source }));
}
