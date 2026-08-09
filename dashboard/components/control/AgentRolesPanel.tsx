// components/control/AgentRolesPanel.tsx — real pipeline-role status roster (RA-mission-control-roster).
//
// This is deliberately NOT a fabricated "Research Agent / Docs Agent" roster — no such
// independently-running named agents exist in this backend today (confirmed by reading
// session_phases.py, session_model.py, provider_router.py). What IS real: every build
// session runs through the same 8 phases (session_phases.py _PHASE_ORDER), and each phase
// records real duration/cost in BuildSession.phase_metrics once it completes. This panel
// shows those 8 real phases as "roles", each with real status derived from actual session
// data polled from /api/pi-ceo/api/sessions — the same endpoint ActiveBuildStrip already
// uses. A role with no recorded runs says so plainly (dead shows dead), it does not
// fabricate a plausible-looking status.
"use client";

import { useEffect, useState } from "react";

interface PhaseMetric {
  duration_s: number;
  cost_usd: number;
}

interface Session {
  id: string;
  repo: string;
  status: string;
  started: number;
  last_phase: string;
  phase_metrics?: Record<string, PhaseMetric>;
}

// Source of truth: app/server/session_phases.py _PHASE_ORDER. Kept in this exact order —
// do not alphabetise, it's the real execution sequence.
const ROLES: { key: string; label: string }[] = [
  { key: "clone", label: "Clone" },
  { key: "analyze", label: "Analyse workspace" },
  { key: "claude_check", label: "Claude check" },
  { key: "sandbox", label: "Sandbox verify" },
  { key: "plan", label: "Plan" },
  { key: "generator", label: "Generate (Claude)" },
  { key: "evaluator", label: "Evaluate" },
  { key: "push", label: "Push branch" },
];

const ACTIVE_STATUSES = new Set([
  "cloning", "planning", "building", "analyzing", "evaluating", "pushing", "running",
]);

function shortRepo(url: string): string {
  return url.replace(/^https?:\/\/github\.com\//, "").replace(/\.git$/, "");
}

function formatElapsed(startedUnix: number): string {
  const secs = Math.floor(Date.now() / 1000 - startedUnix);
  if (secs < 60) return `${secs}s`;
  const m = Math.floor(secs / 60);
  return `${m}m ${(secs % 60).toString().padStart(2, "0")}s`;
}

interface RoleStatus {
  key: string;
  label: string;
  state: "running" | "idle" | "never";
  detail: string;
}

function deriveRoleStatuses(sessions: Session[]): RoleStatus[] {
  return ROLES.map(({ key, label }) => {
    // Running: some non-terminal session is currently in this phase.
    const running = sessions.find(
      (s) => ACTIVE_STATUSES.has(s.status) && s.last_phase === key
    );
    if (running) {
      return {
        key, label, state: "running",
        detail: `${shortRepo(running.repo)} · ${formatElapsed(running.started)}`,
      };
    }

    // Idle: find the most recently-started session that recorded a metric for this phase.
    const withMetric = sessions
      .filter((s) => s.phase_metrics && s.phase_metrics[key])
      .sort((a, b) => b.started - a.started)[0];
    if (withMetric) {
      const m = withMetric.phase_metrics![key];
      return {
        key, label, state: "idle",
        detail: `last: ${shortRepo(withMetric.repo)} · ${m.duration_s}s · $${m.cost_usd.toFixed(4)}`,
      };
    }

    return { key, label, state: "never", detail: "no runs recorded yet" };
  });
}

function StateDot({ state }: { state: RoleStatus["state"] }) {
  const colour =
    state === "running" ? "var(--accent)" : state === "idle" ? "var(--success)" : "var(--text-dim)";
  return (
    <span
      aria-hidden="true"
      style={{
        width: 7,
        height: 7,
        borderRadius: "50%",
        background: colour,
        flexShrink: 0,
        animation: state === "running" ? "pi-roles-pulse 1.4s ease-in-out infinite" : undefined,
      }}
    />
  );
}

export default function AgentRolesPanel() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    async function poll() {
      try {
        const res = await fetch("/api/pi-ceo/api/sessions", { cache: "no-store" });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data: unknown = await res.json();
        if (!alive) return;
        setSessions(Array.isArray(data) ? (data as Session[]) : []);
        setFetchError(null);
      } catch (e) {
        if (!alive) return;
        setFetchError(e instanceof Error ? e.message : String(e));
      } finally {
        if (alive) setLoading(false);
      }
    }
    void poll();
    const id = setInterval(poll, 5000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, []);

  const roles = deriveRoleStatuses(sessions);
  const runningCount = roles.filter((r) => r.state === "running").length;

  return (
    <section
      className="flex flex-col h-full min-h-0"
      style={{ background: "var(--panel)", border: "1px solid var(--border)", borderRadius: 8 }}
      aria-label="Pipeline role status"
    >
      <style>{`
        @keyframes pi-roles-pulse {
          0%, 100% { opacity: 1; transform: scale(1); }
          50%      { opacity: 0.5; transform: scale(0.8); }
        }
      `}</style>
      <header
        className="flex items-center justify-between px-4 py-2.5"
        style={{ borderBottom: "1px solid var(--border)" }}
      >
        <h2 className="text-xs font-semibold uppercase tracking-widest" style={{ color: "var(--text-muted)" }}>
          Pipeline Roles
        </h2>
        <span
          className="text-[10px] font-mono uppercase px-2 py-0.5 rounded"
          style={{ color: "var(--text-dim)", background: "var(--panel-hover)", border: "1px solid var(--border)" }}
          title="Each build session runs through these 8 real phases — this is not a roster of independently-running agents."
        >
          {runningCount > 0 ? `${runningCount} running` : "idle"}
        </span>
      </header>

      <div className="flex-1 overflow-auto p-3 flex flex-col gap-1.5 min-h-0">
        {loading && (
          <p className="text-xs px-1" style={{ color: "var(--text-dim)" }}>Loading…</p>
        )}

        {fetchError && !loading && (
          <p className="text-[11px] font-mono px-1" style={{ color: "var(--warning)" }}>
            ⚠ {fetchError} — retrying every 5s
          </p>
        )}

        {!loading && roles.map((r) => (
          <div
            key={r.key}
            className="flex items-center gap-2.5 px-2.5 py-1.5"
            style={{ background: "var(--panel-hover)", border: "1px solid var(--border-subtle)", borderRadius: 6 }}
          >
            <StateDot state={r.state} />
            <span className="text-[11px] font-medium" style={{ color: "var(--text)", minWidth: 130 }}>
              {r.label}
            </span>
            <span
              className="text-[10px] font-mono ml-auto"
              style={{ color: r.state === "never" ? "var(--text-dim)" : "var(--text-muted)" }}
            >
              {r.detail}
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}
