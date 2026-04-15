// app/(main)/dashboard/page.tsx — analysis command center
"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import Terminal from "@/components/Terminal";
import PhaseTracker from "@/components/PhaseTracker";
import ResultCards from "@/components/ResultCards";
import ActionsPanel from "@/components/ActionsPanel";
import BriefBuilder from "@/components/BriefBuilder";
import { Badge } from "@/components/ui/badge";
import { useSSE } from "@/hooks/useSSE";

function sanitize(s: string): string {
  return s.replace(/[<>"&]/g, "");
}

type RightTab = "phases" | "results" | "actions";

const SIDEBAR_MIN = 220;
const SIDEBAR_MAX = 640;
const SIDEBAR_DEFAULT = 320;


export default function Dashboard() {
  const [repo, setRepo] = useState("");
  const [brief, setBrief] = useState("");
  const [rightTab, setRightTab] = useState<RightTab>("phases");
  const [mobilePane, setMobilePane] = useState<"terminal" | "panel">("terminal");
  // Resizable sidebar state
  const [sidebarWidth, setSidebarWidth] = useState(SIDEBAR_DEFAULT);
  const isResizing = useRef(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const resultsRef = useRef<HTMLDivElement>(null);
  const { lines, phases, result, branch, prUrl, linearUrl, linearId, status, error, start, stop } = useSSE();

  // ── Drag-to-resize handlers ─────────────────────────────────────────────
  const onResizePointerDown = useCallback((e: React.PointerEvent) => {
    e.preventDefault();
    isResizing.current = true;
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
  }, []);

  const onResizePointerMove = useCallback((e: React.PointerEvent) => {
    if (!isResizing.current || !containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    const newWidth = Math.min(SIDEBAR_MAX, Math.max(SIDEBAR_MIN, rect.right - e.clientX));
    setSidebarWidth(newWidth);
  }, []);

  const onResizePointerUp = useCallback(() => {
    isResizing.current = false;
  }, []);

  // Auto-switch to RESULTS tab when analysis completes
  useEffect(() => {
    if (status === "done") {
      setRightTab("results");
      setMobilePane("panel");
      setTimeout(() => resultsRef.current?.scrollTo({ top: 0, behavior: "smooth" }), 100);
    }
    if (status === "running") {
      setRightTab("phases");
      setMobilePane("terminal");
    }
  }, [status]);

  const [submitting, setSubmitting] = useState(false);

  // Clear submitting flag once SSE confirms the session started (or errors)
  useEffect(() => {
    if (status !== "idle") setSubmitting(false);
  }, [status]);

  function handleAnalyze() {
    if (!repo.trim() || submitting) return;
    setSubmitting(true);
    start(sanitize(repo.trim()), brief.trim() || undefined);
  }

  const running = status === "running" || submitting;
  const hasResults = Object.keys(result).length > 2;

  const badgeVariant =
    status === "running" ? "default" :
    status === "done"    ? "success" :
    status === "error"   ? "destructive" : "outline";

  return (
    <div
      className="flex flex-col"
      style={{ height: "calc(100vh - 52px)", overflow: "hidden" }}
    >
      {/* ── Page header ──────────────────────────────────────────── */}
      <div
        className="flex items-center justify-between px-4 h-[52px] shrink-0"
        style={{ borderBottom: "1px solid var(--border)", background: "var(--background)" }}
      >
        <div className="flex flex-col justify-center gap-0.5">
          <h1 className="text-lg font-semibold leading-none" style={{ color: "var(--text)" }}>
            Dashboard
          </h1>
          <p className="text-xs leading-none" style={{ color: "var(--text-dim)" }}>
            Analysis pipeline · Claude Opus 4.6
          </p>
        </div>
        <Badge variant={badgeVariant}>
          {status}
        </Badge>
      </div>

      {/* ── Quick launch bar ─────────────────────────────────────── */}
      <div
        className="flex items-center gap-2 px-4 py-2.5 shrink-0"
        style={{ borderBottom: "1px solid var(--border)", background: "var(--background)" }}
      >
        <input
          type="text"
          value={repo}
          onChange={(e) => setRepo(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && !running && handleAnalyze()}
          placeholder="https://github.com/owner/repo"
          disabled={running}
          className="flex-1 h-9 rounded-md px-3 text-sm disabled:opacity-50 transition-colors outline-none min-h-[44px] sm:min-h-[36px]"
          style={{
            background: "var(--panel)",
            color: "var(--text)",
            border: "1px solid var(--border)",
          }}
          aria-label="GitHub repository URL"
          onFocus={(e) => (e.target.style.borderColor = "var(--accent)")}
          onBlur={(e) => (e.target.style.borderColor = "var(--border)")}
        />
        <button
          onClick={running ? stop : handleAnalyze}
          disabled={!running && !repo.trim()}
          className="h-9 px-4 rounded-md text-sm font-medium disabled:opacity-30 transition-colors shrink-0 min-h-[44px] sm:min-h-[36px]"
          style={{
            background: running ? "var(--error)" : "var(--accent)",
            color: "#ffffff",
          }}
        >
          {running ? "Stop" : "Run ▶"}
        </button>
      </div>

      {/* Brief — BriefBuilder (desktop + mobile, below launch bar) */}
      <div
        className="flex px-4 py-2.5 shrink-0"
        style={{ borderBottom: "1px solid var(--border)", background: "var(--background)" }}
      >
        <BriefBuilder
          repoUrl={repo}
          value={brief}
          onChange={setBrief}
          disabled={running}
        />
      </div>

      {error && (
        <div
          className="px-4 py-2 text-sm shrink-0"
          style={{
            background: "var(--error)/10",
            borderBottom: "1px solid var(--error)/30",
            color: "var(--error)",
          }}
        >
          {error}
        </div>
      )}

      {/* ── Mobile pane switcher ─────────────────────────────────── */}
      <div
        className="flex sm:hidden shrink-0"
        style={{ borderBottom: "1px solid var(--border)" }}
      >
        <button
          onClick={() => setMobilePane("terminal")}
          className="flex-1 text-xs font-medium py-2 transition-colors"
          style={{
            color:       mobilePane === "terminal" ? "var(--text)"      : "var(--text-muted)",
            background:  mobilePane === "terminal" ? "var(--panel)"     : "transparent",
            borderBottom: mobilePane === "terminal" ? "2px solid var(--accent)" : "2px solid transparent",
          }}
        >
          Terminal
        </button>
        <button
          onClick={() => setMobilePane("panel")}
          className="flex-1 text-xs font-medium py-2 transition-colors relative"
          style={{
            color:       mobilePane === "panel" ? "var(--text)"      : "var(--text-muted)",
            background:  mobilePane === "panel" ? "var(--panel)"     : "transparent",
            borderBottom: mobilePane === "panel" ? "2px solid var(--accent)" : "2px solid transparent",
          }}
        >
          Panel
          {hasResults && mobilePane !== "panel" && (
            <span
              className="inline-block w-1.5 h-1.5 rounded-full ml-1.5 align-middle"
              style={{ background: "var(--success)" }}
            />
          )}
        </button>
      </div>

      {/* ── Main layout ──────────────────────────────────────────── */}
      <div
        ref={containerRef}
        className="flex min-h-0"
        // eslint-disable-next-line react-hooks/refs -- isResizing.current is intentionally read during render for CSS cursor hint only (non-reactive, no state needed)
        style={{ flex: 1, overflow: "hidden", cursor: isResizing.current ? "col-resize" : undefined }}
        onPointerMove={onResizePointerMove}
        onPointerUp={onResizePointerUp}
        onPointerLeave={onResizePointerUp}
      >

        {/* LEFT — Terminal */}
        <div
          className={`flex flex-col min-w-0 ${mobilePane === "panel" ? "hidden sm:flex" : "flex"}`}
          style={{ flex: 1, overflow: "hidden" }}
        >
          <Terminal lines={lines} status={status} />
        </div>

        {/* DRAG HANDLE — desktop only */}
        <div
          className="hidden sm:flex w-[5px] shrink-0 cursor-col-resize items-center justify-center group select-none"
          style={{ background: "var(--border)" }}
          onPointerDown={onResizePointerDown}
          title="Drag to resize"
        >
          <div
            className="w-[3px] h-10 rounded-full opacity-0 group-hover:opacity-100 transition-opacity"
            style={{ background: "var(--accent)" }}
          />
        </div>

        {/* RIGHT — Tabbed panel */}
        <div
          className={`flex flex-col ${mobilePane === "terminal" ? "hidden sm:flex" : "flex"} w-full sm:w-auto sm:shrink-0`}
          style={{
            background: "var(--panel)",
            overflow: "hidden",
          }}
        >
          <div
            className="flex flex-col h-full"
            style={{ width: `${sidebarWidth}px` }}
          >
            {/* Tab bar */}
            <div
              className="flex shrink-0"
              style={{ borderBottom: "1px solid var(--border)" }}
            >
              {(["phases", "results", "actions"] as RightTab[]).map((tab) => {
                const active = rightTab === tab;
                const showDot = (tab === "results" && hasResults && rightTab !== "results")
                             || (tab === "actions" && status === "done" && rightTab !== "actions");
                return (
                  <button
                    key={tab}
                    onClick={() => setRightTab(tab)}
                    className="flex-1 text-xs font-medium capitalize py-2 transition-colors relative min-h-[44px] sm:min-h-0"
                    style={{
                      color:        active ? "var(--text)"     : "var(--text-muted)",
                      background:   active ? "var(--background)" : "transparent",
                      borderBottom: active ? "2px solid var(--accent)" : "2px solid transparent",
                    }}
                  >
                    {tab}
                    {showDot && (
                      <span
                        className="inline-block w-1.5 h-1.5 rounded-full ml-1.5 align-middle"
                        style={{ background: "var(--success)" }}
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
                    <p className="text-xs" style={{ color: "var(--text-muted)" }}>
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
      </div>

      {/* ── Status bar ───────────────────────────────────────────── */}
      <div
        className="flex items-center justify-between px-4 py-1.5 shrink-0 text-[10px] gap-2"
        style={{
          borderTop: "1px solid var(--border)",
          background: "var(--background)",
          color: "var(--text-dim)",
        }}
      >
        <div className="flex items-center gap-3 min-w-0 font-mono">
          <span className="truncate">
            Branch: <span style={{ color: "var(--text-muted)" }}>{branch ?? "—"}</span>
          </span>
          {prUrl && (
            <a
              href={prUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="shrink-0"
              style={{ color: "var(--accent)" }}
            >
              PR ↗
            </a>
          )}
          {linearUrl && linearId && (
            <a
              href={linearUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="shrink-0 flex items-center gap-1"
              style={{ color: "var(--info)" }}
            >
              <span>◈</span>
              <span>{linearId} ↗</span>
            </a>
          )}
        </div>
        <div className="flex items-center gap-3 shrink-0 font-mono">
          <span className="hidden sm:inline">
            Lines: <span style={{ color: "var(--text-muted)" }}>{lines.length}</span>
          </span>
          <span
            style={{
              color: status === "running" ? "var(--accent)"  :
                     status === "done"    ? "var(--success)" :
                     status === "error"   ? "var(--error)"   : "var(--text-dim)",
            }}
          >
            {status}
          </span>
          {status === "done" && rightTab !== "results" && (
            <button
              onClick={() => { setRightTab("results"); setMobilePane("panel"); resultsRef.current?.scrollTo({ top: 0 }); }}
              className="text-[10px] font-medium"
              style={{ color: "var(--success)" }}
            >
              Results →
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
