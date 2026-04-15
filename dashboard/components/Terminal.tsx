// components/Terminal.tsx — xterm.js terminal (Bloomberg canvas colors preserved)
"use client";

import { useEffect, useRef } from "react";
import "xterm/css/xterm.css";
import type { TermLine, TermLineType } from "@/lib/types";

// ANSI colour codes — Bloomberg palette kept for terminal canvas readability
const ANSI: Record<TermLineType, string> = {
  phase:   "\x1b[38;2;232;117;26m",   // #E8751A orange
  success: "\x1b[38;2;74;222;128m",   // #4ADE80 green
  error:   "\x1b[38;2;248;113;113m",  // #F87171 red
  tool:    "\x1b[38;2;255;209;102m",  // #FFD166 yellow
  agent:   "\x1b[38;2;240;237;232m",  // #F0EDE8 cream
  system:  "\x1b[38;2;168;165;160m",  // #A8A5A0 warm gray
  output:  "\x1b[38;2;232;228;222m",  // #E8E4DE near-cream
};
const RESET = "\x1b[0m";

const PREFIX: Record<TermLineType, string> = {
  phase:   "▶ ",
  success: "✓ ",
  error:   "✗ ",
  tool:    "$ ",
  agent:   "  ",
  system:  "  ",
  output:  "  ",
};

// xterm theme — Bloomberg colors kept unchanged for terminal canvas
const XTERM_THEME = {
  background:          "#0C0C0C",
  foreground:          "#F0EDE8",
  cursor:              "#E8751A",
  cursorAccent:        "#0C0C0C",
  selectionBackground: "#E8751A44",
  black:               "#0C0C0C",
  red:                 "#F87171",
  green:               "#4ADE80",
  yellow:              "#FFD166",
  blue:                "#6B8CFF",
  magenta:             "#C678DD",
  cyan:                "#56B6C2",
  white:               "#F0EDE8",
  brightBlack:         "#888480",
  brightRed:           "#F87171",
  brightGreen:         "#4ADE80",
  brightYellow:        "#FFD166",
  brightBlue:          "#6B8CFF",
  brightMagenta:       "#C678DD",
  brightCyan:          "#56B6C2",
  brightWhite:         "#FFFFFF",
};

interface Props {
  lines:  TermLine[];
  status: "idle" | "running" | "done" | "error";
}

export default function Terminal({ lines, status }: Props) {
  const mountRef      = useRef<HTMLDivElement>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const termRef       = useRef<any>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const fitRef        = useRef<any>(null);
  const renderedRef   = useRef(0);
  const resizeObsRef  = useRef<ResizeObserver | null>(null);

  // Mount xterm.js once (browser-only dynamic import)
  useEffect(() => {
    if (!mountRef.current || termRef.current) return;

    let disposed = false;
    (async () => {
      const [{ Terminal: XTerm }, { FitAddon }, { WebLinksAddon }] = await Promise.all([
        import("xterm"),
        import("xterm-addon-fit"),
        import("xterm-addon-web-links"),
      ]);

      if (disposed || !mountRef.current) return;

      const term = new XTerm({
        theme:        XTERM_THEME,
        fontFamily:   "'IBM Plex Mono', 'Fira Mono', monospace",
        fontSize:     12,
        lineHeight:   1.6,
        cursorStyle:  "block",
        cursorBlink:  false,
        scrollback:   5000,
        disableStdin: true,
        convertEol:   true,
      });

      const fit   = new FitAddon();
      const links = new WebLinksAddon();
      term.loadAddon(fit);
      term.loadAddon(links);
      term.open(mountRef.current);
      fit.fit();

      termRef.current = term;
      fitRef.current  = fit;

      // Write idle hint
      if (renderedRef.current === 0) {
        term.write(`${ANSI.system}  Paste a GitHub repo URL above and click Analyze to begin.${RESET}\r\n`);
      }

      // Observe container resize
      resizeObsRef.current = new ResizeObserver(() => { fit.fit(); });
      resizeObsRef.current.observe(mountRef.current!);
    })();

    return () => {
      disposed = true;
      resizeObsRef.current?.disconnect();
      termRef.current?.dispose();
      termRef.current = null;
      fitRef.current  = null;
      renderedRef.current = 0;
    };
  }, []);

  // Write only new lines (incremental — never re-render existing)
  useEffect(() => {
    const term = termRef.current;
    if (!term || lines.length === 0) return;

    const newLines = lines.slice(renderedRef.current);
    for (const l of newLines) {
      term.write(`${ANSI[l.type]}${PREFIX[l.type]}${l.text.trim()}${RESET}\r\n`);
    }
    renderedRef.current = lines.length;
  }, [lines]);

  const statusColor =
    status === "running" ? "var(--accent)"  :
    status === "done"    ? "var(--success)" :
    status === "error"   ? "var(--error)"   : "var(--text-dim)";

  return (
    <div className="flex flex-col h-full" style={{ background: "#0C0C0C" }}>
      {/* Header bar — uses CSS var tokens, rounded top */}
      <div
        className="flex items-center justify-between px-3 py-1.5 shrink-0 rounded-t-md"
        style={{
          background: "var(--panel)",
          borderBottom: "1px solid var(--border)",
        }}
      >
        <span
          className="text-[10px] uppercase tracking-widest font-medium"
          style={{ color: "var(--text-muted)" }}
        >
          Terminal output
        </span>
        <div className="flex items-center gap-2">
          {status === "running" && (
            <span
              className="inline-block w-1.5 h-1.5 rounded-full"
              style={{ backgroundColor: "var(--accent)", animation: "pulse 1.5s infinite" }}
            />
          )}
          <span
            className="text-[9px] uppercase tracking-wider font-medium"
            style={{ color: statusColor }}
          >
            {status}
          </span>
          <span className="text-[9px] font-mono" style={{ color: "var(--text-dim)" }}>
            {lines.length}L
          </span>
        </div>
      </div>

      {/* xterm.js mount point — fills remaining space */}
      <div
        ref={mountRef}
        className="flex-1 min-h-0 px-1 py-1"
        style={{ background: "#0C0C0C", overflow: "hidden" }}
      />
    </div>
  );
}
