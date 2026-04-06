// app/(main)/dashboard/page.tsx — analysis dashboard: repo input, terminal, phases, results
"use client";

import { useState, useEffect } from "react";
import Terminal from "@/components/Terminal";
import PhaseTracker from "@/components/PhaseTracker";
import ResultCards from "@/components/ResultCards";
import { useSSE } from "@/hooks/useSSE";

const STORAGE_KEY = "pi-ceo-token";

function sanitize(s: string): string {
  return s.replace(/[<>"&]/g, "");
}

export default function Dashboard() {
  const [repo, setRepo] = useState("");
  const [token, setToken] = useState("");
  const { lines, phases, result, branch, prUrl, status, error, start, stop } = useSSE();

  useEffect(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) setToken(stored);
  }, []);

  function saveToken(t: string) {
    setToken(t);
    localStorage.setItem(STORAGE_KEY, t);
  }

  function handleAnalyze() {
    if (!repo.trim()) return;
    start(sanitize(repo.trim()), token.trim());
  }

  const running = status === "running";

  return (
    <div className="flex flex-col flex-1 min-h-0" style={{ height: "calc(100vh - 40px)" }}>
      {/* Input bar */}
      <div
        className="flex items-center gap-3 px-3 py-2 shrink-0"
        style={{ borderBottom: "1px solid #2A2727", background: "#0A0A0A" }}
      >
        <span className="font-mono text-[10px] shrink-0" style={{ color: "#C8C5C0" }}>REPO</span>
        <input
          type="text"
          value={repo}
          onChange={(e) => setRepo(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && !running && handleAnalyze()}
          placeholder="https://github.com/owner/repo"
          disabled={running}
          className="flex-1 font-mono text-[12px] border-0 outline-none disabled:opacity-50 px-2 py-1"
          style={{
            background: "#141414",
            color: "#F0EDE8",
            border: "1px solid #3A3632",
          }}
          aria-label="GitHub repository URL"
        />
        <span className="font-mono text-[10px] shrink-0" style={{ color: "#C8C5C0" }}>TOKEN</span>
        <input
          type="password"
          value={token}
          onChange={(e) => saveToken(e.target.value)}
          placeholder="ghp_..."
          className="w-28 font-mono text-[11px] border-0 outline-none px-2 py-1"
          style={{
            background: "#141414",
            color: "#F0EDE8",
            border: "1px solid #3A3632",
          }}
          aria-label="GitHub personal access token"
        />
        <button
          onClick={running ? stop : handleAnalyze}
          disabled={!running && !repo.trim()}
          className="font-mono text-[11px] px-5 py-1.5 disabled:opacity-30 transition-opacity shrink-0"
          style={{
            background: running ? "#F87171" : "#E8751A",
            color: "#FFFFFF",
            fontWeight: 700,
            letterSpacing: "0.12em",
          }}
        >
          {running ? "STOP" : "ANALYZE"}
        </button>
      </div>

      {error && (
        <div
          className="px-4 py-1.5 font-mono text-[11px] shrink-0"
          style={{ background: "#1a0808", borderBottom: "1px solid #F87171", color: "#F87171" }}
        >
          ✗ {error}
        </div>
      )}

      {/* Two-column layout */}
      <div className="flex flex-1 min-h-0">
        {/* LEFT — Terminal */}
        <div className="flex-1 flex flex-col min-w-0" style={{ borderRight: "1px solid #2A2727" }}>
          <Terminal lines={lines} status={status} />
        </div>

        {/* RIGHT — Phases + Results */}
        <div className="w-72 xl:w-80 flex flex-col min-h-0 shrink-0" style={{ background: "#111111" }}>
          <PhaseTracker phases={phases} />
          <div className="flex-1 overflow-y-auto">
            <ResultCards result={result} />
          </div>
        </div>
      </div>

      {/* Status bar */}
      <div
        className="flex items-center justify-between px-4 py-1 shrink-0 font-mono text-[9px]"
        style={{ borderTop: "1px solid #2A2727", background: "#0A0A0A", color: "#888480" }}
      >
        <div className="flex items-center gap-4">
          <span>
            BRANCH: <span style={{ color: "#C8C5C0" }}>{branch ?? "—"}</span>
          </span>
          {prUrl && (
            <a href={prUrl} target="_blank" rel="noopener noreferrer" style={{ color: "#E8751A" }}>
              VIEW PR ↗
            </a>
          )}
        </div>
        <div className="flex items-center gap-4">
          <span>LINES: <span style={{ color: "#C8C5C0" }}>{lines.length}</span></span>
          <span>
            STATUS:{" "}
            <span style={{
              color: status === "running" ? "#E8751A" : status === "done" ? "#4ADE80" : status === "error" ? "#F87171" : "#888480"
            }}>
              {status.toUpperCase()}
            </span>
          </span>
          <span>{new Date().toISOString().slice(0, 19).replace("T", " ")} UTC</span>
        </div>
      </div>
    </div>
  );
}
