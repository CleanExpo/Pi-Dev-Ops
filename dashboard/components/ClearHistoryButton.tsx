// components/ClearHistoryButton.tsx — client component for clearing session history
"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

export default function ClearHistoryButton() {
  const router = useRouter();
  const [clearing, setClearing] = useState(false);

  async function clear() {
    if (!confirm("Delete all analysis history? This cannot be undone.")) return;
    setClearing(true);
    await fetch("/api/sessions", { method: "DELETE" }).catch(() => {});
    router.refresh();
    setClearing(false);
  }

  return (
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
  );
}
