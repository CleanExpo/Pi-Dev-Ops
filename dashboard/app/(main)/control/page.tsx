// app/(main)/control/page.tsx — unified command centre (RA-1092)
// Replaces /dashboard and /health with a 4-panel 2x2 grid.
"use client";

import SwarmPanel from "@/components/control/SwarmPanel";
import ModelBadge from "@/components/control/ModelBadge";
import HealthGrid from "@/components/control/HealthGrid";
import BuildForm from "@/components/control/BuildForm";
import RoutineTable from "@/components/control/RoutineTable";

export default function ControlPage() {
  return (
    <div
      className="flex flex-col"
      style={{ height: "calc(100vh - 52px)", overflow: "hidden" }}
    >
      {/* Header */}
      <div
        className="flex items-center justify-between px-4 h-[52px] shrink-0"
        style={{ borderBottom: "1px solid var(--border)", background: "var(--background)" }}
      >
        <div className="flex flex-col justify-center gap-0.5">
          <h1 className="text-lg font-semibold leading-none" style={{ color: "var(--text)" }}>
            Control
          </h1>
          <p className="text-xs leading-none" style={{ color: "var(--text-dim)" }}>
            Swarm · Model · Portfolio · Builds
          </p>
        </div>
      </div>

      {/* 2x2 grid — stacks on mobile */}
      <div className="flex-1 overflow-auto p-4">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 auto-rows-[minmax(280px,1fr)]">
          {/* Panel 1 — Swarm */}
          <SwarmPanel />

          {/* Panel 2 — Model + ZTE */}
          <ModelBadge />

          {/* Panel 3 — Portfolio health */}
          <HealthGrid />

          {/* Panel 4 — Build + routine runs */}
          <section
            className="flex flex-col h-full min-h-0"
            style={{ background: "var(--panel)", border: "1px solid var(--border)", borderRadius: 8 }}
            aria-label="Build and routine runs"
          >
            <header
              className="flex items-center justify-between px-4 py-2.5"
              style={{ borderBottom: "1px solid var(--border)" }}
            >
              <h2
                className="text-xs font-semibold uppercase tracking-widest"
                style={{ color: "var(--text-muted)" }}
              >
                Build &amp; Runs
              </h2>
            </header>
            <div className="flex-1 overflow-auto p-4 flex flex-col gap-4 min-h-0">
              <BuildForm />
              <div className="flex-1 min-h-0 flex flex-col">
                <RoutineTable />
              </div>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
