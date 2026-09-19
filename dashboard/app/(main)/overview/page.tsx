// app/(main)/overview/page.tsx — CEO Command Centre
"use client";

import Link from "next/link";
import { useOperatorObservations } from "@/hooks/useOperatorObservations";
import { AgentCard, ActivityRow } from "@/components/control/OverviewSessionRows";
import { OperatorReadiness } from "@/components/control/OperatorReadiness";
import { automationLabel, sessionTime, swarmLabel } from "@/lib/operator-status";
import {
  claudeCliChip,
  formatUptime,
  OVERVIEW_QUICK_LINKS,
  overviewLede,
  overviewServiceRows,
  serviceMarkGlyph,
} from "@/lib/control/overview-format";

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

export default function OverviewPage() {
  const observations = useOperatorObservations();
  const { health, sessions, sessionsError, sessionsLoaded } = observations;

  const activeSessions = sessions.filter(s =>
    ["cloning", "building", "evaluating", "created"].includes(s.status)
  );
  const recentSessions = [...sessions].sort(
    (a, b) => sessionTime(b.started) - sessionTime(a.started)
  ).slice(0, 20);

  const swarm = { label: swarmLabel(health), color: "var(--text-muted)" };
  const cli = claudeCliChip(health);

  return (
    <div className="flex flex-col h-full overflow-auto">
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
            {overviewLede(health)}
          </p>
        </div>
        <Link
          href="/control/build"
          className="text-xs font-medium px-3 py-1.5 rounded-md transition-colors"
          style={{ background: "var(--accent)", color: "var(--on-accent)" }}
        >
          Run a build
        </Link>
      </div>

      <OperatorReadiness {...observations} />

      {/* ── Status strip ──────────────────────────────────────────────────── */}
      <div
        className="flex items-center gap-3 px-4 py-2.5 shrink-0 flex-wrap"
        style={{ borderBottom: "1px solid var(--border)", background: "var(--panel)" }}
      >
        {health ? (
          <>
            <StatChip
              label="Uptime"
              value={health.uptime_s !== undefined ? formatUptime(health.uptime_s) : "—"}
              color="var(--success)"
            />
            <StatChip
              label="Active Builds"
              value={
                health.sessions && typeof health.sessions.active === "number"
                  ? `${health.sessions.active} / ${health.sessions.max ?? "?"}`
                  : "—"
              }
              color={
                (health.sessions?.active ?? 0) > 0
                  ? "var(--accent)"
                  : "var(--text)"
              }
            />
            <StatChip label="Swarm" value={swarm.label} color={swarm.color} />
            <StatChip
              label="Autonomy"
              value={automationLabel(health)}
              color={
                health.autonomy?.armed
                  ? "var(--success)"
                  : health.autonomy === undefined
                    ? "var(--text-dim)"
                    : "var(--warning)"
              }
            />
            <StatChip
              label="Polls"
              value={
                typeof health.autonomy?.poll_count === "number"
                  ? String(health.autonomy.poll_count)
                  : "—"
              }
            />
            {health.disk_free_gb != null && (
              <StatChip
                label="Disk Free"
                value={`${health.disk_free_gb} GB`}
                color={health.disk_free_gb < 10 ? "var(--warning)" : "var(--text-muted)"}
              />
            )}
            <StatChip
              label="Claude CLI"
              value={cli.value}
              color={cli.color}
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
                    href="/control/goal"
                    className="text-xs mt-1"
                    style={{ color: "var(--accent)" }}
                  >
                    Goal → Linear
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
                  <p className="text-xs" style={{ color: "var(--text-dim)" }}>{sessionsError ? "Activity unavailable." : !sessionsLoaded ? "Checking sessions..." : "No sessions yet."}</p>
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
                {overviewServiceRows(health).map(({ label, mark }) => {
                  const shown = serviceMarkGlyph(mark);
                  return (
                  <div key={label} className="flex items-center justify-between py-1" style={{ borderBottom: "1px solid var(--border)" }}>
                    <span className="text-xs" style={{ color: "var(--text-muted)" }}>{label}</span>
                    <span className="text-[10px] font-mono" style={{ color: shown.color }}>
                      {shown.glyph}
                    </span>
                  </div>
                  );
                })}
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
                      ["Poll count", String(health.autonomy.poll_count ?? "—")],
                      [
                        "Last poll",
                        health.autonomy.seconds_since_last_poll == null
                          ? "Never"
                          : `${health.autonomy.seconds_since_last_poll}s ago`,
                      ],
                    ].map(([k, v]) => (
                      <div key={k} className="flex justify-between text-xs">
                        <span style={{ color: "var(--text-dim)" }}>{k}</span>
                        <span className="font-mono" style={{ color: "var(--text-muted)" }}>{v}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Backend-shape warning banner — surfaces when /health returns
                  the minimal {status:"ok"} shape instead of the full payload.
                  RA-1109: silent success is indistinguishable from broken —
                  tell the user why all the fields are "—". */}
              {health && !health.autonomy && !health.sessions && (
                <div
                  className="text-[10px] px-2.5 py-2 rounded"
                  style={{
                    background: "rgba(245,158,11,0.08)",
                    border: "1px solid rgba(245,158,11,0.3)",
                    color: "var(--warning)",
                  }}
                >
                  <strong>Limited health payload</strong> — backend <code>/health</code> is
                  returning <code>{"{status:\"ok\"}"}</code> only. Tracked separately; Overview
                  renders the shell so the page doesn&apos;t crash.
                </div>
              )}

              {/* Quick links */}
              <div>
                <p className="text-[9px] font-semibold uppercase tracking-widest mb-2" style={{ color: "var(--text-dim)" }}>
                  Quick Actions
                </p>
                <div className="flex flex-col gap-1.5">
                  {OVERVIEW_QUICK_LINKS.map(({ label, href }) => (
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
