// components/control/BuildForm.tsx — Panel 4 top: compact brief form + terminal modal (RA-1092)
"use client";

import { useEffect, useRef, useState } from "react";
import { useSSE } from "@/hooks/useSSE";
import Terminal from "@/components/Terminal";

function sanitize(s: string): string {
  return s.replace(/[<>"&]/g, "");
}

export default function BuildForm() {
  const [repo, setRepo] = useState("");
  const [brief, setBrief] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [terminalOpen, setTerminalOpen] = useState(false);
  const { lines, status, error, branch, prUrl, start, stop } = useSSE();
  const escRef = useRef<HTMLDivElement>(null);

  const running = status === "running" || submitting;

  useEffect(() => {
    if (status !== "idle") setSubmitting(false);
  }, [status]);

  // Auto-open terminal when a run starts
  useEffect(() => {
    if (status === "running") setTerminalOpen(true);
  }, [status]);

  useEffect(() => {
    if (!terminalOpen) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setTerminalOpen(false);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [terminalOpen]);

  function submit() {
    if (!repo.trim() || submitting) return;
    setSubmitting(true);
    start(sanitize(repo.trim()), brief.trim() || undefined);
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <span className="text-[10px] uppercase tracking-widest" style={{ color: "var(--text-dim)" }}>
          Run a build
        </span>
        <button
          onClick={() => setTerminalOpen(true)}
          className="text-[10px] font-mono hover:opacity-70"
          style={{ color: running ? "var(--accent)" : "var(--text-muted)" }}
          disabled={lines.length === 0 && !running}
        >
          {running ? "live ▸" : "show terminal"}
        </button>
      </div>

      <input
        type="text"
        value={repo}
        onChange={(e) => setRepo(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !running) submit();
        }}
        placeholder="https://github.com/owner/repo"
        disabled={running}
        className="h-9 rounded-md px-3 text-xs outline-none disabled:opacity-50"
        style={{
          background: "var(--panel-hover)",
          color: "var(--text)",
          border: "1px solid var(--border)",
        }}
        aria-label="Repository URL"
      />

      <textarea
        value={brief}
        onChange={(e) => setBrief(e.target.value)}
        placeholder="Brief (optional) — scope, focus areas, context"
        disabled={running}
        rows={3}
        className="rounded-md px-3 py-2 text-xs outline-none resize-none disabled:opacity-50"
        style={{
          background: "var(--panel-hover)",
          color: "var(--text)",
          border: "1px solid var(--border)",
          fontFamily: "inherit",
          lineHeight: "1.4",
        }}
        aria-label="Build brief"
      />

      <div className="flex items-center gap-2">
        <button
          onClick={running ? stop : submit}
          disabled={!running && !repo.trim()}
          className="h-8 px-3 rounded-md text-xs font-medium disabled:opacity-30 transition-colors"
          style={{
            background: running ? "var(--error)" : "var(--accent)",
            color: "#fff",
          }}
        >
          {running ? "Stop" : "Run ▶"}
        </button>

        {status !== "idle" && (
          <span
            className="text-[10px] font-mono"
            style={{
              color:
                status === "running"
                  ? "var(--accent)"
                  : status === "done"
                    ? "var(--success)"
                    : status === "error"
                      ? "var(--error)"
                      : "var(--text-dim)",
            }}
          >
            {status}
          </span>
        )}

        {branch && (
          <span className="text-[10px] font-mono truncate" style={{ color: "var(--text-muted)" }}>
            {branch}
          </span>
        )}

        {prUrl && (
          <a
            href={prUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="text-[10px] font-mono"
            style={{ color: "var(--accent)" }}
          >
            PR ↗
          </a>
        )}
      </div>

      {error && (
        <p className="text-[11px]" style={{ color: "var(--error)" }}>
          {error}
        </p>
      )}

      {/* Live terminal modal overlay */}
      {terminalOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4"
          style={{ background: "rgba(0,0,0,0.7)" }}
          onClick={() => setTerminalOpen(false)}
          role="dialog"
          aria-modal="true"
          aria-label="Live build terminal"
        >
          <div
            ref={escRef}
            className="w-full max-w-4xl h-[70vh] flex flex-col rounded-lg overflow-hidden"
            style={{ background: "var(--panel)", border: "1px solid var(--border)" }}
            onClick={(e) => e.stopPropagation()}
          >
            <div
              className="flex items-center justify-between px-4 py-2 shrink-0"
              style={{ borderBottom: "1px solid var(--border)" }}
            >
              <span className="text-xs font-semibold uppercase tracking-widest" style={{ color: "var(--text-muted)" }}>
                Live Build Terminal
              </span>
              <button
                onClick={() => setTerminalOpen(false)}
                className="text-xs"
                style={{ color: "var(--text-muted)" }}
                aria-label="Close terminal"
              >
                ✕
              </button>
            </div>
            <div className="flex-1 min-h-0">
              <Terminal lines={lines} status={status} />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
