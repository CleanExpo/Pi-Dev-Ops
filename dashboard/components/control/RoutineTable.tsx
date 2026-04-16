// components/control/RoutineTable.tsx — Panel 4 subsection: last 10 routine runs (RA-1092)
"use client";

import { useCallback, useEffect, useState } from "react";

interface RoutineRun {
  routine_name: string;
  repo: string;
  trigger: string;
  status: "success" | "failure" | "timeout";
  duration_s: number;
  run_url: string;
  summary: string;
  ts: string;
  session_id?: string;
  evaluator_score?: number | null;
  push_outcome?: string;
}

interface RoutineRunsResponse {
  runs: RoutineRun[];
  total: number;
}

const STATUS_COLOUR: Record<string, string> = {
  success: "#4ADE80",
  failure: "#F87171",
  timeout: "#FFD166",
};

const STATUS_ICON: Record<string, string> = {
  success: "✓",
  failure: "✗",
  timeout: "⏱",
};

function fmtTs(ts: string): string {
  if (!ts) return "—";
  try {
    return new Date(ts).toLocaleString(undefined, {
      month: "short",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return ts;
  }
}

export default function RoutineTable() {
  const [runs, setRuns] = useState<RoutineRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchRuns = useCallback(async () => {
    try {
      const res = await fetch("/api/pi-ceo/api/routines?limit=10");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = (await res.json()) as RoutineRunsResponse;
      setRuns(Array.isArray(data.runs) ? data.runs : []);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load routines");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchRuns();
    const t = setInterval(() => void fetchRuns(), 60_000);
    return () => clearInterval(t);
  }, [fetchRuns]);

  return (
    <div className="flex flex-col min-h-0">
      <div
        className="flex items-center justify-between px-1 py-1.5"
        style={{ borderBottom: "1px solid var(--border)" }}
      >
        <span className="text-[10px] uppercase tracking-widest" style={{ color: "var(--text-dim)" }}>
          Last 10 runs
        </span>
        <button
          onClick={() => void fetchRuns()}
          className="text-[10px] font-mono hover:opacity-70"
          style={{ color: "var(--text-muted)" }}
        >
          refresh
        </button>
      </div>

      {loading && (
        <p className="text-xs px-1 py-2" style={{ color: "var(--text-dim)" }}>
          Loading…
        </p>
      )}

      {error && !loading && (
        <p className="text-xs px-1 py-2" style={{ color: "var(--error)" }}>
          {error}
        </p>
      )}

      {!loading && !error && runs.length === 0 && (
        <p className="text-xs px-1 py-2" style={{ color: "var(--text-dim)" }}>
          No runs recorded.
        </p>
      )}

      {!loading && !error && runs.length > 0 && (
        <div className="overflow-y-auto flex-1">
          <table className="w-full font-mono text-[10px]" style={{ borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ borderBottom: "1px solid var(--border)" }}>
                <th className="text-left px-1 py-1.5 font-normal" style={{ color: "var(--text-dim)" }}>
                  Session
                </th>
                <th className="text-left px-1 py-1.5 font-normal" style={{ color: "var(--text-dim)" }}>
                  Trigger
                </th>
                <th className="text-left px-1 py-1.5 font-normal" style={{ color: "var(--text-dim)" }}>
                  Status
                </th>
                <th className="text-right px-1 py-1.5 font-normal" style={{ color: "var(--text-dim)" }}>
                  Eval
                </th>
                <th className="text-right px-1 py-1.5 font-normal" style={{ color: "var(--text-dim)" }}>
                  Push
                </th>
              </tr>
            </thead>
            <tbody>
              {runs.map((r, i) => {
                const colour = STATUS_COLOUR[r.status] ?? "var(--text-dim)";
                const sid = r.session_id ?? r.routine_name;
                return (
                  <tr
                    key={`${sid}-${r.ts}-${i}`}
                    style={{ borderBottom: "1px solid var(--border)" }}
                  >
                    <td className="px-1 py-1.5">
                      <div className="truncate max-w-[120px]" style={{ color: "var(--text)" }}>
                        {sid.slice(0, 12)}
                      </div>
                      <div className="text-[9px]" style={{ color: "var(--text-dim)" }}>
                        {fmtTs(r.ts)}
                      </div>
                    </td>
                    <td className="px-1 py-1.5" style={{ color: "var(--text-muted)" }}>
                      {r.trigger}
                    </td>
                    <td className="px-1 py-1.5">
                      <span style={{ color: colour }}>
                        {STATUS_ICON[r.status] ?? "?"} {r.status}
                      </span>
                    </td>
                    <td className="px-1 py-1.5 text-right" style={{ color: "var(--text-muted)" }}>
                      {r.evaluator_score !== undefined && r.evaluator_score !== null
                        ? r.evaluator_score.toFixed(1)
                        : "—"}
                    </td>
                    <td className="px-1 py-1.5 text-right" style={{ color: "var(--text-muted)" }}>
                      {r.push_outcome ?? (r.status === "success" ? "ok" : "—")}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
