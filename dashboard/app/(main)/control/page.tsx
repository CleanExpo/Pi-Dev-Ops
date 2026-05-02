// app/(main)/control/page.tsx — unified command centre (RA-1092)
// Replaces /dashboard and /health with sticky TopBar + 2×2 panel grid.
"use client";

import TopBar from "@/components/control/TopBar";
import SwarmPanel from "@/components/control/SwarmPanel";
import ModelBadge from "@/components/control/ModelBadge";
import HealthGrid from "@/components/control/HealthGrid";
import BuildForm from "@/components/control/BuildForm";
import RoutineTable from "@/components/control/RoutineTable";
import ActiveBuildStrip from "@/components/control/ActiveBuildStrip";
import LiveActivityFeed from "@/components/control/LiveActivityFeed";
import CuratorProposalsPanel from "@/components/control/CuratorProposalsPanel";

export default function ControlPage() {
  return (
    <div className="flex flex-col" style={{ height: "100vh", overflow: "hidden" }}>
      {/* Sticky global top bar */}
      <TopBar />

      {/* RA-1440 — Mission Control live activity (throughput + queue + completions) */}
      <div className="px-4 pt-4 pb-2" style={{ background: "var(--background)" }}>
        <LiveActivityFeed />
      </div>

      {/* Always-visible live-build strip (only renders when a build is active) */}
      <div className="px-4 pt-2" style={{ background: "var(--background)" }}>
        <ActiveBuildStrip />
      </div>

      {/* 2×2 grid — fills remaining viewport height */}
      <div className="flex-1 overflow-auto p-4" style={{ minHeight: 0 }}>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 auto-rows-[minmax(300px,1fr)]">
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

          {/* Panel 5 — RA-1839 Curator proposals (spans both columns) */}
          <div className="md:col-span-2">
            <CuratorProposalsPanel />
          </div>
        </div>
      </div>
    </div>
  );
}
