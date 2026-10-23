// components/control/RoutineSummaryBar.tsx — counts strip for /routines (RA-1011).
// Only rendered once a read has succeeded; while a refresh is unsettled, or
// after one failed, it does not restate an earlier empty read as current.
import { fmtTs } from "@/lib/control/routine-format";

export interface RoutineRun {
  routine_name: string;
  repo: string;
  trigger: string;
  status: "success" | "failure" | "timeout";
  duration_s: number;
  run_url: string;
  summary: string;
  ts: string;
}

// "Today" is the Brisbane calendar day, not the UTC one (a 08:00 AEST run is the previous UTC day).
const brisbaneDay = (d: Date) => d.toLocaleDateString("en-CA", { timeZone: "Australia/Brisbane" });

// `asOf` is when `runs` was read: after a failed refresh the retained runs are counted against the day of
// that read, never against a later day they cannot describe.
export function RoutineSummaryBar({ runs, checking, failed, asOf = Date.now() }: { runs: RoutineRun[]; checking: boolean; failed: boolean; asOf?: number }) {
  const today = brisbaneDay(new Date(asOf));
  const qualifier = checking ? ", checking" : failed ? ", last good check" : "";
  const todayRuns = runs.filter((r) => brisbaneDay(new Date(r.ts)) === today);
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
          {todayRuns.length}{qualifier}
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
            {successRate}%{qualifier}
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

      {runs.length === 0 && !checking && (
        <span className="font-mono text-[10px]" style={{ color: "var(--text-dim)" }}>
          {failed ? "None at the last good check." : "No runs recorded yet."}
        </span>
      )}

      {checking && (
        <span className="font-mono text-[10px]" style={{ color: "var(--text-dim)" }}>
          Checking again…
        </span>
      )}
    </div>
  );
}
