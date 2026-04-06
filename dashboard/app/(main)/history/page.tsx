// app/(main)/history/page.tsx — past analysis sessions stored in localStorage
"use client";

import { useState, useEffect } from "react";
import type { Session } from "@/lib/types";

const HISTORY_KEY = "pi-ceo-history";

function StatusBadge({ status }: { status: "running" | "done" | "error" | "idle" }) {
  const color = { running: "#E8751A", done: "#4ADE80", error: "#F87171", idle: "#888480" }[status];
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
        <p className="font-mono text-[12px]" style={{ color: "#C8C5C0" }}>No analysis sessions yet.</p>
        <p className="font-mono text-[10px] mt-2" style={{ color: "#888480" }}>
          Run an analysis from the Dashboard to see history here.
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col flex-1">
      <div
        className="flex items-center justify-between px-4 py-2 shrink-0"
        style={{ borderBottom: "1px solid #2A2727" }}
      >
        <span className="font-mono text-[10px] uppercase tracking-widest" style={{ color: "#C8C5C0" }}>
          Analysis History — {sessions.length} sessions
        </span>
        <button
          onClick={clearHistory}
          className="font-mono text-[9px] transition-colors"
          style={{ color: "#888480" }}
          onMouseOver={(e) => (e.currentTarget.style.color = "#F87171")}
          onMouseOut={(e) => (e.currentTarget.style.color = "#888480")}
        >
          CLEAR ALL
        </button>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr style={{ borderBottom: "1px solid #2A2727" }}>
              {["REPO", "BRANCH", "DATE", "QUALITY", "ZTE", "STATUS", "PR"].map((h) => (
                <th
                  key={h}
                  className="font-mono text-[9px] uppercase text-left px-4 py-2"
                  style={{ color: "#C8C5C0" }}
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
                  style={{ borderBottom: "1px solid #1E1C1C" }}
                  onMouseOver={(e) => (e.currentTarget.style.background = "#141414")}
                  onMouseOut={(e) => (e.currentTarget.style.background = "transparent")}
                >
                  <td className="px-4 py-2">
                    <a
                      href={s.repoUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="font-mono text-[11px]"
                      style={{ color: "#F0EDE8" }}
                      onMouseOver={(e) => (e.currentTarget.style.color = "#E8751A")}
                      onMouseOut={(e) => (e.currentTarget.style.color = "#F0EDE8")}
                    >
                      {s.repoName}
                    </a>
                  </td>
                  <td className="px-4 py-2">
                    <span className="font-mono text-[10px]" style={{ color: "#C8C5C0" }}>{s.branch}</span>
                  </td>
                  <td className="px-4 py-2">
                    <span className="font-mono text-[10px]" style={{ color: "#A8A5A0" }}>
                      {new Date(s.startedAt).toISOString().slice(0, 10)}
                    </span>
                  </td>
                  <td className="px-4 py-2">
                    <span
                      className="font-mono text-[11px]"
                      style={{ color: avg !== null ? (avg >= 7 ? "#4ADE80" : avg >= 5 ? "#FFD166" : "#F87171") : "#888480" }}
                    >
                      {avg !== null ? `${avg}/10` : "—"}
                    </span>
                  </td>
                  <td className="px-4 py-2">
                    <span className="font-mono text-[11px]" style={{ color: "#E8E4DE" }}>
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
                        className="font-mono text-[10px]"
                        style={{ color: "#E8751A" }}
                      >
                        OPEN ↗
                      </a>
                    ) : (
                      <span className="font-mono text-[10px]" style={{ color: "#888480" }}>—</span>
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
