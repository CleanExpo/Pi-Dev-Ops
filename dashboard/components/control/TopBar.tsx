// components/control/TopBar.tsx — sticky global top bar: logo · clock · model chip · theme toggle
"use client";

import { useEffect, useState } from "react";
import ThemeToggle from "@/components/ThemeToggle";
import ProjectSelector from "./ProjectSelector";
import { BRISBANE_LABEL, brisbaneTime } from "@/lib/brisbane-time";

interface ZteData {
  model: string;
  model_id: string;
}

// Empty until mounted: the server's render and the browser's first render
// would otherwise differ by the seconds between them (hydration mismatch).
function useLiveClock(): string {
  const [time, setTime] = useState("");
  useEffect(() => {
    const tick = () => setTime(`${brisbaneTime(new Date(), true)} ${BRISBANE_LABEL}`);
    tick();
    const t = setInterval(tick, 1000);
    return () => clearInterval(t);
  }, []);
  return time;
}

// null until /api/zte reports a model. The chip used to start as a hard-coded
// "claude-opus-5" and keep it whenever the read failed — an unobserved model
// shown as the active one. ModelBadge says "Not observed" for the same data.
function useModelChip(): string | null {
  const [model, setModel] = useState<string | null>(null);
  useEffect(() => {
    let cancelled = false;
    const load = () => fetch("/api/zte")
      .then((r) => r.ok ? r.json() : null)
      .then((d: ZteData | null) => { if (!cancelled) setModel(d?.model || null); })
      .catch(() => { if (!cancelled) setModel(null); });
    void load();
    const t = setInterval(() => void load(), 120_000);
    return () => {
      cancelled = true;
      clearInterval(t);
    };
  }, []);
  return model;
}

export default function TopBar() {
  const clock = useLiveClock();
  const model = useModelChip();

  return (
    <header
      className="flex items-center justify-between px-4 shrink-0"
      style={{
        height: 48,
        borderBottom: "1px solid var(--border)",
        background: "var(--background)",
        position: "sticky",
        top: 0,
        zIndex: 40,
      }}
    >
      {/* Left: logo */}
      <div className="flex items-center gap-2">
        <span
          className="text-sm font-semibold tracking-tight"
          style={{ color: "var(--accent)" }}
          aria-label="Pi CEO"
        >
          ⬡ Pi CEO
        </span>
        <span
          className="hidden sm:inline text-[10px] font-mono"
          style={{ color: "var(--text-dim)" }}
        >
          Second Brain
        </span>
      </div>

      {/* Right: project selector + clock + model + theme */}
      <div className="flex items-center gap-3">
        {/* RA-1103 — active project picker for remote/multi-project work */}
        <ProjectSelector />

        {/* Live clock */}
        <span
          className="hidden sm:inline text-[11px] font-mono tabular-nums"
          style={{ color: "var(--text-dim)" }}
          title="Brisbane time"
        >
          {clock}
        </span>

        {/* Model chip */}
        <span
          className="text-[10px] font-mono px-2 py-0.5 rounded"
          style={{
            color: model ? "var(--accent)" : "var(--text-dim)",
            background: "var(--accent-subtle)",
            border: "1px solid var(--accent)33",
          }}
          title={model ? `Active model: ${model}` : "Active model not observed"}
        >
          {model ?? "model unknown"}
        </span>

        {/* Theme toggle */}
        <ThemeToggle />
      </div>
    </header>
  );
}
