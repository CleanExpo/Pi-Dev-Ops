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

const TRIGGER_COLOR = { manual: "#C8C5C0", webhook: "#E8751A", cron: "#4ADE80" };
const STATUS_COLOR  = { running: "#E8751A", done: "#4ADE80", error: "#F87171" };

function QualityScore({ result }: { result: Partial<AnalysisResult> | null }) {
  const q = result?.quality;
  if (!q) return <span className="font-mono text-[11px]" style={{ color: "#888480" }}>—</span>;
  const avg = Math.round((q.completeness + q.correctness + q.codeQuality + q.documentation) / 4);
  const color = avg >= 7 ? "#4ADE80" : avg >= 5 ? "#FFD166" : "#F87171";
  return <span className="font-mono text-[11px]" style={{ color }}>{avg}/10</span>;
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
      <div className="flex flex-col flex-1 items-center justify-center">
        <p className="font-mono text-[12px]" style={{ color: "#C8C5C0" }}>No analysis sessions yet.</p>
        <p className="font-mono text-[10px] mt-2" style={{ color: "#888480" }}>
          Run an analysis from the Dashboard to see history here.
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col flex-1">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2 shrink-0"
        style={{ borderBottom: "1px solid #2A2727" }}>
        <span className="font-mono text-[10px] uppercase tracking-widest" style={{ color: "#C8C5C0" }}>
          Analysis History — {sessions.length} sessions
        </span>
        <ClearHistoryButton />
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr style={{ borderBottom: "1px solid #2A2727" }}>
              {["REPO", "BRANCH", "DATE", "QUALITY", "ZTE", "TRIGGER", "STATUS", "PR"].map((h) => (
                <th key={h} className="font-mono text-[9px] uppercase text-left px-4 py-2"
                  style={{ color: "#C8C5C0" }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sessions.map((s) => (
              <tr key={s.id} style={{ borderBottom: "1px solid #1E1C1C" }}
                className="hover:bg-[#141414] transition-colors">
                <td className="px-4 py-2">
                  <a href={s.repo_url} target="_blank" rel="noopener noreferrer"
                    className="font-mono text-[11px] hover:text-[#E8751A] transition-colors"
                    style={{ color: "#F0EDE8" }}>
                    {s.repo_name}
                  </a>
                </td>
                <td className="px-4 py-2">
                  <span className="font-mono text-[10px]" style={{ color: "#C8C5C0" }}>
                    {s.branch || "—"}
                  </span>
                </td>
                <td className="px-4 py-2">
                  <span className="font-mono text-[10px]" style={{ color: "#A8A5A0" }}>
                    {new Date(s.started_at).toISOString().slice(0, 10)}
                  </span>
                </td>
                <td className="px-4 py-2"><QualityScore result={s.result} /></td>
                <td className="px-4 py-2">
                  <span className="font-mono text-[11px]" style={{ color: "#E8E4DE" }}>
                    {s.result?.zteScore !== undefined ? `${s.result.zteScore}/60` : "—"}
                  </span>
                </td>
                <td className="px-4 py-2">
                  <span className="font-mono text-[9px] uppercase"
                    style={{ color: TRIGGER_COLOR[s.trigger] ?? "#888480" }}>
                    {s.trigger}
                  </span>
                </td>
                <td className="px-4 py-2">
                  <span className="font-mono text-[9px] uppercase"
                    style={{ color: STATUS_COLOR[s.status] }}>
                    {s.status}
                  </span>
                </td>
                <td className="px-4 py-2">
                  {s.pr_url
                    ? <a href={s.pr_url} target="_blank" rel="noopener noreferrer"
                        className="font-mono text-[10px] hover:opacity-70" style={{ color: "#E8751A" }}>
                        OPEN ↗
                      </a>
                    : <span className="font-mono text-[10px]" style={{ color: "#888480" }}>—</span>
                  }
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
