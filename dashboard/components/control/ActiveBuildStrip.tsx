// components/control/ActiveBuildStrip.tsx — always-visible live progress strip.
// Polls /api/pi-ceo/api/sessions every 4s. Unlike SSE terminals that show
// "🔴 disconnected" when the stream drops, this keeps rendering regardless —
// source of truth is the server's session list, not the client's connection.
//
// Shipped 2026-04-17 in response to the "I lost connection, is it dead?"
// trust problem — a terminal looking dead while the backend keeps working
// is the archetypal surface-treatment failure (RA-1109).

"use client";

import { useEffect, useState } from "react";

interface Session {
  id: string;
  repo: string;
  status: string;
  lines: number;
  last_phase: string;
  files_modified: number;
  retry_count: number;
  evaluator_score: number | null;
  evaluator_status: string | null;
  started: number;
}

// Active (non-terminal) server-side statuses
const ACTIVE_STATUSES = new Set([
  "cloning", "planning", "building", "analyzing",
  "evaluating", "pushing", "running",
]);

const PHASE_ORDER: Record<string, number> = {
  sandbox: 0, clone: 1, analyze: 2, plan: 3,
  generator: 4, evaluator: 5, push: 6, ship: 7,
};

const PHASE_TOTAL = 7;

function phaseLabel(phase: string): string {
  const labels: Record<string, string> = {
    sandbox: "Sandbox verify",
    clone: "Clone",
    analyze: "Analyse workspace",
    plan: "Plan",
    generator: "Generate (Claude)",
    evaluator: "Evaluate",
    push: "Push branch",
    ship: "Ship",
  };
  return labels[phase] ?? phase ?? "starting";
}

function shortRepo(url: string): string {
  return url.replace(/^https?:\/\/github\.com\//, "").replace(/\.git$/, "");
}

function formatElapsed(startedUnix: number): string {
  const secs = Math.floor(Date.now() / 1000 - startedUnix);
  if (secs < 60) return `${secs}s`;
  const m = Math.floor(secs / 60);
  const s = secs % 60;
  return `${m}m ${s.toString().padStart(2, "0")}s`;
}

function BuildRow({ s }: { s: Session }) {
  // Force re-render once per second for elapsed ticker.
  const [, setTick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setTick((n) => n + 1), 1000);
    return () => clearInterval(id);
  }, []);

  const phaseIdx = PHASE_ORDER[s.last_phase] ?? 0;
  const pct = Math.min(100, Math.round(((phaseIdx + 1) / PHASE_TOTAL) * 100));

  return (
    <div
      className="flex flex-col gap-1.5 px-3 py-2.5"
      style={{
        background: "var(--panel)",
        border: "1px solid var(--border)",
        borderRadius: 6,
      }}
    >
      <div className="flex items-center gap-3 text-[11px] font-mono">
        {/* Pulsing amber dot = live */}
        <span
          aria-label="building"
          style={{
            width: 8,
            height: 8,
            borderRadius: "50%",
            background: "var(--accent)",
            animation: "pi-strip-pulse 1.4s ease-in-out infinite",
            flexShrink: 0,
          }}
        />
        <span style={{ color: "var(--text)", fontWeight: 600 }}>
          {shortRepo(s.repo)}
        </span>
        <span style={{ color: "var(--text-muted)" }}>
          {phaseLabel(s.last_phase)}
          {s.retry_count > 0 && <> · retry {s.retry_count}/3</>}
        </span>
        <span style={{ marginLeft: "auto", color: "var(--text-dim)" }}>
          {formatElapsed(s.started)} · {s.lines} lines
          {s.files_modified > 0 && <> · {s.files_modified} files</>}
        </span>
      </div>

      {/* Striped animated progress bar — always moving even if percent doesn't change */}
      <div
        aria-label={`${phaseLabel(s.last_phase)} — ${pct}%`}
        style={{
          height: 6,
          borderRadius: 3,
          overflow: "hidden",
          background: "var(--panel-hover)",
          border: "1px solid var(--border-subtle)",
        }}
      >
        <div
          style={{
            width: `${pct}%`,
            height: "100%",
            background: "var(--accent)",
            backgroundImage:
              "repeating-linear-gradient(45deg, rgba(255,255,255,0.15) 0, rgba(255,255,255,0.15) 6px, transparent 6px, transparent 12px)",
            backgroundSize: "24px 24px",
            animation: "pi-strip-stripe 800ms linear infinite",
            transition: "width 600ms ease-out",
          }}
        />
      </div>
    </div>
  );
}

export default function ActiveBuildStrip() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [fetchError, setFetchError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    async function poll() {
      try {
        const res = await fetch("/api/pi-ceo/api/sessions", { cache: "no-store" });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data: unknown = await res.json();
        if (!alive) return;
        const list = Array.isArray(data) ? data : [];
        const active = (list as Session[]).filter((s) =>
          ACTIVE_STATUSES.has(s.status)
        );
        setSessions(active);
        setFetchError(null);
      } catch (e) {
        if (!alive) return;
        setFetchError(e instanceof Error ? e.message : String(e));
      }
    }
    void poll();
    const id = setInterval(poll, 4000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, []);

  if (sessions.length === 0 && !fetchError) return null;

  return (
    <>
      <style>{`
        @keyframes pi-strip-pulse {
          0%, 100% { opacity: 1; transform: scale(1); }
          50%      { opacity: 0.5; transform: scale(0.85); }
        }
        @keyframes pi-strip-stripe {
          from { background-position: 0 0; }
          to   { background-position: 24px 0; }
        }
      `}</style>
      <section
        aria-label="Active builds"
        className="flex flex-col gap-2"
        style={{ marginBottom: 12 }}
      >
        <div
          className="text-[10px] uppercase tracking-widest font-semibold"
          style={{ color: "var(--text-muted)" }}
        >
          Active Builds ({sessions.length})
        </div>
        {sessions.map((s) => (
          <BuildRow key={s.id} s={s} />
        ))}
        {fetchError && (
          <div
            className="text-[10px] font-mono"
            style={{ color: "var(--warning)" }}
          >
            build-strip poll error: {fetchError} — retrying every 4 s
          </div>
        )}
      </section>
    </>
  );
}
