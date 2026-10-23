"use client";
// app/(main)/routines/page.tsx — Routine run outcome tracker (RA-1011)

import { useEffect, useRef, useState, useCallback } from "react";
import { fetchProxy } from "@/lib/pi-ceo-fetch";
import {
  ROUTINES_LIST_NOTE, STATUS_COLOR, STATUS_ICON, TRIGGER_LABEL, fmtClock, fmtDuration, fmtTs, repoShort,
} from "@/lib/control/routine-format";
import { RoutineSummaryBar, type RoutineRun } from "@/components/control/RoutineSummaryBar";

interface RoutineRunsResponse {
  runs: RoutineRun[];
  total: number;
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
  const [checking, setChecking] = useState(false);

  // Refresh and the 60 s timer can overlap: only the latest request may update the page.
  const latestRead = useRef(0);

  const fetchRuns = useCallback(async () => {
    const read = ++latestRead.current;
    setChecking(true);
    try {
      // 200-with-empty from the proxy used to read as "no routines have run",
      // a claim about the scheduler nothing observed — lib/pi-ceo-fetch.ts.
      const r = await fetchProxy<RoutineRunsResponse>("/api/routines?limit=50");
      if (read !== latestRead.current) return;
      if (!r.ok) {
        setError(r.reason === "unreachable" ? "Pi-CEO backend unreachable" : `HTTP ${r.upstreamStatus ?? "error"}`);
        return;
      }
      const data = r.data;
      setRuns(data.runs);
      setTotal(data.total);
      setError(null);
      setLastFetch(Date.now());
    } catch (e) {
      if (read === latestRead.current) setError(String(e));
    } finally {
      if (read === latestRead.current) {
        setChecking(false);
        setLoading(false);
      }
    }
  }, []);

  // lastFetch is set only on a successful read, so it marks counts that were actually observed.
  const hasCounts = lastFetch > 0;
  // Retained totals say whether they are being re-read or are from the last good check.
  const totalNote = checking ? ", checking" : error !== null ? ", last good check" : "";

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
            {hasCounts && <span className="hidden sm:inline"> — {ROUTINES_LIST_NOTE} {total} total{totalNote}</span>}
            {hasCounts && <span className="sm:hidden"> ({total}{totalNote})</span>}
          </span>
        </div>
        <div className="flex items-center gap-3">
          {lastFetch > 0 && (
            <span className="font-mono text-[10px] hidden sm:inline" style={{ color: "var(--text-dim)" }}>
              {fmtClock(lastFetch)}
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

      {/* Summary bar — counts exist only once a read has succeeded; a later failed refresh keeps them, labelled */}
      {hasCounts && <RoutineSummaryBar runs={runs} checking={checking} failed={error !== null} asOf={lastFetch} />}

      {/* Error: a failed read is "couldn't check", never zero runs */}
      {error && (
        <div className="px-3 sm:px-4 py-3" style={{ borderBottom: "1px solid var(--border)" }}>
          <span className="font-mono text-xs" style={{ color: "#F87171" }}>
            Couldn&apos;t check routines: {error}
            {(error.includes("unreachable") || error.includes("502")) && " — Pi CEO server offline. Start with: cd app && uvicorn server.main:app --host 127.0.0.1 --port 7777"}
            {hasCounts && ` Showing the last good check, from ${fmtClock(lastFetch)}.`}
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
      {!loading && !error && !checking && runs.length === 0 && (
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
