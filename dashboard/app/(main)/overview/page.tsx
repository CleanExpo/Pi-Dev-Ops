// app/(main)/overview/page.tsx — CEO Command Centre
"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

// ── Types ─────────────────────────────────────────────────────────────────────

interface HealthData {
  status: string;
  uptime_s: number;
  sessions: { active: number; total: number; max: number };
  claude_cli: boolean;
  anthropic_key: boolean;
  linear_key: boolean;
  autonomy: {
    enabled: boolean;
    armed: boolean;
    poll_count: number;
    seconds_since_last_poll: number | null;
  };
  disk_free_gb: number | null;
  vercel_token?: boolean;
  swarm_enabled?: boolean;
  swarm_shadow?: boolean;
}

interface PiSession {
  id: string;
  repo: string;
  status: string;
  started: string;
  last_phase?: string;
  evaluator_score?: number;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatUptime(s: number): string {
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`;
  return `${Math.floor(s / 86400)}d ${Math.floor((s % 86400) / 3600)}h`;
}

function repoShort(repo: string): string {
  try {
    const parts = new URL(repo).pathname.replace(/^\//, "").split("/");
    return parts.slice(0, 2).join("/");
  } catch {
    return repo.replace(/^https?:\/\/[^/]+\//, "").slice(0, 40);
  }
}

function skillFromPhase(phase?: string): string {
  if (!phase) return "Initialising";
  const map: Record<string, string> = {
    clone: "Checkout",
    build: "Code Review",
    scan: "Security Scan",
    test: "QA",
    evaluate: "ZTE Eval",
    ship: "Deploy",
    push: "Git Push",
  };
  for (const [key, label] of Object.entries(map)) {
    if (phase.toLowerCase().includes(key)) return label;
  }
  return phase;
}

function statusDot(status: string): string {
  if (["cloning", "building", "evaluating"].includes(status)) return "var(--accent)";
  if (status === "complete" || status === "done") return "var(--success)";
  if (status === "failed" || status === "error") return "var(--error)";
  return "var(--text-dim)";
}

// ── Sub-components ────────────────────────────────────────────────────────────

function StatChip({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div
      className="flex flex-col gap-0.5 px-3 py-2 rounded-lg"
      style={{ background: "var(--panel)", border: "1px solid var(--border)" }}
    >
      <span className="text-[9px] font-semibold uppercase tracking-widest" style={{ color: "var(--text-dim)" }}>
        {label}
      </span>
      <span className="text-sm font-mono font-bold leading-tight" style={{ color: color ?? "var(--text)" }}>
        {value}
      </span>
    </div>
  );
}

function AgentCard({ session }: { session: PiSession }) {
  const live = ["cloning", "building", "evaluating", "created"].includes(session.status);
  return (
    <div
      className="flex items-start gap-3 px-3 py-2.5 rounded-lg"
      style={{
        background: "var(--panel)",
        border: `1px solid ${live ? "var(--accent)" : "var(--border)"}`,
        opacity: live ? 1 : 0.65,
      }}
    >
      <div className="flex flex-col items-center gap-1 pt-0.5">
        <span
          className="w-2 h-2 rounded-full shrink-0"
          style={{ background: statusDot(session.status) }}
        />
        {live && (
          <span
            className="text-[8px] font-semibold uppercase tracking-wider"
            style={{ color: "var(--accent)" }}
          >
            LIVE
          </span>
        )}
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-xs font-medium truncate" style={{ color: "var(--text)" }}>
          {repoShort(session.repo)}
        </p>
        <p className="text-[10px] mt-0.5" style={{ color: "var(--text-muted)" }}>
          {skillFromPhase(session.last_phase)}
          {session.evaluator_score !== undefined && session.evaluator_score > 0 && (
            <span style={{ color: session.evaluator_score >= 8 ? "var(--success)" : "var(--text-dim)" }}>
              {" "}· {session.evaluator_score}/10
            </span>
          )}
        </p>
      </div>
      <span
        className="text-[9px] font-mono shrink-0 mt-0.5"
        style={{ color: "var(--text-dim)" }}
      >
        {session.id.slice(0, 6)}
      </span>
    </div>
  );
}

function ActivityRow({ session, index }: { session: PiSession; index: number }) {
  const ts = new Date(session.started);
  const timeStr = ts.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  const live = ["cloning", "building", "evaluating", "created"].includes(session.status);

  return (
    <div
      className="flex items-center gap-3 px-3 py-2 text-xs font-mono"
      style={{
        borderBottom: "1px solid var(--border)",
        background: index % 2 === 0 ? "transparent" : "rgba(255,255,255,0.01)",
      }}
    >
      <span className="shrink-0 w-10 text-right" style={{ color: "var(--text-dim)" }}>
        {timeStr}
      </span>
      <span
        className="w-1.5 h-1.5 rounded-full shrink-0"
        style={{ background: statusDot(session.status) }}
      />
      <span className="flex-1 truncate" style={{ color: "var(--text-muted)" }}>
        {repoShort(session.repo)}
      </span>
      <span
        className="shrink-0 text-[9px] px-1.5 py-0.5 rounded uppercase tracking-wide"
        style={{
          background: live ? "rgba(249,115,22,0.12)" : "transparent",
          color: live ? "var(--accent)" : "var(--text-dim)",
          border: `1px solid ${live ? "var(--accent)" : "var(--border)"}`,
        }}
      >
        {session.status}
      </span>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function OverviewPage() {
  const [health, setHealth] = useState<HealthData | null>(null);
  const [sessions, setSessions] = useState<PiSession[]>([]);
  const [_tick, setTick] = useState(0);

  useEffect(() => {
    async function load() {
      try {
        const [hRes, sRes] = await Promise.all([
          fetch("/api/pi-ceo/health"),
          fetch("/api/pi-ceo/api/sessions"),
        ]);
        if (hRes.ok) setHealth(await hRes.json() as HealthData);
        if (sRes.ok) setSessions(await sRes.json() as PiSession[]);
      } catch { /* ignore */ }
    }
    void load();
    const t = setInterval(() => { void load(); setTick(n => n + 1); }, 15_000);
    return () => clearInterval(t);
  }, []);

  const activeSessions = sessions.filter(s =>
    ["cloning", "building", "evaluating", "created"].includes(s.status)
  );
  const recentSessions = [...sessions].sort(
    (a, b) => new Date(b.started).getTime() - new Date(a.started).getTime()
  ).slice(0, 20);

  const swarmOn = health?.swarm_enabled !== false;
  const swarmShadow = health?.swarm_shadow === true;
  const swarmLabel = !swarmOn ? "Off" : swarmShadow ? "Shadow" : "Active";
  const swarmColor = !swarmOn ? "var(--error)" : swarmShadow ? "var(--warning)" : "var(--success)";

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* ── Page header ──────────────────────────────────────────────────── */}
      <div
        className="flex items-center justify-between px-4 h-[52px] shrink-0"
        style={{ borderBottom: "1px solid var(--border)" }}
      >
        <div>
          <h1 className="text-base font-semibold leading-none" style={{ color: "var(--text)" }}>
            Command Centre
          </h1>
          <p className="text-[10px] mt-0.5 leading-none" style={{ color: "var(--text-dim)" }}>
            Live system overview · refreshes every 15s
          </p>
        </div>
        <Link
          href="/control"
          className="text-xs font-medium px-3 py-1.5 rounded-md transition-colors"
          style={{ background: "var(--accent)", color: "#fff" }}
        >
          Run Analysis ▶
        </Link>
      </div>

      {/* ── Status strip ──────────────────────────────────────────────────── */}
      <div
        className="flex items-center gap-3 px-4 py-2.5 shrink-0 flex-wrap"
        style={{ borderBottom: "1px solid var(--border)", background: "var(--panel)" }}
      >
        {health ? (
          <>
            <StatChip label="Uptime" value={formatUptime(health.uptime_s)} color="var(--success)" />
            <StatChip
              label="Active Builds"
              value={`${health.sessions.active} / ${health.sessions.max}`}
              color={health.sessions.active > 0 ? "var(--accent)" : "var(--text)"}
            />
            <StatChip label="Swarm" value={swarmLabel} color={swarmColor} />
            <StatChip
              label="Autonomy"
              value={health.autonomy.armed ? "Armed" : "Disarmed"}
              color={health.autonomy.armed ? "var(--success)" : "var(--warning)"}
            />
            <StatChip
              label="Polls"
              value={String(health.autonomy.poll_count)}
            />
            {health.disk_free_gb !== null && (
              <StatChip
                label="Disk Free"
                value={`${health.disk_free_gb} GB`}
                color={health.disk_free_gb < 10 ? "var(--warning)" : "var(--text-muted)"}
              />
            )}
            <StatChip
              label="Claude CLI"
              value={health.claude_cli ? "OK" : "—"}
              color={health.claude_cli ? "var(--success)" : "var(--error)"}
            />
          </>
        ) : (
          <span className="text-xs animate-pulse" style={{ color: "var(--text-dim)" }}>
            Connecting to backend…
          </span>
        )}
      </div>

      {/* ── Main grid ─────────────────────────────────────────────────────── */}
      <div className="flex-1 min-h-0 overflow-auto">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-px h-full" style={{ background: "var(--border)" }}>

          {/* ── LEFT: Agents On-Shift ───────────────────────────────────── */}
          <div className="flex flex-col overflow-hidden" style={{ background: "var(--background)" }}>
            <div
              className="flex items-center justify-between px-4 py-2.5 shrink-0"
              style={{ borderBottom: "1px solid var(--border)" }}
            >
              <span className="text-[10px] font-semibold uppercase tracking-widest" style={{ color: "var(--text-dim)" }}>
                Agents On-Shift
              </span>
              <span
                className="text-[9px] font-mono px-1.5 py-0.5 rounded"
                style={{ background: "var(--panel)", color: "var(--text-muted)", border: "1px solid var(--border)" }}
              >
                {activeSessions.length} active
              </span>
            </div>
            <div className="flex-1 overflow-y-auto p-3 flex flex-col gap-2">
              {activeSessions.length === 0 ? (
                <div className="flex flex-col items-center justify-center flex-1 gap-2 py-8">
                  <span className="text-2xl opacity-20">⚙</span>
                  <p className="text-xs text-center" style={{ color: "var(--text-dim)" }}>
                    No active builds.
                  </p>
                  <Link
                    href="/control"
                    className="text-xs mt-1"
                    style={{ color: "var(--accent)" }}
                  >
                    Start analysis →
                  </Link>
                </div>
              ) : (
                activeSessions.map(s => <AgentCard key={s.id} session={s} />)
              )}

              {/* Recent completed */}
              {sessions.filter(s => s.status === "complete" || s.status === "done").slice(0, 3).map(s => (
                <AgentCard key={s.id} session={s} />
              ))}
            </div>
          </div>

          {/* ── CENTER: Live Activity Feed ──────────────────────────────── */}
          <div className="flex flex-col overflow-hidden" style={{ background: "var(--background)" }}>
            <div
              className="flex items-center justify-between px-4 py-2.5 shrink-0"
              style={{ borderBottom: "1px solid var(--border)" }}
            >
              <span className="text-[10px] font-semibold uppercase tracking-widest" style={{ color: "var(--text-dim)" }}>
                Live Activity Feed
              </span>
              <span
                className="text-[9px] font-mono px-1.5 py-0.5 rounded"
                style={{ background: "var(--panel)", color: "var(--text-muted)", border: "1px solid var(--border)" }}
              >
                {recentSessions.length} sessions
              </span>
            </div>
            <div className="flex-1 overflow-y-auto">
              {recentSessions.length === 0 ? (
                <div className="flex items-center justify-center h-full">
                  <p className="text-xs" style={{ color: "var(--text-dim)" }}>No sessions yet.</p>
                </div>
              ) : (
                recentSessions.map((s, i) => (
                  <ActivityRow key={s.id} session={s} index={i} />
                ))
              )}
            </div>
          </div>

          {/* ── RIGHT: System Health Detail ─────────────────────────────── */}
          <div className="flex flex-col overflow-hidden" style={{ background: "var(--background)" }}>
            <div
              className="flex items-center justify-between px-4 py-2.5 shrink-0"
              style={{ borderBottom: "1px solid var(--border)" }}
            >
              <span className="text-[10px] font-semibold uppercase tracking-widest" style={{ color: "var(--text-dim)" }}>
                System Health
              </span>
              {health && (
                <span
                  className="text-[9px] font-mono px-1.5 py-0.5 rounded"
                  style={{
                    background: health.status === "ok" ? "rgba(34,197,94,0.12)" : "rgba(239,68,68,0.12)",
                    color: health.status === "ok" ? "var(--success)" : "var(--error)",
                    border: `1px solid ${health.status === "ok" ? "rgba(34,197,94,0.3)" : "rgba(239,68,68,0.3)"}`,
                  }}
                >
                  {health.status.toUpperCase()}
                </span>
              )}
            </div>

            <div className="flex-1 overflow-y-auto p-4 flex flex-col gap-4">
              {/* Services checklist */}
              <div>
                <p className="text-[9px] font-semibold uppercase tracking-widest mb-2" style={{ color: "var(--text-dim)" }}>
                  Services
                </p>
                {[
                  { label: "Claude CLI", ok: health?.claude_cli ?? false },
                  { label: "Anthropic API Key", ok: health?.anthropic_key ?? false },
                  { label: "Linear API Key", ok: health?.linear_key ?? false },
                  { label: "Vercel Token", ok: health?.vercel_token ?? false },
                  { label: "Autonomy Loop", ok: health?.autonomy.armed ?? false },
                ].map(({ label, ok }) => (
                  <div key={label} className="flex items-center justify-between py-1" style={{ borderBottom: "1px solid var(--border)" }}>
                    <span className="text-xs" style={{ color: "var(--text-muted)" }}>{label}</span>
                    <span
                      className="text-[10px] font-mono"
                      style={{ color: ok ? "var(--success)" : "var(--error)" }}
                    >
                      {ok ? "✓" : "✗"}
                    </span>
                  </div>
                ))}
              </div>

              {/* Autonomy detail */}
              {health?.autonomy && (
                <div>
                  <p className="text-[9px] font-semibold uppercase tracking-widest mb-2" style={{ color: "var(--text-dim)" }}>
                    Autonomy
                  </p>
                  <div className="flex flex-col gap-1">
                    {[
                      ["State", health.autonomy.armed ? "Armed" : "Disarmed"],
                      ["Poll count", String(health.autonomy.poll_count)],
                      ["Last poll", health.autonomy.seconds_since_last_poll !== null
                        ? `${health.autonomy.seconds_since_last_poll}s ago`
                        : "Never"],
                    ].map(([k, v]) => (
                      <div key={k} className="flex justify-between text-xs">
                        <span style={{ color: "var(--text-dim)" }}>{k}</span>
                        <span className="font-mono" style={{ color: "var(--text-muted)" }}>{v}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Quick links */}
              <div>
                <p className="text-[9px] font-semibold uppercase tracking-widest mb-2" style={{ color: "var(--text-dim)" }}>
                  Quick Actions
                </p>
                <div className="flex flex-col gap-1.5">
                  {[
                    { label: "Run Analysis", href: "/dashboard" },
                    { label: "Build History", href: "/history" },
                    { label: "Active Builds", href: "/builds" },
                    { label: "Settings", href: "/settings" },
                  ].map(({ label, href }) => (
                    <Link
                      key={href}
                      href={href}
                      className="flex items-center justify-between text-xs px-3 py-1.5 rounded transition-colors"
                      style={{
                        background: "var(--panel)",
                        color: "var(--text-muted)",
                        border: "1px solid var(--border)",
                      }}
                    >
                      {label}
                      <span style={{ color: "var(--accent)" }}>→</span>
                    </Link>
                  ))}
                </div>
              </div>
            </div>
          </div>

        </div>
      </div>
    </div>
  );
}
