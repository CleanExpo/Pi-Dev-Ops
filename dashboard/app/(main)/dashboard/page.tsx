// app/(main)/dashboard/page.tsx — analysis dashboard
"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import Terminal from "@/components/Terminal";
import PhaseTracker from "@/components/PhaseTracker";
import ResultCards from "@/components/ResultCards";
import ActionsPanel from "@/components/ActionsPanel";
import PageHero from "@/components/PageHero";
import { Badge } from "@/components/ui/badge";
import { useSSE } from "@/hooks/useSSE";

function sanitize(s: string): string {
  return s.replace(/[<>"&]/g, "");
}

type RightTab = "phases" | "results" | "actions";

const SIDEBAR_MIN = 220;
const SIDEBAR_MAX = 640;
const SIDEBAR_DEFAULT = 320;

const BRIEF_TEMPLATE =
  "Scope: Full audit — ZTE score, quality gates, leverage points, executive summary\nFocus areas: All components\nContext: ";

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
    // GitHub token is read server-side from Supabase settings — no need to pass it here
    start(sanitize(repo.trim()), brief.trim() || undefined);
  }

  const running = status === "running" || submitting;
  const hasResults = Object.keys(result).length > 2;

  const statusColor =
    status === "running" ? "#E8751A" :
    status === "done"    ? "#4ADE80" :
    status === "error"   ? "#F87171" : "#888480";

  return (
    <div
      className="flex flex-col"
      style={{ height: "calc(100vh - 48px)", overflow: "hidden" }}
    >
      {/* ── Cinematic page header — carries landing aesthetic into app ─ */}
      <PageHero
        title="DASHBOARD"
        subtitle="Analysis pipeline · Claude Opus 4.6"
        compact
        right={
          <Badge
            variant={
              status === "running" ? "default" :
              status === "done"    ? "success" :
              status === "error"   ? "destructive" : "outline"
            }
          >
            {status.toUpperCase()}
          </Badge>
        }
      />

      {/* ── Input bar ─────────────────────────────────────────────── */}
      <div
        className="flex items-center gap-2 sm:gap-3 px-3 py-2 shrink-0"
        style={{ borderBottom: "1px solid var(--c-border)", background: "var(--c-bg)" }}
      >
        <span className="font-mono text-xs shrink-0" style={{ color: "var(--c-muted)" }}>REPO</span>
        <input
          type="text"
          value={repo}
          onChange={(e) => setRepo(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && !running && handleAnalyze()}
          placeholder="https://github.com/owner/repo"
          disabled={running}
          className="flex-1 font-mono text-xs outline-none disabled:opacity-50 px-2 min-h-[44px] sm:min-h-0 sm:py-1"
          style={{ background: "var(--c-panel)", color: "var(--c-text)", border: "1px solid var(--c-border)" }}
          aria-label="GitHub repository URL"
        />
        <button
          onClick={running ? stop : handleAnalyze}
          disabled={!running && !repo.trim()}
          className="font-mono text-xs px-4 sm:px-5 disabled:opacity-30 transition-opacity shrink-0 min-h-[44px]"
          style={{
            background: running ? "#F87171" : "var(--c-orange)",
            color: "#FFFFFF",
            fontWeight: 700,
            letterSpacing: "0.12em",
          }}
        >
          {running ? "STOP" : "ANALYZE"}
        </button>
      </div>

      {/* ── Brief bar ─────────────────────────────────────────────── */}
      <div
        className="flex flex-col gap-1 px-3 py-2 shrink-0"
        style={{ borderBottom: "1px solid var(--c-border)", background: "var(--c-bg)" }}
      >
        <div className="flex items-center justify-between">
          <span className="font-mono text-xs" style={{ color: "var(--c-muted)" }}>BRIEF</span>
          <button
            type="button"
            onClick={() => setBrief(BRIEF_TEMPLATE)}
            disabled={running}
            className="font-mono text-xs px-2 py-0.5 disabled:opacity-30 transition-opacity"
            style={{
              background: "var(--c-panel)",
              color: "var(--c-chrome)",
              border: "1px solid var(--c-border)",
            }}
          >
            Use template
          </button>
        </div>
        <textarea
          value={brief}
          onChange={(e) => setBrief(e.target.value)}
          placeholder={`Describe what to analyse. Click "Use template" for a structured format.`}
          disabled={running}
          rows={3}
          className="font-mono text-xs outline-none disabled:opacity-50 px-2 py-1 resize-none"
          style={{ background: "var(--c-panel)", color: "var(--c-text)", border: "1px solid var(--c-border)" }}
          aria-label="Analysis brief"
        />
      </div>

      {error && (
        <div
          className="px-4 py-2 font-mono text-xs shrink-0"
          style={{ background: "#1a0808", borderBottom: "1px solid #F87171", color: "#F87171" }}
        >
          ✗ {error}
        </div>
      )}

      {/* ── Mobile pane switcher ─────────────────────────────────── */}
      <div
        className="flex sm:hidden shrink-0"
        style={{ borderBottom: "1px solid var(--c-border)" }}
      >
        <button
          onClick={() => setMobilePane("terminal")}
          className="flex-1 font-mono text-xs py-2 transition-colors"
          style={{
            color: mobilePane === "terminal" ? "var(--c-text)" : "var(--c-chrome)",
            background: mobilePane === "terminal" ? "var(--c-panel)" : "transparent",
            borderBottom: mobilePane === "terminal" ? "2px solid var(--c-orange)" : "2px solid transparent",
          }}
        >
          TERMINAL
        </button>
        <button
          onClick={() => setMobilePane("panel")}
          className="flex-1 font-mono text-xs py-2 transition-colors relative"
          style={{
            color: mobilePane === "panel" ? "var(--c-text)" : "var(--c-chrome)",
            background: mobilePane === "panel" ? "var(--c-panel)" : "transparent",
            borderBottom: mobilePane === "panel" ? "2px solid var(--c-orange)" : "2px solid transparent",
          }}
        >
          PANEL
          {hasResults && mobilePane !== "panel" && (
            <span
              className="inline-block w-1.5 h-1.5 rounded-full ml-1.5 align-middle"
              style={{ background: "#4ADE80" }}
            />
          )}
        </button>
      </div>

      {/* ── Main layout — stacks on mobile, side-by-side on sm+ ──── */}
      <div
        ref={containerRef}
        className="flex min-h-0"
        style={{ flex: 1, overflow: "hidden", cursor: isResizing.current ? "col-resize" : undefined }}
        onPointerMove={onResizePointerMove}
        onPointerUp={onResizePointerUp}
        onPointerLeave={onResizePointerUp}
      >

        {/* LEFT — Terminal (hidden on mobile when panel is active) */}
        <div
          className={`flex flex-col min-w-0 ${mobilePane === "panel" ? "hidden sm:flex" : "flex"}`}
          style={{ flex: 1, overflow: "hidden" }}
        >
          <Terminal lines={lines} status={status} />
        </div>

        {/* DRAG HANDLE — desktop only */}
        <div
          className="hidden sm:flex w-[5px] shrink-0 cursor-col-resize items-center justify-center group select-none"
          style={{ background: "var(--c-border)" }}
          onPointerDown={onResizePointerDown}
          title="Drag to resize"
        >
          <div
            className="w-[3px] h-10 rounded-full opacity-0 group-hover:opacity-100 transition-opacity"
            style={{ background: "var(--c-orange)" }}
          />
        </div>

        {/* RIGHT — Tabbed panel (hidden on mobile when terminal is active) */}
        <div
          className={`flex flex-col ${mobilePane === "terminal" ? "hidden sm:flex" : "flex"} w-full sm:w-auto sm:shrink-0`}
          style={{
            width: undefined,
            background: "var(--c-panel)",
            overflow: "hidden",
          }}
        >
          {/* Dynamic-width wrapper for desktop only */}
          <div
            className="flex flex-col h-full"
            style={{ width: `${sidebarWidth}px` }}
          >
            {/* Tab bar */}
            <div className="flex shrink-0" style={{ borderBottom: "1px solid var(--c-border)" }}>
              {(["phases", "results", "actions"] as RightTab[]).map((tab) => {
                const active = rightTab === tab;
                const showDot = (tab === "results" && hasResults && rightTab !== "results")
                             || (tab === "actions" && status === "done" && rightTab !== "actions");
                return (
                  <button
                    key={tab}
                    onClick={() => setRightTab(tab)}
                    className="flex-1 font-mono text-xs uppercase tracking-widest py-2 sm:py-2 transition-colors relative min-h-[44px] sm:min-h-0"
                    style={{
                      color: active ? "var(--c-text)" : "var(--c-chrome)",
                      background: active ? "var(--c-bg)" : "transparent",
                      borderBottom: active ? "1px solid var(--c-orange)" : "1px solid transparent",
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
                    <p className="font-mono text-xs" style={{ color: "var(--c-chrome)" }}>
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

      {/* ── Status bar ────────────────────────────────────────────── */}
      <div
        className="flex items-center justify-between px-4 py-1.5 shrink-0 font-mono text-[10px] gap-2"
        style={{ borderTop: "1px solid var(--c-border)", background: "var(--c-bg)", color: "var(--c-chrome)" }}
      >
        <div className="flex items-center gap-3 min-w-0">
          <span className="truncate">
            BRANCH: <span style={{ color: "var(--c-muted)" }}>{branch ?? "—"}</span>
          </span>
          {prUrl && (
            <a href={prUrl} target="_blank" rel="noopener noreferrer" className="shrink-0" style={{ color: "var(--c-orange)" }}>
              PR ↗
            </a>
          )}
          {linearUrl && linearId && (
            <a href={linearUrl} target="_blank" rel="noopener noreferrer" className="shrink-0 flex items-center gap-1" style={{ color: "#6B7FE3" }}>
              <span>◈</span>
              <span>{linearId} ↗</span>
            </a>
          )}
        </div>
        <div className="flex items-center gap-3 shrink-0">
          <span className="hidden sm:inline">LINES: <span style={{ color: "var(--c-muted)" }}>{lines.length}</span></span>
          <span>
            <span style={{ color: statusColor }}>{status.toUpperCase()}</span>
          </span>
          {status === "done" && rightTab !== "results" && (
            <button
              onClick={() => { setRightTab("results"); setMobilePane("panel"); resultsRef.current?.scrollTo({ top: 0 }); }}
              className="font-mono text-[10px] tracking-wider"
              style={{ color: "#4ADE80" }}
            >
              RESULTS →
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
