// components/control/BuildForm.tsx — Panel 4 top: terminal-style brief form + live modal (RA-1092)
"use client";

import { useEffect, useRef, useState } from "react";
import { useSSE } from "@/hooks/useSSE";
import Terminal from "@/components/Terminal";
import { useActiveProject } from "./ProjectSelector";

function sanitize(s: string): string {
  return s.replace(/[<>"&]/g, "");
}

function repoToUrl(repo: string): string {
  if (!repo) return "";
  if (repo.startsWith("http")) return repo;
  return `https://github.com/${repo}`;
}

export default function BuildForm() {
  const activeProject = useActiveProject();
  const [repo, setRepo] = useState("");
  const [brief, setBrief] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [terminalOpen, setTerminalOpen] = useState(false);
  const [repoFocused, setRepoFocused] = useState(false);
  const [briefFocused, setBriefFocused] = useState(false);
  const { lines, status, error, branch, prUrl, start, stop } = useSSE();
  const escRef = useRef<HTMLDivElement>(null);

  // RA-1103 — pre-fill repo from active project when user picks one in TopBar.
  // Only overwrite empty / unedited input — don't clobber what the user is typing.
  useEffect(() => {
    if (!activeProject) return;
    const url = repoToUrl(activeProject.repo);
    setRepo((current) => (current ? current : url));
  }, [activeProject]);

  const running = status === "running" || submitting;

  useEffect(() => {
    if (status !== "idle") setSubmitting(false);
  }, [status]);

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

  const inputBase: React.CSSProperties = {
    background: "var(--panel-hover)",
    color: "var(--text)",
    border: "1px solid var(--border)",
    fontFamily: "var(--font-mono, monospace)",
    fontSize: "11px",
    outline: "none",
    transition: "border-color 0.15s ease",
  };

  const inputFocused: React.CSSProperties = {
    borderColor: "var(--accent)",
    boxShadow: "0 0 0 2px var(--accent-subtle)",
  };

  return (
    <div className="flex flex-col gap-2">
      <style>{`
        @keyframes pi-caret-blink {
          0%, 100% { opacity: 1; }
          50%       { opacity: 0; }
        }
      `}</style>

      <div className="flex items-center justify-between">
        <span className="text-[10px] uppercase tracking-widest font-mono" style={{ color: "var(--text-dim)" }}>
          {/* Amber prompt caret */}
          <span style={{ color: "var(--accent)" }} aria-hidden="true">
            {running ? "▸ " : "$ "}
          </span>
          {running ? "build running…" : "run a build"}
        </span>
        <button
          onClick={() => setTerminalOpen(true)}
          className="text-[10px] font-mono hover:opacity-70"
          style={{ color: running ? "var(--accent)" : "var(--text-muted)" }}
          disabled={lines.length === 0 && !running}
        >
          {running ? "live ▸" : "terminal"}
        </button>
      </div>

      {/* Repo input with prompt prefix */}
      <div className="flex items-center rounded-md overflow-hidden" style={{ ...inputBase, ...(repoFocused ? inputFocused : {}) }}>
        <span
          className="px-2 text-[11px] font-mono shrink-0 select-none"
          style={{
            color: "var(--accent)",
            borderRight: "1px solid var(--border)",
            background: "var(--panel)",
            padding: "0 8px",
            lineHeight: "36px",
          }}
          aria-hidden="true"
        >
          repo
        </span>
        <input
          type="text"
          value={repo}
          onChange={(e) => setRepo(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && !running) submit(); }}
          onFocus={() => setRepoFocused(true)}
          onBlur={() => setRepoFocused(false)}
          placeholder="https://github.com/owner/repo"
          disabled={running}
          className="flex-1 h-9 px-2.5 bg-transparent outline-none disabled:opacity-50 text-[11px]"
          style={{ color: "var(--text)", fontFamily: "var(--font-mono, monospace)" }}
          aria-label="Repository URL"
        />
      </div>

      {/* Brief textarea with terminal prompt prefix */}
      <div
        className="flex rounded-md overflow-hidden"
        style={{ ...inputBase, ...(briefFocused ? inputFocused : {}), alignItems: "flex-start" }}
      >
        <span
          className="text-[11px] font-mono shrink-0 select-none pt-2"
          style={{
            color: "var(--accent)",
            borderRight: "1px solid var(--border)",
            background: "var(--panel)",
            padding: "8px 8px 0",
            lineHeight: 1.4,
          }}
          aria-hidden="true"
        >
          msg
        </span>
        <textarea
          value={brief}
          onChange={(e) => setBrief(e.target.value)}
          onFocus={() => setBriefFocused(true)}
          onBlur={() => setBriefFocused(false)}
          placeholder="Brief (optional) — scope, focus areas, context"
          disabled={running}
          rows={3}
          className="flex-1 px-2.5 py-2 bg-transparent outline-none resize-none disabled:opacity-50 text-[11px]"
          style={{
            color: "var(--text)",
            fontFamily: "var(--font-mono, monospace)",
            lineHeight: "1.4",
          }}
          aria-label="Build brief"
        />
      </div>

      <div className="flex items-center gap-2">
        <button
          onClick={running ? stop : submit}
          disabled={!running && !repo.trim()}
          className="h-8 px-3 rounded-md text-xs font-mono font-medium disabled:opacity-30 transition-colors"
          style={{
            background: running ? "var(--error)" : "var(--accent)",
            color: "#fff",
          }}
        >
          {running ? "■ stop" : "▶ run"}
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
            {/* Blinking cursor when running */}
            {status === "running" && (
              <span
                aria-hidden="true"
                style={{ animation: "pi-caret-blink 1s step-end infinite", marginRight: 4 }}
              >
                ▮
              </span>
            )}
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
        <p className="text-[11px] font-mono" style={{ color: "var(--error)" }}>
          <span aria-hidden="true">⚠ </span>{error}
        </p>
      )}

      {/* Live terminal modal overlay */}
      {terminalOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4"
          style={{ background: "rgba(0,0,0,0.75)" }}
          onClick={() => setTerminalOpen(false)}
          role="dialog"
          aria-modal="true"
          aria-label="Live build terminal"
        >
          <div
            ref={escRef}
            className="w-full max-w-4xl h-[70vh] flex flex-col rounded-lg overflow-hidden"
            style={{
              background: "var(--panel)",
              border: "1px solid var(--border)",
              boxShadow: "0 24px 64px rgba(0,0,0,0.5)",
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div
              className="flex items-center justify-between px-4 py-2 shrink-0"
              style={{ borderBottom: "1px solid var(--border)", background: "var(--panel)" }}
            >
              {/* macOS-style traffic lights */}
              <div className="flex items-center gap-1.5">
                <span className="w-3 h-3 rounded-full" style={{ background: "#ef4444" }} aria-hidden="true" />
                <span className="w-3 h-3 rounded-full" style={{ background: "#f59e0b" }} aria-hidden="true" />
                <span className="w-3 h-3 rounded-full" style={{ background: "#22c55e" }} aria-hidden="true" />
                <span className="text-[10px] font-mono ml-3" style={{ color: "var(--text-dim)" }}>
                  pi-ceo build — live output
                </span>
              </div>
              <button
                onClick={() => setTerminalOpen(false)}
                className="text-xs"
                style={{ color: "var(--text-muted)" }}
                aria-label="Close terminal (Escape)"
              >
                esc ✕
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
