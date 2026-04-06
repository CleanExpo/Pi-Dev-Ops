// app/(main)/dashboard/page.tsx — analysis dashboard
"use client";

import { useState, useEffect, useRef } from "react";
import Terminal from "@/components/Terminal";
import PhaseTracker from "@/components/PhaseTracker";
import ResultCards from "@/components/ResultCards";
import { useSSE } from "@/hooks/useSSE";

const STORAGE_KEY = "pi-ceo-token";

function sanitize(s: string): string {
  return s.replace(/[<>"&]/g, "");
}

type RightTab = "phases" | "results";

export default function Dashboard() {
  const [repo, setRepo] = useState("");
  const [token, setToken] = useState("");
  const [rightTab, setRightTab] = useState<RightTab>("phases");
  const resultsRef = useRef<HTMLDivElement>(null);
  const { lines, phases, result, branch, prUrl, status, error, start, stop } = useSSE();

  useEffect(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) setToken(stored);
  }, []);

  // Auto-switch to RESULTS tab when analysis completes
  useEffect(() => {
    if (status === "done") {
      setRightTab("results");
      // Scroll results panel to top so user sees them immediately
      setTimeout(() => resultsRef.current?.scrollTo({ top: 0, behavior: "smooth" }), 100);
    }
    if (status === "running") {
      setRightTab("phases");
    }
  }, [status]);

  // Also switch to results when first result data arrives
  useEffect(() => {
    if (Object.keys(result).length > 2 && status === "running") {
      // Has real data beyond repoUrl/repoName — show results alongside phases
    }
  }, [result, status]);

  function saveToken(t: string) {
    setToken(t);
    localStorage.setItem(STORAGE_KEY, t);
  }

  function handleAnalyze() {
    if (!repo.trim()) return;
    start(sanitize(repo.trim()), token.trim());
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
        <span className="font-mono text-[10px] shrink-0" style={{ color: "#C8C5C0" }}>TOKEN</span>
        <input
          type="password"
          value={token}
          onChange={(e) => saveToken(e.target.value)}
          placeholder="ghp_..."
          className="w-28 font-mono text-[11px] outline-none px-2 py-1"
          style={{ background: "#141414", color: "#F0EDE8", border: "1px solid #3A3632" }}
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

      {/* ── Main two-column layout ───────────────────────────────── */}
      <div className="flex min-h-0" style={{ flex: 1, overflow: "hidden" }}>

        {/* LEFT — Terminal (fills and scrolls internally) */}
        <div
          className="flex flex-col min-w-0"
          style={{ flex: 1, overflow: "hidden", borderRight: "1px solid #2A2727" }}
        >
          <Terminal lines={lines} status={status} />
        </div>

        {/* RIGHT — Tabbed panel: PHASES | RESULTS */}
        <div
          className="flex flex-col shrink-0"
          style={{ width: "320px", background: "#111111", overflow: "hidden" }}
        >
          {/* Tab bar */}
          <div
            className="flex shrink-0"
            style={{ borderBottom: "1px solid #2A2727" }}
          >
            {(["phases", "results"] as RightTab[]).map((tab) => {
              const active = rightTab === tab;
              const showDot = tab === "results" && hasResults && rightTab !== "results";
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

          {/* Tab content — each fills the remaining height */}
          <div className="flex-1 min-h-0 overflow-hidden relative">
            {/* PHASES tab */}
            <div
              className="absolute inset-0 overflow-y-auto"
              style={{ display: rightTab === "phases" ? "block" : "none" }}
            >
              <PhaseTracker phases={phases} />
            </div>

            {/* RESULTS tab */}
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
