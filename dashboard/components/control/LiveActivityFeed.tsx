// LiveActivityFeed.tsx — Mission Control live autonomy view (RA-1440).
// Polls /api/pi-ceo/api/mission-control/live every 5s and renders:
//   • 24h throughput sparkline
//   • Currently running sessions (phase, elapsed, repo)
//   • Recent completions (score, branch, PR link)
//   • Linear queue depth + next-up ticket
//   • Pulse status (last heartbeat, comments today)
"use client";

import { useEffect, useState } from "react";

// ── Types ─────────────────────────────────────────────────────────────────
interface LiveData {
  ts: string;
  throughput: { hourly_24h: number[] };
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
}

// ── Formatters ────────────────────────────────────────────────────────────
function fmtElapsed(s: number): string {
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m ${s % 60}s`;
  return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`;
}

function fmtAgo(iso: string | null): string {
  if (!iso) return "never";
  const ms = Date.now() - new Date(iso).getTime();
  if (ms < 0) return "just now";
  const s = Math.floor(ms / 1000);
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  return `${Math.floor(s / 3600)}h ago`;
}

// ── Sparkline (SVG, no deps) ──────────────────────────────────────────────
function Sparkline({ data }: { data: number[] }) {
  const w = 200;
  const h = 40;
  const max = Math.max(...data, 1);
  const step = w / (data.length - 1 || 1);
  const points = data
    .map((v, i) => `${(i * step).toFixed(1)},${(h - (v / max) * h).toFixed(1)}`)
    .join(" ");
  const fillPoints = `0,${h} ${points} ${w},${h}`;
  const total = data.reduce((a, b) => a + b, 0);

  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-baseline gap-2">
        <span className="text-3xl font-bold text-cyan-400 tabular-nums">{total}</span>
        <span className="text-xs text-slate-400">sessions / 24h</span>
      </div>
      <svg width={w} height={h} className="overflow-visible">
        <polygon points={fillPoints} fill="rgb(6 182 212 / 0.15)" />
        <polyline
          points={points}
          fill="none"
          stroke="rgb(6 182 212)"
          strokeWidth="1.5"
          strokeLinejoin="round"
        />
        {data.map((v, i) =>
          v > 0 ? (
            <circle
              key={i}
              cx={(i * step).toFixed(1)}
              cy={(h - (v / max) * h).toFixed(1)}
              r="2"
              fill="rgb(6 182 212)"
            />
          ) : null
        )}
      </svg>
    </div>
  );
}

// ── Phase pill ────────────────────────────────────────────────────────────
function PhasePill({ phase }: { phase: string }) {
  const color = {
    spec: "bg-blue-500/20 text-blue-300 border-blue-500/40",
    plan: "bg-purple-500/20 text-purple-300 border-purple-500/40",
    build: "bg-amber-500/20 text-amber-300 border-amber-500/40",
    test: "bg-cyan-500/20 text-cyan-300 border-cyan-500/40",
    ship: "bg-emerald-500/20 text-emerald-300 border-emerald-500/40",
    review: "bg-rose-500/20 text-rose-300 border-rose-500/40",
    evaluating: "bg-cyan-500/20 text-cyan-300 border-cyan-500/40",
    cloning: "bg-slate-500/20 text-slate-300 border-slate-500/40",
    created: "bg-slate-500/20 text-slate-300 border-slate-500/40",
    building: "bg-amber-500/20 text-amber-300 border-amber-500/40",
    running: "bg-amber-500/20 text-amber-300 border-amber-500/40",
  }[phase] || "bg-slate-500/20 text-slate-300 border-slate-500/40";
  return (
    <span className={`px-2 py-0.5 text-xs font-mono rounded border ${color}`}>
      {phase}
    </span>
  );
}

// ── Pulsing dot ───────────────────────────────────────────────────────────
function LiveDot({ active }: { active: boolean }) {
  return (
    <span className="inline-flex h-2 w-2">
      <span
        className={`absolute inline-flex h-2 w-2 rounded-full ${
          active ? "bg-emerald-400 animate-ping" : "bg-slate-600"
        } opacity-75`}
      />
      <span
        className={`relative inline-flex h-2 w-2 rounded-full ${
          active ? "bg-emerald-500" : "bg-slate-600"
        }`}
      />
    </span>
  );
}

// ── Main component ────────────────────────────────────────────────────────
export default function LiveActivityFeed() {
  const [data, setData] = useState<LiveData | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [lastUpdate, setLastUpdate] = useState<number>(0);

  useEffect(() => {
    let mounted = true;
    const tick = async () => {
      try {
        const r = await fetch("/api/pi-ceo/api/mission-control/live", {
          credentials: "include",
          cache: "no-store",
        });
        if (!r.ok) {
          if (mounted) setErr(`HTTP ${r.status}`);
          return;
        }
        const j = (await r.json()) as LiveData;
        if (mounted) {
          setData(j);
          setLastUpdate(Date.now());
          setErr(null);
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

  const isLive = lastUpdate > 0 && Date.now() - lastUpdate < 15000;

  if (!data && !err) {
    return (
      <div className="rounded-lg border border-slate-700/50 bg-slate-900/50 p-6 backdrop-blur-sm">
        <div className="animate-pulse text-slate-400">Loading Mission Control…</div>
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
          <span className="text-xs text-slate-500">
            {err ? `⚠ ${err}` : isLive ? "live · polling 5s" : "stalled"}
          </span>
        </div>
        {data && (
          <span className="text-xs text-slate-500 tabular-nums">
            updated {fmtAgo(data.ts)}
          </span>
        )}
      </div>

      {/* Stats grid */}
      {data && (
        <>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 p-4 border-b border-slate-800">
            {/* Throughput */}
            <div>
              <div className="text-xs uppercase text-slate-500 mb-1">24h throughput</div>
              <Sparkline data={data.throughput.hourly_24h} />
            </div>

            {/* Queue */}
            <div>
              <div className="text-xs uppercase text-slate-500 mb-1">Linear queue</div>
              <div className="flex items-baseline gap-3">
                <div>
                  <span className="text-3xl font-bold text-rose-400 tabular-nums">
                    {data.queue.urgent}
                  </span>
                  <span className="text-xs text-slate-400 ml-1">urgent</span>
                </div>
                <div>
                  <span className="text-2xl font-semibold text-amber-400 tabular-nums">
                    {data.queue.high}
                  </span>
                  <span className="text-xs text-slate-400 ml-1">high</span>
                </div>
              </div>
              {data.queue.next_issue_id && (
                <div className="text-xs text-slate-400 mt-2 truncate">
                  next:{" "}
                  <span className="font-mono text-cyan-400">
                    {data.queue.next_issue_id}
                  </span>{" "}
                  {data.queue.next_issue_title}
                </div>
              )}
            </div>

            {/* Pulse */}
            <div>
              <div className="text-xs uppercase text-slate-500 mb-1">Pulse heartbeat</div>
              <div className="flex items-baseline gap-2">
                <span className="text-3xl font-bold text-emerald-400 tabular-nums">
                  {data.pulse.comments_today}
                </span>
                <span className="text-xs text-slate-400">comments today</span>
              </div>
              <div className="text-xs text-slate-400 mt-1">
                last: <span className="font-mono">{fmtAgo(data.pulse.last_at)}</span>
                {data.pulse.pulse_issue_id && (
                  <span className="ml-2 text-slate-500">
                    → {data.pulse.pulse_issue_id}
                  </span>
                )}
              </div>
            </div>
          </div>

          {/* Active sessions */}
          <div className="p-4 border-b border-slate-800">
            <div className="text-xs uppercase text-slate-500 mb-2 flex items-center gap-2">
              Active sessions
              <span className="px-1.5 py-0.5 bg-slate-800 rounded text-slate-300 tabular-nums">
                {data.active_sessions.length}
              </span>
            </div>
            {data.active_sessions.length === 0 ? (
              <div className="text-sm text-slate-500 italic">
                No active sessions — poller waits for next tick or queue empty.
              </div>
            ) : (
              <div className="space-y-2">
                {data.active_sessions.map((s) => (
                  <div
                    key={s.id}
                    className="flex items-center gap-3 py-2 px-3 rounded bg-slate-900/50 border border-slate-800"
                  >
                    <LiveDot active={true} />
                    <span className="font-mono text-xs text-slate-400">
                      {s.id}
                    </span>
                    <PhasePill phase={s.phase || s.status} />
                    <span className="text-sm text-slate-200 font-medium">
                      {s.repo}
                    </span>
                    {s.issue_id && (
                      <span className="text-xs text-cyan-400 font-mono">
                        {s.issue_id}
                      </span>
                    )}
                    <span className="ml-auto text-xs text-slate-400 tabular-nums">
                      {fmtElapsed(s.elapsed_s)}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Recent completions */}
          <div className="p-4">
            <div className="text-xs uppercase text-slate-500 mb-2">
              Recent completions
            </div>
            {data.recent_completions.length === 0 ? (
              <div className="text-sm text-slate-500 italic">
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
                    <span className="font-mono text-slate-500">{c.id}</span>
                    <span className="text-slate-200 font-medium">{c.repo}</span>
                    {c.branch && (
                      <span className="text-slate-400 font-mono truncate max-w-[200px]">
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
                      <a
                        href={c.pr_url}
                        target="_blank"
                        rel="noreferrer"
                        className="text-cyan-400 hover:underline ml-auto"
                      >
                        PR →
                      </a>
                    )}
                    <span className="text-slate-500 tabular-nums">
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
