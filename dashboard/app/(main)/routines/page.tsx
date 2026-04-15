"use client";
// app/(main)/routines/page.tsx — Routine run outcome tracker (RA-1011)

import { useEffect, useState, useCallback } from "react";

interface RoutineRun {
  routine_name: string;
  repo: string;
  trigger: string;
  status: "success" | "failure" | "timeout";
  duration_s: number;
  run_url: string;
  summary: string;
  ts: string;
}

interface RoutineRunsResponse {
  runs: RoutineRun[];
  total: number;
}

const STATUS_COLOR: Record<string, string> = {
  success: "#4ADE80",
  failure: "#F87171",
  timeout: "#FFD166",
};

const STATUS_ICON: Record<string, string> = {
  success: "✓",
  failure: "✗",
  timeout: "⏱",
};

const TRIGGER_LABEL: Record<string, string> = {
  api:      "API",
  schedule: "Sched",
  github:   "GitHub",
};

function fmtDuration(s: number): string {
  if (s < 60) return `${Math.round(s)}s`;
  const m = Math.floor(s / 60);
  const rem = Math.round(s % 60);
  return rem > 0 ? `${m}m ${rem}s` : `${m}m`;
}

function fmtTs(ts: string): string {
  if (!ts) return "—";
  try {
    return new Date(ts).toLocaleString(undefined, {
      month:  "short",
      day:    "2-digit",
      hour:   "2-digit",
      minute: "2-digit",
    });
  } catch {
    return ts;
  }
}

function repoShort(repo: string): string {
  return repo.split("/").slice(-1)[0] ?? repo;
}

function SummaryBar({ runs }: { runs: RoutineRun[] }) {
  const today = new Date().toISOString().slice(0, 10);
  const todayRuns = runs.filter((r) => r.ts.startsWith(today));
  const successCount = runs.filter((r) => r.status === "success").length;
  const successRate = runs.length > 0 ? Math.round((successCount / runs.length) * 100) : null;
  const lastFailure = runs.find((r) => r.status === "failure");

  return (
    <div
      className="flex items-center gap-4 px-3 sm:px-4 py-2 flex-wrap"
      style={{ borderBottom: "1px solid var(--border)", background: "var(--panel)" }}
    >
      <div className="flex items-center gap-1.5">
        <span className="font-mono text-[10px] uppercase tracking-widest" style={{ color: "var(--text-dim)" }}>
          Today
        </span>
        <span className="font-mono text-xs font-semibold" style={{ color: "var(--text)" }}>
          {todayRuns.length}
        </span>
      </div>

      {successRate !== null && (
        <div className="flex items-center gap-1.5">
          <span className="font-mono text-[10px] uppercase tracking-widest" style={{ color: "var(--text-dim)" }}>
            Success
          </span>
          <span
            className="font-mono text-xs font-semibold"
            style={{ color: successRate >= 80 ? "#4ADE80" : successRate >= 50 ? "#FFD166" : "#F87171" }}
          >
            {successRate}%
          </span>
        </div>
      )}

      {lastFailure && (
        <div className="flex items-center gap-1.5 min-w-0">
          <span className="font-mono text-[10px] uppercase tracking-widest" style={{ color: "var(--text-dim)" }}>
            Last fail
          </span>
          <span
            className="font-mono text-[10px] truncate max-w-[180px]"
            style={{ color: "#F87171" }}
            title={`${lastFailure.routine_name} @ ${lastFailure.ts}`}
          >
            {lastFailure.routine_name} — {fmtTs(lastFailure.ts)}
          </span>
        </div>
      )}

      {runs.length === 0 && (
        <span className="font-mono text-[10px]" style={{ color: "var(--text-dim)" }}>
          No runs recorded yet.
        </span>
      )}
    </div>
  );
}

function RunRow({ run }: { run: RoutineRun }) {
  const [expanded, setExpanded] = useState(false);
  const statusColor = STATUS_COLOR[run.status] ?? "var(--text-dim)";

  return (
    <>
      <div
        className="grid px-3 sm:px-4 py-2.5 cursor-pointer transition-colors items-start gap-2"
        style={{
          gridTemplateColumns: "28px 1fr 80px 56px 52px 52px",
          borderBottom: "1px solid var(--border)",
          background: "transparent",
        }}
        onMouseEnter={(e) => (e.currentTarget.style.background = "var(--panel-hover)")}
        onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
        onClick={() => setExpanded((v) => !v)}
      >
        {/* Status icon */}
        <span
          className="font-mono text-xs font-bold text-center"
          style={{ color: statusColor }}
        >
          {STATUS_ICON[run.status] ?? "?"}
        </span>

        {/* Routine + repo */}
        <div className="min-w-0">
          <div className="font-mono text-xs truncate" style={{ color: "var(--text)" }}>
            {run.routine_name}
          </div>
          <div className="font-mono text-[10px] truncate" style={{ color: "var(--text-dim)" }}>
            {repoShort(run.repo)}
          </div>
        </div>

        {/* Timestamp */}
        <span className="font-mono text-[10px] text-right hidden sm:block" style={{ color: "var(--text-muted)" }}>
          {fmtTs(run.ts)}
        </span>

        {/* Trigger */}
        <span
          className="font-mono text-[10px] text-center px-1 rounded"
          style={{ background: "var(--panel)", color: "var(--text-dim)" }}
        >
          {TRIGGER_LABEL[run.trigger] ?? run.trigger}
        </span>

        {/* Duration */}
        <span className="font-mono text-[10px] text-right" style={{ color: "var(--text-muted)" }}>
          {fmtDuration(run.duration_s)}
        </span>

        {/* Chevron */}
        <span className="font-mono text-[10px] text-right" style={{ color: "var(--text-dim)" }}>
          {expanded ? "▲" : "▼"}
        </span>
      </div>

      {expanded && (
        <div
          className="px-4 py-3 font-mono text-xs"
          style={{
            borderBottom: "1px solid var(--border)",
            background: "var(--panel)",
          }}
        >
          {run.summary ? (
            <p style={{ color: "var(--text-muted)", whiteSpace: "pre-wrap" }}>{run.summary}</p>
          ) : (
            <p style={{ color: "var(--text-dim)" }}>No summary provided.</p>
          )}
          <div className="flex flex-wrap gap-4 mt-2">
            <span style={{ color: "var(--text-dim)" }}>
              repo: <span style={{ color: "var(--text-muted)" }}>{run.repo}</span>
            </span>
            <span style={{ color: "var(--text-dim)" }}>
              ts: <span style={{ color: "var(--text-muted)" }}>{run.ts}</span>
            </span>
            {run.run_url && (
              <a
                href={run.run_url}
                target="_blank"
                rel="noopener noreferrer"
                className="underline"
                style={{ color: "var(--accent)" }}
                onClick={(e) => e.stopPropagation()}
              >
                view run ↗
              </a>
            )}
          </div>
        </div>
      )}
    </>
  );
}

export default function RoutinesPage() {
  const [runs, setRuns] = useState<RoutineRun[]>([]);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [lastFetch, setLastFetch] = useState<number>(0);
  const [loading, setLoading] = useState(true);

  const fetchRuns = useCallback(async () => {
    try {
      const res = await fetch("/api/pi-ceo/api/routines?limit=50");
      if (!res.ok) {
        const body = await res.json().catch(() => ({ detail: res.statusText }));
        setError((body as { detail?: string }).detail ?? `HTTP ${res.status}`);
        return;
      }
      const data = await res.json() as RoutineRunsResponse;
      setRuns(data.runs);
      setTotal(data.total);
      setError(null);
      setLastFetch(Date.now());
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchRuns();
    const t = setInterval(fetchRuns, 60_000);
    return () => clearInterval(t);
  }, [fetchRuns]);

  return (
    <div className="flex flex-col flex-1">
      {/* Header */}
      <div
        className="flex items-center justify-between px-3 sm:px-4 py-2 shrink-0 flex-wrap gap-2"
        style={{ borderBottom: "1px solid var(--border)" }}
      >
        <div className="flex items-center gap-3">
          <span className="font-mono text-xs uppercase tracking-widest" style={{ color: "var(--text-muted)" }}>
            Routines
            <span className="hidden sm:inline"> — {total} total</span>
            <span className="sm:hidden"> ({total})</span>
          </span>
        </div>
        <div className="flex items-center gap-3">
          {lastFetch > 0 && (
            <span className="font-mono text-[10px] hidden sm:inline" style={{ color: "var(--text-dim)" }}>
              {new Date(lastFetch).toLocaleTimeString()}
            </span>
          )}
          <button
            onClick={() => void fetchRuns()}
            className="font-mono text-[10px] px-3 min-h-[36px] transition-opacity hover:opacity-70"
            style={{ border: "1px solid var(--border)", color: "var(--text-muted)" }}
          >
            REFRESH
          </button>
        </div>
      </div>

      {/* Summary bar */}
      <SummaryBar runs={runs} />

      {/* Error */}
      {error && (
        <div className="px-3 sm:px-4 py-3" style={{ borderBottom: "1px solid var(--border)" }}>
          <span className="font-mono text-xs" style={{ color: "#F87171" }}>
            {error.includes("unreachable") || error.includes("502")
              ? "Pi CEO server offline. Start with: cd app && uvicorn server.main:app --host 127.0.0.1 --port 7777"
              : error}
          </span>
        </div>
      )}

      {/* Column headers */}
      {!loading && !error && (
        <div
          className="grid px-3 sm:px-4 py-1.5 gap-2"
          style={{
            gridTemplateColumns: "28px 1fr 80px 56px 52px 52px",
            borderBottom: "1px solid var(--border)",
            background: "var(--panel)",
          }}
        >
          <span />
          <span className="font-mono text-[10px] uppercase tracking-widest" style={{ color: "var(--text-dim)" }}>Routine / Repo</span>
          <span className="font-mono text-[10px] uppercase tracking-widest text-right hidden sm:block" style={{ color: "var(--text-dim)" }}>Time</span>
          <span className="font-mono text-[10px] uppercase tracking-widest text-center" style={{ color: "var(--text-dim)" }}>Source</span>
          <span className="font-mono text-[10px] uppercase tracking-widest text-right" style={{ color: "var(--text-dim)" }}>Dur</span>
          <span />
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="flex flex-1 items-center justify-center">
          <span className="font-mono text-xs" style={{ color: "var(--text-dim)" }}>Loading…</span>
        </div>
      )}

      {/* Empty */}
      {!loading && !error && runs.length === 0 && (
        <div className="flex flex-col flex-1 items-center justify-center px-4 text-center">
          <p className="font-mono text-xs" style={{ color: "var(--text-muted)" }}>No routine runs recorded yet.</p>
          <p className="font-mono text-[10px] mt-2" style={{ color: "var(--text-dim)" }}>
            POST to /api/webhook/routine-complete with X-Pi-CEO-Secret to log a run.
          </p>
        </div>
      )}

      {/* Run list */}
      {!loading && runs.length > 0 && (
        <div className="overflow-y-auto flex-1">
          {runs.map((r, i) => (
            <RunRow key={`${r.routine_name}-${r.ts}-${i}`} run={r} />
          ))}
        </div>
      )}
    </div>
  );
}
