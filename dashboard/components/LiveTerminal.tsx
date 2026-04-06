"use client";

import { useEffect, useRef, useState } from "react";
import { useWebSocket } from "@/hooks/useWebSocket";
import { api } from "@/lib/api";
import type { Session, OutputLine, LineType } from "@/lib/types";

// Color map for each line type — matches the Pi CEO orange/dark theme
const LINE_COLORS: Record<LineType | "done", string> = {
  phase: "#E8751A",    // orange — section headers
  system: "#888888",   // muted — system info
  success: "#4CAF82",  // green — success
  error: "#EF4444",    // red — errors
  tool: "#6B8CFF",     // blue — tool calls
  agent: "#C0AAFF",    // lavender — agent output
  output: "#F0EDE8",   // cream — stdout
  metric: "#FFD166",   // yellow — cost/metrics
  stderr: "#FF6B6B",   // salmon — stderr
  done: "#4CAF82",     // green — done
};

function TerminalLine({ line }: { line: OutputLine }) {
  const color = LINE_COLORS[line.type] ?? "#F0EDE8";
  const prefix =
    line.type === "phase"
      ? "▶ "
      : line.type === "tool"
        ? "$ "
        : line.type === "success"
          ? "✓ "
          : line.type === "error"
            ? "✗ "
            : line.type === "metric"
              ? "⊕ "
              : "  ";

  return (
    <div
      className="font-mono text-xs leading-5 whitespace-pre-wrap break-all px-1"
      style={{ color }}
    >
      {prefix}
      {line.text.trim()}
    </div>
  );
}

interface LiveTerminalProps {
  activeSessionId?: string | null;
}

export default function LiveTerminal({ activeSessionId }: LiveTerminalProps) {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(
    activeSessionId ?? null
  );
  const { lines, status } = useWebSocket(selectedId);
  const bottomRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [autoScroll, setAutoScroll] = useState(true);

  // Keep session list fresh
  useEffect(() => {
    function refresh() {
      api
        .sessions()
        .then(setSessions)
        .catch(() => {});
    }
    refresh();
    const t = setInterval(refresh, 3000);
    return () => clearInterval(t);
  }, []);

  // When a new session is created externally, switch to it
  useEffect(() => {
    if (activeSessionId) setSelectedId(activeSessionId);
  }, [activeSessionId]);

  // Auto-scroll
  useEffect(() => {
    if (autoScroll && bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [lines, autoScroll]);

  // Detect manual scroll up → disable auto-scroll
  function handleScroll() {
    const el = containerRef.current;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
    setAutoScroll(atBottom);
  }

  const statusColor =
    status === "connected"
      ? "#E8751A"
      : status === "done"
        ? "#4CAF82"
        : status === "error"
          ? "#EF4444"
          : "#666666";

  return (
    <div
      id="terminal"
      className="bg-pi-dark-2 border border-pi-border rounded-lg flex flex-col"
      style={{ height: "480px" }}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-pi-border shrink-0">
        <div className="flex items-center gap-3">
          <div className="flex gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-red-500/60" />
            <span className="w-2.5 h-2.5 rounded-full bg-yellow-500/60" />
            <span className="w-2.5 h-2.5 rounded-full bg-green-500/60" />
          </div>
          <span className="font-mono text-xs text-pi-muted">
            pi-ceo — live output
          </span>
        </div>

        <div className="flex items-center gap-3">
          {/* Status indicator */}
          <div className="flex items-center gap-1.5">
            <span
              className={`w-1.5 h-1.5 rounded-full ${status === "connected" || status === "done" ? "status-dot-active" : ""}`}
              style={{ backgroundColor: statusColor }}
            />
            <span className="font-mono text-[9px] uppercase tracking-wider" style={{ color: statusColor }}>
              {status}
            </span>
          </div>

          {/* Session selector */}
          <select
            value={selectedId ?? ""}
            onChange={(e) => setSelectedId(e.target.value || null)}
            className="bg-pi-dark-3 border border-pi-border rounded px-2 py-1 font-mono text-[10px] text-pi-muted focus:border-pi-orange"
          >
            <option value="">Select session…</option>
            {sessions.map((s) => (
              <option key={s.id} value={s.id}>
                {s.id} — {s.status} ({s.lines}L)
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Output area */}
      <div
        ref={containerRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto p-3 space-y-0.5 bg-[#080808]"
      >
        {!selectedId && (
          <div className="flex items-center justify-center h-full">
            <p className="font-mono text-xs text-pi-muted">
              Select a session or launch a build to see live output.
            </p>
          </div>
        )}

        {selectedId && lines.length === 0 && status === "connecting" && (
          <div className="flex items-center gap-2 px-1 py-2">
            <span className="inline-block w-3 h-3 border border-pi-orange/40 border-t-pi-orange rounded-full animate-spin" />
            <span className="font-mono text-xs text-pi-muted">
              Connecting to session {selectedId}…
            </span>
          </div>
        )}

        {lines.map((line, i) => (
          <TerminalLine key={i} line={line} />
        ))}
        <div ref={bottomRef} />
      </div>

      {/* Footer bar */}
      <div className="px-4 py-2 border-t border-pi-border flex items-center justify-between shrink-0">
        <span className="font-mono text-[9px] text-pi-muted">
          {lines.length} lines
        </span>
        <div className="flex items-center gap-3">
          {!autoScroll && (
            <button
              onClick={() => {
                setAutoScroll(true);
                bottomRef.current?.scrollIntoView({ behavior: "smooth" });
              }}
              className="font-mono text-[9px] text-pi-orange/70 hover:text-pi-orange transition-colors"
            >
              ↓ Scroll to bottom
            </button>
          )}
          <button
            onClick={() => {
              if (selectedId) {
                api.kill(selectedId).catch(() => {});
              }
            }}
            disabled={!selectedId || status !== "connected"}
            className="font-mono text-[9px] text-red-400/60 hover:text-red-400 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
          >
            ✗ Kill
          </button>
        </div>
      </div>
    </div>
  );
}
