// app/error.tsx — Next.js App Router global error boundary
"use client";

import { useEffect } from "react";
import { CSS } from "@/lib/brand-tokens";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("[GlobalError]", error);
  }, [error]);

  return (
    <div
      className="dark flex flex-col items-center justify-center min-h-screen font-mono"
      style={{ background: "var(--background)", color: "var(--text)" }}
    >
      <div
        className="w-full max-w-lg mx-4 p-8"
        style={{ border: `1px solid ${CSS.error}`, background: "var(--panel)" }}
      >
        <div className="flex items-center gap-3 mb-4">
          <span className="text-[18px]" style={{ color: CSS.error }}>✗</span>
          <span
            className="text-[14px] font-bold uppercase tracking-widest"
            style={{ color: CSS.error, fontFamily: "'Bebas Neue', sans-serif" }}
          >
            Application Error
          </span>
        </div>

        <p className="text-[11px] mb-2 leading-relaxed" style={{ color: "var(--text-muted)" }}>
          {error.message || "An unexpected error occurred."}
        </p>
        {error.digest && (
          <p className="text-[9px] mb-6" style={{ color: "var(--text-dim)" }}>
            Error ID: {error.digest}
          </p>
        )}

        <div className="flex gap-3">
          <button
            onClick={reset}
            className="font-mono text-[10px] px-5 py-2 tracking-wider"
            style={{ background: CSS.accent, color: CSS.onAccent, fontWeight: 700 }}
          >
            RETRY
          </button>
          <a
            href="/control"
            className="font-mono text-[10px] px-5 py-2 tracking-wider"
            style={{ background: "var(--panel-hover)", color: "var(--text-muted)", border: "1px solid var(--border)" }}
          >
            ← CONTROL
          </a>
        </div>
      </div>
    </div>
  );
}
