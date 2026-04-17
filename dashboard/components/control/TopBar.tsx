// components/control/TopBar.tsx — sticky global top bar: logo · clock · model chip · theme toggle
"use client";

import { useEffect, useState } from "react";
import ThemeToggle from "@/components/ThemeToggle";
import ProjectSelector from "./ProjectSelector";

interface ZteData {
  model: string;
  model_id: string;
}

function useLiveClock(): string {
  const [time, setTime] = useState(() =>
    new Date().toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit" })
  );
  useEffect(() => {
    const t = setInterval(() => {
      setTime(new Date().toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit" }));
    }, 1000);
    return () => clearInterval(t);
  }, []);
  return time;
}

function useModelChip(): string {
  const [model, setModel] = useState<string>("claude-opus-4-7");
  useEffect(() => {
    let cancelled = false;
    fetch("/api/zte")
      .then((r) => r.ok ? r.json() : null)
      .then((d: ZteData | null) => {
        if (!cancelled && d?.model) setModel(d.model);
      })
      .catch(() => undefined);
    const t = setInterval(() => {
      fetch("/api/zte")
        .then((r) => r.ok ? r.json() : null)
        .then((d: ZteData | null) => {
          if (!cancelled && d?.model) setModel(d.model);
        })
        .catch(() => undefined);
    }, 120_000);
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
          ⬡ Pi-CEO
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
          aria-live="polite"
          aria-atomic="true"
        >
          {clock}
        </span>

        {/* Model chip */}
        <span
          className="text-[10px] font-mono px-2 py-0.5 rounded"
          style={{
            color: "var(--accent)",
            background: "var(--accent-subtle)",
            border: "1px solid var(--accent)33",
          }}
          title={`Active model: ${model}`}
        >
          {model}
        </span>

        {/* Theme toggle */}
        <ThemeToggle />
      </div>
    </header>
  );
}
