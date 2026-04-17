// components/ClearHistoryButton.tsx — client component for clearing session history
"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

export default function ClearHistoryButton() {
  const router = useRouter();
  const [clearing, setClearing] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function clear() {
    if (!confirm("Delete all analysis history? This cannot be undone.")) return;
    setClearing(true);
    setErr(null);
    // RA-1109: don't swallow errors silently — user must know if the
    // destructive DELETE succeeded, failed, or timed out.
    try {
      const res = await fetch("/api/sessions", { method: "DELETE" });
      if (!res.ok) {
        const body = await res.text().catch(() => "");
        setErr(`HTTP ${res.status} — ${body.slice(0, 120) || "no detail"}`);
        return;
      }
      router.refresh();
    } catch (e) {
      setErr(`Network error: ${String(e).slice(0, 140)}`);
    } finally {
      setClearing(false);
    }
  }

  return (
    <div className="flex flex-col items-end gap-1">
      <button
        onClick={clear}
        disabled={clearing}
        className="font-mono text-[9px] transition-colors disabled:opacity-40"
        style={{ color: "#888480" }}
        onMouseOver={(e) => (e.currentTarget.style.color = "#F87171")}
        onMouseOut={(e) => (e.currentTarget.style.color = "#888480")}
      >
        {clearing ? "CLEARING…" : "CLEAR ALL"}
      </button>
      {err && (
        <span className="text-[9px] font-mono" style={{ color: "var(--error)" }}>
          ⚠ {err}
        </span>
      )}
    </div>
  );
}
