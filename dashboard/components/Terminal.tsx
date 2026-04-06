// components/Terminal.tsx — Bloomberg-style live terminal output panel

"use client";

import { useEffect, useRef } from "react";
import type { TermLine, TermLineType } from "@/lib/types";

const COLOR: Record<TermLineType, string> = {
  phase:   "#E8751A",  // orange — phase headers
  success: "#4CAF82",  // green
  error:   "#EF4444",  // red
  tool:    "#FFD166",  // yellow — tool calls
  agent:   "#F0EDE8",  // cream — Claude output
  system:  "#666666",  // dim — system info
  output:  "#AAAAAA",  // grey — stdout
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

  // Auto-scroll only if already near the bottom
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
    if (atBottom) bottomRef.current?.scrollIntoView();
  }, [lines]);

  return (
    <div className="flex flex-col h-full" style={{ background: "#0C0C0C" }}>
      {/* Title bar */}
      <div
        className="flex items-center justify-between px-3 py-1.5 shrink-0"
        style={{ borderBottom: "1px solid #1A1A1A" }}
      >
        <span className="font-mono text-[10px] text-[#666] uppercase tracking-widest">
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
            style={{
              color:
                status === "running" ? "#E8751A" :
                status === "done"    ? "#4CAF82" :
                status === "error"   ? "#EF4444" : "#444",
            }}
          >
            {status}
          </span>
          <span className="font-mono text-[9px] text-[#444]">
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
          <p className="font-mono text-[11px] text-[#333] pt-4">
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
