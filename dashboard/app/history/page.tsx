// app/history/page.tsx — past analysis sessions stored in localStorage
"use client";

import { useState, useEffect } from "react";
import type { Session } from "@/lib/types";

const HISTORY_KEY = "pi-ceo-history";

function StatusBadge({ status }: { status: "running" | "done" | "error" | "idle" }) {
  const color = { running: "#E8751A", done: "#4CAF82", error: "#EF4444", idle: "#777" }[status];
  return (
    <span className="font-mono text-[9px]" style={{ color }}>
      {status.toUpperCase()}
    </span>
  );
}

export default function HistoryPage() {
  const [sessions, setSessions] = useState<Session[]>([]);

  useEffect(() => {
    try {
      const stored = localStorage.getItem(HISTORY_KEY);
      if (stored) setSessions((JSON.parse(stored) as Session[]).reverse());
    } catch { /* ignore */ }
  }, []);

  function clearHistory() {
    localStorage.removeItem(HISTORY_KEY);
    setSessions([]);
  }

  if (sessions.length === 0) {
    return (
      <div className="flex flex-col flex-1 items-center justify-center">
        <p className="font-mono text-[12px] text-[#888]">No analysis sessions yet.</p>
        <p className="font-mono text-[10px] text-[#666] mt-2">
          Run an analysis from the Dashboard to see history here.
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col flex-1">
      <div
        className="flex items-center justify-between px-4 py-2 shrink-0"
        style={{ borderBottom: "1px solid #252525" }}
      >
        <span className="font-mono text-[10px] text-[#999] uppercase tracking-widest">
          Analysis History — {sessions.length} sessions
        </span>
        <button
          onClick={clearHistory}
          className="font-mono text-[9px] text-[#777] hover:text-red transition-colors"
        >
          CLEAR ALL
        </button>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr style={{ borderBottom: "1px solid #252525" }}>
              {["REPO", "BRANCH", "DATE", "QUALITY", "ZTE", "STATUS", "PR"].map((h) => (
                <th
                  key={h}
                  className="font-mono text-[9px] text-[#888] uppercase text-left px-4 py-2"
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sessions.map((s) => {
              const q = s.result?.quality;
              const avg = q
                ? Math.round((q.completeness + q.correctness + q.codeQuality + q.documentation) / 4)
                : null;
              return (
                <tr
                  key={s.id}
                  className="hover:bg-[#141414] transition-colors"
                  style={{ borderBottom: "1px solid #1E1E1E" }}
                >
                  <td className="px-4 py-2">
                    <a
                      href={s.repoUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="font-mono text-[11px] text-text hover:text-orange transition-colors"
                    >
                      {s.repoName}
                    </a>
                  </td>
                  <td className="px-4 py-2">
                    <span className="font-mono text-[10px] text-[#999]">{s.branch}</span>
                  </td>
                  <td className="px-4 py-2">
                    <span className="font-mono text-[10px] text-[#888]">
                      {new Date(s.startedAt).toISOString().slice(0, 10)}
                    </span>
                  </td>
                  <td className="px-4 py-2">
                    <span
                      className="font-mono text-[11px]"
                      style={{ color: avg !== null ? (avg >= 7 ? "#4CAF82" : avg >= 5 ? "#FFD166" : "#EF4444") : "#777" }}
                    >
                      {avg !== null ? `${avg}/10` : "—"}
                    </span>
                  </td>
                  <td className="px-4 py-2">
                    <span className="font-mono text-[11px] text-[#BBB]">
                      {s.result?.zteScore !== undefined ? `${s.result.zteScore}/60` : "—"}
                    </span>
                  </td>
                  <td className="px-4 py-2">
                    <StatusBadge status={s.completedAt ? "done" : "idle"} />
                  </td>
                  <td className="px-4 py-2">
                    {s.previewUrl ? (
                      <a
                        href={s.previewUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="font-mono text-[10px] text-orange hover:underline"
                      >
                        OPEN ↗
                      </a>
                    ) : (
                      <span className="font-mono text-[10px] text-[#666]">—</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
