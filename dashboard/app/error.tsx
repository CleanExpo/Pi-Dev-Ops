// app/error.tsx — Next.js App Router global error boundary
"use client";

import { useEffect } from "react";

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
      className="flex flex-col items-center justify-center min-h-screen font-mono"
      style={{ background: "#0A0A0A", color: "#F0EDE8" }}
    >
      <div
        className="w-full max-w-lg mx-4 p-8"
        style={{ border: "1px solid #F87171", background: "#1a0808" }}
      >
        <div className="flex items-center gap-3 mb-4">
          <span className="text-[18px]" style={{ color: "#F87171" }}>✗</span>
          <span
            className="text-[14px] font-bold uppercase tracking-widest"
            style={{ color: "#F87171", fontFamily: "'Bebas Neue', sans-serif" }}
          >
            Application Error
          </span>
        </div>

        <p className="text-[11px] mb-2 leading-relaxed" style={{ color: "#C8C5C0" }}>
          {error.message || "An unexpected error occurred."}
        </p>
        {error.digest && (
          <p className="text-[9px] mb-6" style={{ color: "#888480" }}>
            Error ID: {error.digest}
          </p>
        )}

        <div className="flex gap-3">
          <button
            onClick={reset}
            className="font-mono text-[10px] px-5 py-2 tracking-wider"
            style={{ background: "#E8751A", color: "#FFF", fontWeight: 700 }}
          >
            RETRY
          </button>
          <a
            href="/dashboard"
            className="font-mono text-[10px] px-5 py-2 tracking-wider"
            style={{ background: "#141414", color: "#C8C5C0", border: "1px solid #3A3632" }}
          >
            ← DASHBOARD
          </a>
        </div>
      </div>
    </div>
  );
}
