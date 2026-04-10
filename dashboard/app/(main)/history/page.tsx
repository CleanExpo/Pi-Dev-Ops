// app/(main)/history/page.tsx — analysis session history from Supabase
import { createServerClient } from "@/lib/supabase/server";
import ClearHistoryButton from "@/components/ClearHistoryButton";
import type { AnalysisResult } from "@/lib/types";

interface SessionRow {
  id:           string;
  repo_url:     string;
  repo_name:    string;
  branch:       string;
  pr_url:       string | null;
  status:       "running" | "done" | "error";
  trigger:      "manual" | "webhook" | "cron";
  started_at:   string;
  completed_at: string | null;
  result:       Partial<AnalysisResult> | null;
}

const TRIGGER_COLOR = { manual: "var(--c-muted)", webhook: "var(--c-orange)", cron: "#4ADE80" };
const STATUS_COLOR  = { running: "var(--c-orange)", done: "#4ADE80", error: "#F87171" };

function QualityScore({ result }: { result: Partial<AnalysisResult> | null }) {
  const q = result?.quality;
  if (!q) return <span className="font-mono text-xs" style={{ color: "var(--c-chrome)" }}>—</span>;
  const avg = Math.round((q.completeness + q.correctness + q.codeQuality + q.documentation) / 4);
  const color = avg >= 7 ? "#4ADE80" : avg >= 5 ? "#FFD166" : "#F87171";
  return <span className="font-mono text-xs" style={{ color }}>{avg}/10</span>;
}

export default async function HistoryPage() {
  let sessions: SessionRow[] = [];

  try {
    const supabase = createServerClient();
    const { data } = await supabase
      .from("sessions")
      .select("id,repo_url,repo_name,branch,pr_url,status,trigger,started_at,completed_at,result")
      .order("started_at", { ascending: false })
      .limit(100);
    sessions = (data ?? []) as SessionRow[];
  } catch {
    // Supabase not configured yet
  }

  if (sessions.length === 0) {
    return (
      <div className="flex flex-col flex-1 items-center justify-center px-4 text-center">
        <p className="font-mono text-xs" style={{ color: "var(--c-muted)" }}>No analysis sessions yet.</p>
        <p className="font-mono text-[10px] mt-2" style={{ color: "var(--c-chrome)" }}>
          Run an analysis from the Dashboard to see history here.
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col flex-1">
      {/* Header */}
      <div className="flex items-center justify-between px-3 sm:px-4 py-2 shrink-0 flex-wrap gap-2"
        style={{ borderBottom: "1px solid var(--c-border)" }}>
        <span className="font-mono text-xs uppercase tracking-widest" style={{ color: "var(--c-muted)" }}>
          History
          <span className="hidden sm:inline"> — {sessions.length} sessions</span>
          <span className="sm:hidden"> ({sessions.length})</span>
        </span>
        <ClearHistoryButton />
      </div>

      {/* ── Desktop table — hidden below md ───────────────────────── */}
      <div className="hidden md:block overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr style={{ borderBottom: "1px solid var(--c-border)" }}>
              {["REPO", "BRANCH", "DATE", "QUALITY", "ZTE", "TRIGGER", "STATUS", "PR"].map((h) => (
                <th key={h} className="font-mono text-[10px] uppercase text-left px-4 py-2"
                  style={{ color: "var(--c-muted)" }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sessions.map((s) => (
              <tr key={s.id} style={{ borderBottom: "1px solid var(--c-border)" }}
                className="transition-colors"
                onMouseEnter={undefined}>
                <td className="px-4 py-2">
                  <a href={s.repo_url} target="_blank" rel="noopener noreferrer"
                    className="font-mono text-xs hover:underline transition-colors"
                    style={{ color: "var(--c-text)" }}>
                    {s.repo_name}
                  </a>
                </td>
                <td className="px-4 py-2">
                  <span className="font-mono text-[10px]" style={{ color: "var(--c-muted)" }}>
                    {s.branch || "—"}
                  </span>
                </td>
                <td className="px-4 py-2">
                  <span className="font-mono text-[10px]" style={{ color: "var(--c-chrome)" }}>
                    {new Date(s.started_at).toISOString().slice(0, 10)}
                  </span>
                </td>
                <td className="px-4 py-2"><QualityScore result={s.result} /></td>
                <td className="px-4 py-2">
                  <span className="font-mono text-xs" style={{ color: "var(--c-cream)" }}>
                    {s.result?.zteScore !== undefined ? `${s.result.zteScore}/60` : "—"}
                  </span>
                </td>
                <td className="px-4 py-2">
                  <span className="font-mono text-[10px] uppercase"
                    style={{ color: TRIGGER_COLOR[s.trigger] ?? "var(--c-chrome)" }}>
                    {s.trigger}
                  </span>
                </td>
                <td className="px-4 py-2">
                  <span className="font-mono text-[10px] uppercase"
                    style={{ color: STATUS_COLOR[s.status] }}>
                    {s.status}
                  </span>
                </td>
                <td className="px-4 py-2">
                  {s.pr_url
                    ? <a href={s.pr_url} target="_blank" rel="noopener noreferrer"
                        className="font-mono text-[10px] hover:opacity-70" style={{ color: "var(--c-orange)" }}>
                        OPEN ↗
                      </a>
                    : <span className="font-mono text-[10px]" style={{ color: "var(--c-chrome)" }}>—</span>
                  }
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* ── Mobile/tablet cards — visible below md ────────────────── */}
      <div className="md:hidden flex flex-col divide-y" style={{ borderColor: "var(--c-border)" }}>
        {sessions.map((s) => (
          <div key={s.id} className="px-3 py-3 flex flex-col gap-2">
            {/* Repo + PR link */}
            <div className="flex items-start justify-between gap-2">
              <a
                href={s.repo_url}
                target="_blank"
                rel="noopener noreferrer"
                className="font-mono text-xs break-all flex-1"
                style={{ color: "var(--c-text)" }}
              >
                {s.repo_name}
              </a>
              {s.pr_url && (
                <a
                  href={s.pr_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="font-mono text-[10px] shrink-0"
                  style={{ color: "var(--c-orange)" }}
                >
                  PR ↗
                </a>
              )}
            </div>

            {/* Meta row: status + trigger + date */}
            <div className="flex items-center gap-3 flex-wrap">
              <span
                className="font-mono text-[10px] uppercase"
                style={{ color: STATUS_COLOR[s.status] }}
              >
                {s.status}
              </span>
              <span
                className="font-mono text-[10px] uppercase"
                style={{ color: TRIGGER_COLOR[s.trigger] ?? "var(--c-chrome)" }}
              >
                {s.trigger}
              </span>
              <span className="font-mono text-[10px]" style={{ color: "var(--c-chrome)" }}>
                {new Date(s.started_at).toISOString().slice(0, 10)}
              </span>
            </div>

            {/* Scores + branch */}
            <div className="flex items-center gap-4 flex-wrap">
              <div className="flex items-center gap-1">
                <span className="font-mono text-[10px]" style={{ color: "var(--c-chrome)" }}>Q:</span>
                <QualityScore result={s.result} />
              </div>
              <div className="flex items-center gap-1">
                <span className="font-mono text-[10px]" style={{ color: "var(--c-chrome)" }}>ZTE:</span>
                <span className="font-mono text-xs" style={{ color: "var(--c-cream)" }}>
                  {s.result?.zteScore !== undefined ? `${s.result.zteScore}/60` : "—"}
                </span>
              </div>
              {s.branch && (
                <span className="font-mono text-[10px]" style={{ color: "var(--c-muted)" }}>
                  {s.branch}
                </span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
