// LiveActivityFeed.tsx — Mission Control live autonomy view (RA-1440).
// Polls /api/pi-ceo/api/mission-control/live every 5s and renders:
//   • 24h throughput sparkline
//   • Currently running sessions (phase, elapsed, repo)
//   • Recent completions (score, branch, PR link)
//   • Linear queue depth + next-up ticket
//   • Pulse status (last heartbeat, comments today)
//   • Observability action ledger for not-yet-live components
"use client";

import { useEffect, useState } from "react";

import ThroughputSparkline from "./ThroughputSparkline";
import ClaudeSessionsHUD, { type ClaudeHud } from "./ClaudeSessionsHUD";
import { LiveDot, PhasePill } from "./LiveFeedMarks";
import LiveWatchLinks from "./LiveWatchLinks";
import { fetchProxyJSON } from "@/lib/pi-ceo-fetch";
import { fmtElapsed, fmtAgo } from "@/lib/control/activity-format";
import { idleSessionsNote, watchBuildsHref, watchLoopHref, watchSwarmHref } from "@/lib/control/watchWork";

// ── Types ─────────────────────────────────────────────────────────────────
interface LiveData {
  ts: string;
  error?: string;
  // The backend key is `hourly` (app/server/routes/mission_control.py). This read
  // `hourly_24h`, which only the proxy's offline fallback ever produced — so the
  // panel rendered when the backend was down and threw when it was up. Optional so
  // a partial payload degrades instead of taking the cockpit down.
  throughput?: { hourly?: number[] };
  active_sessions: Array<{
    id: string;
    repo: string;
    phase: string;
    status: string;
    elapsed_s: number;
    issue_id: string | null;
    last_log_tail: string;
  }>;
  recent_completions: Array<{
    id: string;
    repo: string;
    branch: string | null;
    score: number | null;
    pr_url: string | null;
    issue_id: string | null;
    completed_at: string | null;
  }>;
  queue: {
    urgent: number;
    high: number;
    next_issue_id: string | null;
    next_issue_title: string;
  };
  pulse: {
    last_at: string | null;
    comments_today: number;
    pulse_issue_id: string | null;
  };
  claude_hud?: ClaudeHud;
  observability?: {
    source: string;
    ok: boolean;
    fully_observed: boolean;
    red_components: string[];
    degraded_components: string[];
    actions: Array<{
      component: string;
      status: string;
      ok: boolean;
      observed: boolean;
      owner: string;
      severity: string;
      next_action: string;
      evidence_required: string[];
      detail: string | null;
    }>;
  };
}

export default function LiveActivityFeed() {
  const [data, setData] = useState<LiveData | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [lastUpdate, setLastUpdate] = useState<number>(0);
  // `now` is the component's idempotent view of wall-clock time. Calling
  // Date.now() directly in render violates React's components-must-be-pure
  // rule — the render would see a different value on every re-render even
  // with identical props/state. Storing it in state and ticking once a
  // second keeps render deterministic for any given commit.
  const [now, setNow] = useState<number>(() => Date.now());

  useEffect(() => {
    let mounted = true;
    const tick = async () => {
      try {
        // See lib/pi-ceo-fetch.ts — a proxy fallback is not a live reading.
        const j = await fetchProxyJSON<LiveData>("/api/mission-control/live", {
          credentials: "include",
          cache: "no-store",
        });
        if (!j) {
          if (mounted) setErr("Pi-CEO backend unreachable");
          return;
        }
        if (mounted) {
          setData(j);
          if (j.error) {
            setLastUpdate(0);
            setErr(j.error);
          } else {
            setLastUpdate(Date.now());
            setErr(null);
          }
        }
      } catch (e) {
        if (mounted) setErr(String(e));
      }
    };
    tick();
    const id = setInterval(tick, 5000);
    return () => {
      mounted = false;
      clearInterval(id);
    };
  }, []);

  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);

  const isLive = lastUpdate > 0 && now - lastUpdate < 15000;

  if (!data && !err) {
    return (
      <div className="rounded-lg border border-slate-700/50 bg-slate-900/50 p-6 backdrop-blur-sm">
        <div className="animate-pulse text-text-muted">Loading Mission Control…</div>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-slate-700/50 bg-gradient-to-br from-slate-900/80 to-slate-950/80 backdrop-blur-sm">
      {/* Header */}
      <div className="border-b border-slate-800 p-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <LiveDot active={isLive} />
          <h2 className="text-lg font-semibold text-slate-100">Mission Control</h2>
          <span className="text-xs text-text-muted">
            {err ? `⚠ ${err}` : isLive ? "live · polling 5s" : "stalled"}
          </span>
        </div>
        {data && !err && (
          <span className="text-xs text-text-muted tabular-nums">
            updated {fmtAgo(data.ts)}
          </span>
        )}
      </div>
      {data && !err ? (
        <div className="px-4 py-2 border-b border-slate-800">
          <LiveWatchLinks hasPr={data.recent_completions.some((c) => Boolean(c.pr_url))} />
        </div>
      ) : null}

      {/* Stats grid */}
      {data && (
        <>
          <ClaudeSessionsHUD data={data.claude_hud} />
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 p-4 border-b border-slate-800">
            {/* Throughput */}
            <div>
              <div className="text-xs uppercase text-text-muted mb-1">24h throughput</div>
              <ThroughputSparkline data={data.throughput?.hourly ?? []} />
            </div>

            {/* Queue */}
            <div>
              <div className="text-xs uppercase text-text-muted mb-1">Linear queue</div>
              <div className="flex items-baseline gap-3">
                <div>
                  <span className="text-3xl font-bold text-rose-400 tabular-nums">
                    {data.queue.urgent}
                  </span>
                  <span className="text-xs text-text-muted ml-1">urgent</span>
                </div>
                <div>
                  <span className="text-2xl font-semibold text-amber-400 tabular-nums">
                    {data.queue.high}
                  </span>
                  <span className="text-xs text-text-muted ml-1">high</span>
                </div>
              </div>
              {data.queue.next_issue_id && (
                <div className="text-xs text-text-muted mt-2 truncate">
                  next:{" "}
                  <a href={watchLoopHref()} className="font-mono text-cyan-400 hover:underline">
                    {data.queue.next_issue_id}
                  </a>{" "}
                  {data.queue.next_issue_title}
                </div>
              )}
            </div>

            {/* Pulse */}
            <div>
              <div className="text-xs uppercase text-text-muted mb-1">Pulse heartbeat</div>
              <div className="flex items-baseline gap-2">
                <span className="text-3xl font-bold text-emerald-400 tabular-nums">
                  {data.pulse.comments_today}
                </span>
                <span className="text-xs text-text-muted">comments today</span>
              </div>
              <div className="text-xs text-text-muted mt-1">
                last: <span className="font-mono">{fmtAgo(data.pulse.last_at)}</span>
                {data.pulse.pulse_issue_id && (
                  <span className="ml-2 text-text-muted">
                    → {data.pulse.pulse_issue_id}
                  </span>
                )}
              </div>
            </div>
          </div>

          {/* Observability action ledger */}
          {data.observability && (
            <div className="p-4 border-b border-slate-800">
              <div className="flex items-center justify-between gap-3 mb-2">
                <div className="text-xs uppercase text-text-muted">
                  Observability readiness
                </div>
                <span
                  className={`px-2 py-0.5 rounded border text-xs font-mono ${
                    data.observability.fully_observed
                      ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/40"
                      : data.observability.ok
                        ? "bg-amber-500/20 text-amber-300 border-amber-500/40"
                        : "bg-rose-500/20 text-rose-300 border-rose-500/40"
                  }`}
                >
                  {data.observability.fully_observed
                    ? "fully observed"
                    : data.observability.ok
                      ? "degraded"
                      : "red"}
                </span>
              </div>
              {data.observability.actions.length === 0 ? (
                <div className="text-sm text-emerald-400">
                  All companion signals observed.
                </div>
              ) : (
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-2">
                  {data.observability.actions.map((action) => (
                    <div
                      key={action.component}
                      className="rounded border border-slate-800 bg-slate-900/40 p-3"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <div className="font-mono text-xs text-cyan-300">
                            {action.component}
                          </div>
                          <div className="text-xs text-text-muted">
                            {action.owner} · {action.status}
                          </div>
                        </div>
                        <span
                          className={`px-1.5 py-0.5 rounded text-[11px] font-mono ${
                            action.severity === "high"
                              ? "bg-rose-500/20 text-rose-300"
                              : "bg-amber-500/20 text-amber-300"
                          }`}
                        >
                          {action.severity}
                        </span>
                      </div>
                      <p className="text-sm text-slate-200 mt-2">
                        {action.next_action}
                      </p>
                      <div className="text-xs text-text-muted mt-2">
                        evidence: {action.evidence_required.join(", ")}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Active sessions */}
          <div className="p-4 border-b border-slate-800">
            <div className="text-xs uppercase text-text-muted mb-2 flex items-center gap-2">
              Active sessions
              <span className="px-1.5 py-0.5 bg-slate-800 rounded text-slate-300 tabular-nums">
                {data.active_sessions.length}
              </span>
            </div>
            {data.active_sessions.length === 0 ? (
              <div className="text-sm text-text-muted italic">
                {idleSessionsNote({
                  sessionCount: 0,
                  urgent: data.queue.urgent,
                  high: data.queue.high,
                  nextIssueId: data.queue.next_issue_id,
                })}
              </div>
            ) : (
              <div className="space-y-2">
                {data.active_sessions.map((s) => (
                  <div
                    key={s.id}
                    className="flex items-center gap-3 py-2 px-3 rounded bg-slate-900/50 border border-slate-800"
                  >
                    <LiveDot active={true} />
                    <a href={watchBuildsHref()} className="font-mono text-xs text-cyan-400 hover:underline">
                      {s.id}
                    </a>
                    <PhasePill phase={s.phase || s.status} />
                    <span className="text-sm text-slate-200 font-medium">
                      {s.repo}
                    </span>
                    {s.issue_id && (
                      <span className="text-xs text-cyan-400 font-mono">
                        {s.issue_id}
                      </span>
                    )}
                    <span className="ml-auto text-xs text-text-muted tabular-nums">
                      {fmtElapsed(s.elapsed_s)}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Recent completions */}
          <div className="p-4">
            <div className="text-xs uppercase text-text-muted mb-2">
              Recent completions
            </div>
            {data.recent_completions.length === 0 ? (
              <div className="text-sm text-text-muted italic">
                No completions yet — first session in flight.
              </div>
            ) : (
              <div className="space-y-1.5">
                {data.recent_completions.map((c) => (
                  <div
                    key={c.id}
                    className="flex items-center gap-3 py-1.5 px-3 rounded bg-slate-900/30 text-xs"
                  >
                    <span className="text-emerald-400">✓</span>
                    <span className="font-mono text-text-muted">{c.id}</span>
                    <span className="text-slate-200 font-medium">{c.repo}</span>
                    {c.branch && (
                      <span className="text-text-muted font-mono truncate max-w-[200px]">
                        {c.branch}
                      </span>
                    )}
                    {c.score !== null && c.score !== undefined && (
                      <span
                        className={`px-1.5 py-0.5 rounded tabular-nums ${
                          c.score >= 8
                            ? "bg-emerald-500/20 text-emerald-300"
                            : c.score >= 6
                              ? "bg-amber-500/20 text-amber-300"
                              : "bg-rose-500/20 text-rose-300"
                        }`}
                      >
                        {c.score}/10
                      </span>
                    )}
                    {c.pr_url && (
                      <>
                        <a
                          href={c.pr_url}
                          target="_blank"
                          rel="noreferrer"
                          className="text-cyan-400 hover:underline ml-auto"
                        >
                          PR →
                        </a>
                        <a href={watchSwarmHref()} className="text-cyan-400 hover:underline">
                          Swarm
                        </a>
                      </>
                    )}
                    <span className="text-text-muted tabular-nums">
                      {fmtAgo(c.completed_at)}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
