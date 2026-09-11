"use client";
// Copy-to-clipboard code block.
//
// Extracted from BrainStatusPanel.tsx when that file was edited, per the
// CLAUDE.md file-length convention: the panel is over the 300-line convention
// and grandfathered, so touching it means extracting rather than adding.
// Self-contained — no props beyond the lines it renders.

import { useCallback, useState } from "react";

export default function CopyBlock({ lines }: { lines: string[] }) {
  const [copied, setCopied] = useState(false);
  const text = lines.join("\n");

  const copy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      /* clipboard denied */
    }
  }, [text]);

  if (!lines.length) return null;

  return (
    <div className="mt-2 relative">
      <pre
        className="text-xs p-3 rounded overflow-x-auto font-mono"
        style={{
          background: "var(--background)",
          border: "1px solid var(--border)",
          color: "var(--text)",
        }}
      >
        {text}
      </pre>
      <button
        type="button"
        onClick={() => void copy()}
        className="absolute top-2 right-2 text-[10px] font-medium px-2 py-1 rounded"
        style={{
          background: "var(--panel)",
          border: "1px solid var(--border)",
          color: copied ? "var(--success)" : "var(--text-muted)",
        }}
      >
        {copied ? "Copied" : "Copy"}
      </button>
    </div>
  );
}
