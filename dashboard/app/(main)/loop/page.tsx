// app/(main)/loop/page.tsx — Loop Cockpit (RA-6862)
// Read-only surface for the autonomous loop that previously had NO dashboard
// coverage: the autonomy poller, the RA-6670 P3 burndown, and the swarm. Composes
// existing endpoints via the /api/pi-ceo/* proxy — no new backend, no write actions
// (kill-switch / gate-approval buttons are Phase 2, gated on proxy-auth review).
"use client";

import { useCallback, useEffect, useState } from "react";

const POLL_MS = 20_000;

// ── Response shapes (partial / defensive — every field optional, fail-soft) ──
interface AutonomyStatus {
  enabled: boolean;
  poll_interval_s: number;
  last_poll_at: number | null;
  last_poll_ago_s: number | null;
  stale: boolean;
  poll_count: number;
  poller_iteration_errors: number;
  last_iteration_error: string | null;
}

interface MCSession { id: string; repo?: string; phase?: string; elapsed_s?: number; issue_id?: string | null }
interface MCCompletion { id: string; repo?: string; branch?: string; score?: number; pr_url?: string | null; completed_at?: string }
interface MissionControl {
  throughput?: { hourly?: number[] };
  active_sessions?: MCSession[];
  recent_completions?: MCCompletion[];
  queue?: { urgent?: number; high?: number; next_issue_id?: string | null };
  observability?: { fully_observed?: boolean; degraded_components?: string[]; actions?: string[] };
  ts?: string;
}

interface SwarmStatus {
  swarm_enabled_env?: boolean;
  kill_switch_active?: boolean;
  escalation_lock_active?: boolean;
  panic_count_last_hour?: number;
  pr_quota?: { used?: number; limit?: number };
}

interface RoutineRun { ts?: string; name?: string; status?: string; ok?: boolean }
interface RoutinesResp { runs?: RoutineRun[]; total?: number }

async function getJSON<T>(path: string): Promise<T | null> {
  try {
    const res = await fetch(`/api/pi-ceo${path}`);
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  }
}

function agoLabel(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return "never";
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m ago`;
  return `${Math.round(seconds / 3600)}h ago`;
}

function Dot({ color }: { color: string }) {
  return <span className="w-1.5 h-1.5 rounded-full shrink-0 inline-block" style={{ background: color }} />;
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section
      className="flex flex-col min-h-0"
      style={{ background: "var(--panel)", border: "1px solid var(--border)", borderRadius: 8 }}
      aria-label={title}
    >
      <header className="px-4 py-2.5" style={{ borderBottom: "1px solid var(--border)" }}>
        <h2 className="text-xs font-semibold uppercase tracking-widest" style={{ color: "var(--text-muted)" }}>
          {title}
        </h2>
      </header>
      <div className="flex-1 overflow-auto p-4 flex flex-col gap-2 min-h-0">{children}</div>
    </section>
  );
}

function Row({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="flex items-center justify-between gap-3 text-sm">
      <span style={{ color: "var(--text-muted)" }}>{label}</span>
      <span className="font-medium tabular-nums" style={{ color: color ?? "var(--text)" }}>{value}</span>
    </div>
  );
}

export default function LoopPage() {
  const [autonomy, setAutonomy] = useState<AutonomyStatus | null>(null);
  const [mc, setMc] = useState<MissionControl | null>(null);
  const [swarm, setSwarm] = useState<SwarmStatus | null>(null);
  const [routines, setRoutines] = useState<RoutinesResp | null>(null);
  const [lastSync, setLastSync] = useState<string>("—");

  const refresh = useCallback(async () => {
    const [a, m, s, r] = await Promise.all([
      getJSON<AutonomyStatus>("/api/autonomy/status"),
      getJSON<MissionControl>("/api/mission-control/live"),
      getJSON<SwarmStatus>("/api/swarm/status"),
      getJSON<RoutinesResp>("/api/routines?limit=20"),
    ]);
    setAutonomy(a);
    setMc(m);
    setSwarm(s);
    setRoutines(r);
    setLastSync(new Date().toLocaleTimeString());
  }, []);

  useEffect(() => {
    void refresh();
    const t = setInterval(() => { void refresh(); }, POLL_MS);
    return () => clearInterval(t);
  }, [refresh]);

  // ── "Needs me" — read-only flags derived from live state ──
  const needs: { text: string; color: string }[] = [];
  if (swarm?.kill_switch_active) needs.push({ text: "Kill-switch is ACTIVE — autonomous work is paused", color: "var(--error)" });
  if (swarm?.escalation_lock_active) needs.push({ text: "Escalation lock is active — awaiting approver", color: "var(--warning)" });
  if (autonomy && autonomy.enabled && autonomy.stale) needs.push({ text: "Autonomy poller is stale (>15m since last poll)", color: "var(--warning)" });
  if (autonomy && !autonomy.enabled) needs.push({ text: "Autonomy poller is disabled (TAO_AUTONOMY_ENABLED=0)", color: "var(--warning)" });
  if (autonomy && autonomy.poller_iteration_errors > 0) needs.push({ text: `Poller has ${autonomy.poller_iteration_errors} iteration error(s)${autonomy.last_iteration_error ? `: ${autonomy.last_iteration_error}` : ""}`, color: "var(--error)" });
  for (const a of mc?.observability?.actions ?? []) needs.push({ text: a, color: "var(--warning)" });
  if (mc?.queue?.next_issue_id) needs.push({ text: `Next queued ticket: ${mc.queue.next_issue_id}`, color: "var(--text-muted)" });

  // All four fetches null = we never reached the backend (unauthenticated or
  // backend down). Absent data must NOT read as "healthy".
  const disconnected = !autonomy && !mc && !swarm && !routines;

  const burndownRuns = (routines?.runs ?? []).filter((r) => (r.name ?? "").toLowerCase().includes("burndown"));
  const hourly = mc?.throughput?.hourly ?? [];
  const completed24h = hourly.reduce((acc, n) => acc + (n || 0), 0);

  return (
    <div className="flex flex-col" style={{ height: "100vh", overflow: "hidden" }}>
      {/* Header */}
      <header
        className="flex items-center justify-between px-4 h-[52px] shrink-0"
        style={{ background: "var(--panel)", borderBottom: "1px solid var(--border)" }}
      >
        <div className="flex items-center gap-2">
          <span className="font-mono text-base" style={{ color: "var(--accent)" }}>∞</span>
          <h1 className="text-sm font-semibold" style={{ color: "var(--text)" }}>Loop Cockpit</h1>
          <span className="text-xs" style={{ color: "var(--text-dim)" }}>the autonomous system, live</span>
        </div>
        <span className="text-xs tabular-nums" style={{ color: "var(--text-dim)" }}>synced {lastSync}</span>
      </header>

      <div className="flex-1 overflow-auto p-4 flex flex-col gap-4" style={{ minHeight: 0 }}>
        {/* Needs me */}
        <section
          className="flex flex-col gap-2 p-4"
          style={{
            background: "var(--panel)",
            border: `1px solid ${disconnected ? "var(--error)" : needs.length ? "var(--warning)" : "var(--border)"}`,
            borderRadius: 8,
          }}
          aria-label="Needs me"
        >
          <div className="flex items-center gap-2">
            <Dot color={disconnected ? "var(--error)" : needs.length ? "var(--warning)" : "var(--success)"} />
            <h2 className="text-xs font-semibold uppercase tracking-widest" style={{ color: "var(--text-muted)" }}>
              Needs me
            </h2>
          </div>
          {disconnected ? (
            <p className="text-sm" style={{ color: "var(--text)" }}>
              Disconnected — not authenticated or the Pi-CEO backend is unreachable, so live data is unavailable. Log in to populate the cockpit.
            </p>
          ) : needs.length === 0 ? (
            <p className="text-sm" style={{ color: "var(--text-muted)" }}>
              Nothing needs you — the loop is healthy.
            </p>
          ) : (
            <ul className="flex flex-col gap-1.5">
              {needs.map((n, i) => (
                <li key={i} className="flex items-start gap-2 text-sm">
                  <span className="mt-1.5"><Dot color={n.color} /></span>
                  <span style={{ color: "var(--text)" }}>{n.text}</span>
                </li>
              ))}
            </ul>
          )}
        </section>

        {/* Panels grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4 auto-rows-[minmax(220px,1fr)]">
          {/* Autonomy poller */}
          <Panel title="Autonomy Poller">
            {autonomy ? (
              <>
                <Row label="Status" value={autonomy.enabled ? "Enabled" : "Disabled"} color={autonomy.enabled ? "var(--success)" : "var(--error)"} />
                <Row label="Last poll" value={agoLabel(autonomy.last_poll_ago_s)} color={autonomy.stale ? "var(--warning)" : undefined} />
                <Row label="Interval" value={`${autonomy.poll_interval_s}s`} />
                <Row label="Polls run" value={String(autonomy.poll_count)} />
                <Row label="Iteration errors" value={String(autonomy.poller_iteration_errors)} color={autonomy.poller_iteration_errors ? "var(--error)" : undefined} />
              </>
            ) : (
              <p className="text-sm" style={{ color: "var(--text-dim)" }}>No autonomy data.</p>
            )}
          </Panel>

          {/* Swarm & kill-switch */}
          <Panel title="Swarm & Kill-Switch">
            {swarm ? (
              <>
                <Row label="Swarm" value={swarm.swarm_enabled_env ? "Enabled" : "Off"} color={swarm.swarm_enabled_env ? "var(--success)" : "var(--text-muted)"} />
                <Row label="Kill-switch" value={swarm.kill_switch_active ? "ACTIVE" : "Clear"} color={swarm.kill_switch_active ? "var(--error)" : "var(--success)"} />
                <Row label="Escalation lock" value={swarm.escalation_lock_active ? "Locked" : "Open"} color={swarm.escalation_lock_active ? "var(--warning)" : undefined} />
                <Row label="Panics (1h)" value={String(swarm.panic_count_last_hour ?? 0)} color={swarm.panic_count_last_hour ? "var(--warning)" : undefined} />
                <Row label="PR quota" value={`${swarm.pr_quota?.used ?? 0} / ${swarm.pr_quota?.limit ?? 0}`} />
              </>
            ) : (
              <p className="text-sm" style={{ color: "var(--text-dim)" }}>No swarm data.</p>
            )}
          </Panel>

          {/* Queue & throughput */}
          <Panel title="Queue & Throughput">
            <Row label="Urgent queued" value={String(mc?.queue?.urgent ?? 0)} color={(mc?.queue?.urgent ?? 0) > 0 ? "var(--warning)" : undefined} />
            <Row label="High queued" value={String(mc?.queue?.high ?? 0)} />
            <Row label="Next ticket" value={mc?.queue?.next_issue_id ?? "—"} />
            <Row label="Completed (24h)" value={String(completed24h)} color={completed24h > 0 ? "var(--success)" : undefined} />
            <Row label="Active sessions" value={String(mc?.active_sessions?.length ?? 0)} />
          </Panel>

          {/* Active sessions */}
          <Panel title="Active Sessions">
            {(mc?.active_sessions?.length ?? 0) === 0 ? (
              <p className="text-sm" style={{ color: "var(--text-dim)" }}>No sessions running.</p>
            ) : (
              (mc?.active_sessions ?? []).map((s) => (
                <div key={s.id} className="flex items-center justify-between gap-2 text-sm">
                  <span className="truncate" style={{ color: "var(--text)" }}>{s.repo ?? s.id}</span>
                  <span className="shrink-0 tabular-nums" style={{ color: "var(--text-muted)" }}>
                    {s.phase ?? "?"}{s.elapsed_s ? ` · ${Math.round(s.elapsed_s / 60)}m` : ""}
                  </span>
                </div>
              ))
            )}
          </Panel>

          {/* Burndown + recent loop runs */}
          <Panel title="Loop Runs (incl. RA-6670 burndown)">
            {burndownRuns.length > 0 && (
              <div className="flex items-center gap-2 text-sm pb-1" style={{ borderBottom: "1px solid var(--border)" }}>
                <Dot color="var(--accent)" />
                <span style={{ color: "var(--text)" }}>
                  Burndown: last run {burndownRuns[0].status ?? (burndownRuns[0].ok ? "ok" : "?")}
                  {burndownRuns[0].ts ? ` · ${new Date(burndownRuns[0].ts).toLocaleString()}` : ""}
                </span>
              </div>
            )}
            {(routines?.runs?.length ?? 0) === 0 ? (
              <p className="text-sm" style={{ color: "var(--text-dim)" }}>No recent runs.</p>
            ) : (
              (routines?.runs ?? []).slice(0, 10).map((r, i) => (
                <div key={`${r.name ?? "run"}-${i}`} className="flex items-center justify-between gap-2 text-sm">
                  <span className="truncate" style={{ color: "var(--text)" }}>{r.name ?? "run"}</span>
                  <span className="shrink-0" style={{ color: (r.status === "ok" || r.ok) ? "var(--success)" : "var(--text-muted)" }}>
                    {r.status ?? (r.ok ? "ok" : "—")}
                  </span>
                </div>
              ))
            )}
          </Panel>

          {/* Recent completions */}
          <Panel title="Recent Completions">
            {(mc?.recent_completions?.length ?? 0) === 0 ? (
              <p className="text-sm" style={{ color: "var(--text-dim)" }}>No completions yet.</p>
            ) : (
              (mc?.recent_completions ?? []).slice(0, 8).map((c) => (
                <div key={c.id} className="flex items-center justify-between gap-2 text-sm">
                  <span className="truncate" style={{ color: "var(--text)" }}>{c.repo ?? c.id}</span>
                  <span className="shrink-0 tabular-nums" style={{ color: "var(--text-muted)" }}>
                    {c.score !== undefined ? `${c.score}` : ""}{c.pr_url ? " · PR" : ""}
                  </span>
                </div>
              ))
            )}
          </Panel>
        </div>
      </div>
    </div>
  );
}
