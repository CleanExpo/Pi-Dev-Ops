// app/(main)/dashboard/page.tsx — analysis dashboard
"use client";

import { useState, useEffect, useRef } from "react";
import Terminal from "@/components/Terminal";
import PhaseTracker from "@/components/PhaseTracker";
import ResultCards from "@/components/ResultCards";
import ActionsPanel from "@/components/ActionsPanel";
import { useSSE } from "@/hooks/useSSE";

function sanitize(s: string): string {
  return s.replace(/[<>"&]/g, "");
}

type RightTab = "phases" | "results" | "actions";

export default function Dashboard() {
  const [repo, setRepo] = useState("");
  const [rightTab, setRightTab] = useState<RightTab>("phases");
  const resultsRef = useRef<HTMLDivElement>(null);
  const { lines, phases, result, branch, prUrl, status, error, start, stop } = useSSE();

  // Auto-switch to RESULTS tab when analysis completes
  useEffect(() => {
    if (status === "done") {
      setRightTab("results");
      setTimeout(() => resultsRef.current?.scrollTo({ top: 0, behavior: "smooth" }), 100);
    }
    if (status === "running") {
      setRightTab("phases");
    }
  }, [status]);

  function handleAnalyze() {
    if (!repo.trim()) return;
    // GitHub token is read server-side from Supabase settings — no need to pass it here
    start(sanitize(repo.trim()));
  }

  const running = status === "running";
  const hasResults = Object.keys(result).length > 2;

  const statusColor =
    status === "running" ? "#E8751A" :
    status === "done"    ? "#4ADE80" :
    status === "error"   ? "#F87171" : "#888480";

  return (
    <div
      className="flex flex-col"
      style={{ height: "calc(100vh - 40px)", overflow: "hidden" }}
    >
      {/* ── Input bar ───────────────────────────────────────────── */}
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
          className="flex-1 font-mono text-[12px] outline-none disabled:opacity-50 px-2 py-1"
          style={{ background: "#141414", color: "#F0EDE8", border: "1px solid #3A3632" }}
          aria-label="GitHub repository URL"
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

      {/* ── Main two-column layout ───────────────────────────────── */}
      <div className="flex min-h-0" style={{ flex: 1, overflow: "hidden" }}>

        {/* LEFT — Terminal */}
        <div
          className="flex flex-col min-w-0"
          style={{ flex: 1, overflow: "hidden", borderRight: "1px solid #2A2727" }}
        >
          <Terminal lines={lines} status={status} />
        </div>

        {/* RIGHT — Tabbed panel */}
        <div
          className="flex flex-col shrink-0"
          style={{ width: "320px", background: "#111111", overflow: "hidden" }}
        >
          {/* Tab bar */}
          <div className="flex shrink-0" style={{ borderBottom: "1px solid #2A2727" }}>
            {(["phases", "results", "actions"] as RightTab[]).map((tab) => {
              const active = rightTab === tab;
              const showDot = (tab === "results" && hasResults && rightTab !== "results")
                           || (tab === "actions" && status === "done" && rightTab !== "actions");
              return (
                <button
                  key={tab}
                  onClick={() => setRightTab(tab)}
                  className="flex-1 font-mono text-[10px] uppercase tracking-widest py-2 transition-colors relative"
                  style={{
                    color: active ? "#F0EDE8" : "#888480",
                    background: active ? "#181616" : "transparent",
                    borderBottom: active ? "1px solid #E8751A" : "1px solid transparent",
                    marginBottom: "-1px",
                  }}
                >
                  {tab}
                  {showDot && (
                    <span
                      className="inline-block w-1.5 h-1.5 rounded-full ml-1.5 align-middle"
                      style={{ background: "#4ADE80" }}
                    />
                  )}
                </button>
              );
            })}
          </div>

          {/* Tab content */}
          <div className="flex-1 min-h-0 overflow-hidden relative">
            <div
              className="absolute inset-0 overflow-y-auto"
              style={{ display: rightTab === "phases" ? "block" : "none" }}
            >
              <PhaseTracker phases={phases} />
            </div>

            <div
              ref={resultsRef}
              className="absolute inset-0 overflow-y-auto"
              style={{ display: rightTab === "results" ? "block" : "none" }}
            >
              {hasResults ? (
                <ResultCards result={result} />
              ) : (
                <div className="px-4 py-8 text-center">
                  <p className="font-mono text-[10px]" style={{ color: "#888480" }}>
                    Results appear here as phases complete.
                  </p>
                </div>
              )}
            </div>

            <div
              className="absolute inset-0 overflow-y-auto"
              style={{ display: rightTab === "actions" ? "block" : "none" }}
            >
              <ActionsPanel result={result} branch={branch} />
            </div>
          </div>
        </div>
      </div>

      {/* ── Status bar ──────────────────────────────────────────── */}
      <div
        className="flex items-center justify-between px-4 py-1 shrink-0 font-mono text-[9px]"
        style={{ borderTop: "1px solid #2A2727", background: "#0A0A0A", color: "#888480" }}
      >
        <div className="flex items-center gap-4">
          <span>BRANCH: <span style={{ color: "#C8C5C0" }}>{branch ?? "—"}</span></span>
          {prUrl && (
            <a href={prUrl} target="_blank" rel="noopener noreferrer" style={{ color: "#E8751A" }}>
              VIEW PR ↗
            </a>
          )}
        </div>
        <div className="flex items-center gap-4">
          <span>LINES: <span style={{ color: "#C8C5C0" }}>{lines.length}</span></span>
          <span>
            STATUS: <span style={{ color: statusColor }}>{status.toUpperCase()}</span>
          </span>
          {status === "done" && rightTab !== "results" && (
            <button
              onClick={() => { setRightTab("results"); resultsRef.current?.scrollTo({ top: 0 }); }}
              className="font-mono text-[9px] tracking-wider"
              style={{ color: "#4ADE80" }}
            >
              VIEW RESULTS →
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
