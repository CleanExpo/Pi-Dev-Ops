// components/Terminal.tsx — Bloomberg-style live terminal output panel
"use client";

import { useEffect, useRef } from "react";
import type { TermLine, TermLineType } from "@/lib/types";

const COLOR: Record<TermLineType, string> = {
  phase:   "#E8751A",  // orange — phase headers
  success: "#4ADE80",  // bright green
  error:   "#F87171",  // bright red
  tool:    "#FFD166",  // yellow — tool calls
  agent:   "#F0EDE8",  // cream — Claude output
  system:  "#A8A5A0",  // warm gray — system info
  output:  "#E8E4DE",  // near-cream — stdout
};

const PREFIX: Record<TermLineType, string> = {
  phase:   "▶ ",
  success: "✓ ",
  error:   "✗ ",
  tool:    "$ ",
  agent:   "  ",
  system:  "  ",
  output:  "  ",
};

interface Props {
  lines: TermLine[];
  status: "idle" | "running" | "done" | "error";
}

export default function Terminal({ lines, status }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
    if (atBottom) bottomRef.current?.scrollIntoView();
  }, [lines]);

  const statusColor =
    status === "running" ? "#E8751A" :
    status === "done"    ? "#4ADE80" :
    status === "error"   ? "#F87171" : "#888480";

  return (
    <div className="flex flex-col h-full" style={{ background: "#0C0C0C" }}>
      {/* Title bar */}
      <div
        className="flex items-center justify-between px-3 py-1.5 shrink-0"
        style={{ borderBottom: "1px solid #2A2727" }}
      >
        <span className="font-mono text-[10px] uppercase tracking-widest" style={{ color: "#C8C5C0" }}>
          terminal output
        </span>
        <div className="flex items-center gap-2">
          {status === "running" && (
            <span
              className="inline-block w-1.5 h-1.5 rounded-full"
              style={{ backgroundColor: "#E8751A", animation: "pulse 1.5s infinite" }}
            />
          )}
          <span
            className="font-mono text-[9px] uppercase tracking-wider"
            style={{ color: statusColor }}
          >
            {status}
          </span>
          <span className="font-mono text-[9px]" style={{ color: "#888480" }}>
            {lines.length}L
          </span>
        </div>
      </div>

      {/* Output */}
      <div
        ref={containerRef}
        className="flex-1 overflow-y-auto px-3 py-2 space-y-px"
      >
        {lines.length === 0 && status === "idle" && (
          <p className="font-mono text-[11px] pt-4" style={{ color: "#888480" }}>
            Paste a GitHub repo URL above and click ANALYZE to begin.
          </p>
        )}
        {lines.map((line, i) => (
          <div
            key={i}
            className="font-mono text-[12px] leading-[1.6] whitespace-pre-wrap break-all"
            style={{ color: COLOR[line.type] }}
          >
            {PREFIX[line.type]}{line.text.trim()}
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
