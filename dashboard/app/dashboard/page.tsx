"use client";

import { useState } from "react";
import TierCards from "@/components/TierCards";
import TaskRunner from "@/components/TaskRunner";
import LiveTerminal from "@/components/LiveTerminal";
import FileTree from "@/components/FileTree";
import SkillsPanel from "@/components/SkillsPanel";
import { API_BASE } from "@/lib/api";

function TopBar() {
  return (
    <header className="h-12 bg-pi-dark-2 border-b border-pi-border flex items-center justify-between px-6 shrink-0">
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full bg-green-400 status-dot-active" />
          <span className="font-mono text-[10px] text-pi-muted uppercase tracking-wider">
            Connected
          </span>
        </div>
        <span className="font-mono text-[10px] text-pi-muted/40">/</span>
        <span className="font-mono text-[10px] text-pi-muted/60 truncate max-w-[200px]">
          {API_BASE}
        </span>
      </div>
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-3 font-mono text-[10px] text-pi-muted">
          <span>
            <span className="text-pi-orange">Opus</span> · Orchestrator
          </span>
          <span>
            <span className="text-[#6B8CFF]">Sonnet</span> · Specialist
          </span>
          <span>
            <span className="text-[#4CAF82]">Haiku</span> · Worker
          </span>
        </div>
      </div>
    </header>
  );
}

export default function DashboardPage() {
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);

  return (
    <div className="flex flex-col flex-1 min-h-0">
      <TopBar />

      <main className="flex-1 overflow-y-auto">
        <div className="max-w-[1400px] mx-auto px-6 py-6 space-y-8">

          {/* Tier Status Cards */}
          <section>
            <TierCards />
          </section>

          {/* Task Runner + Terminal (side by side on large screens) */}
          <section className="grid grid-cols-1 xl:grid-cols-2 gap-6">
            <TaskRunner
              onSessionCreated={(id) => setActiveSessionId(id)}
            />
            <LiveTerminal activeSessionId={activeSessionId} />
          </section>

          {/* File Tree + Skills (side by side on large screens) */}
          <section className="grid grid-cols-1 xl:grid-cols-2 gap-6">
            <FileTree />
            <div className="min-h-[480px]">
              <SkillsPanel />
            </div>
          </section>

          {/* Footer */}
          <footer className="border-t border-pi-border pt-6 pb-4">
            <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
              <div>
                <p className="font-bebas text-lg tracking-widest text-pi-cream/40">
                  PI CEO
                </p>
                <p className="font-mono text-[10px] text-pi-muted/40">
                  Solo DevOps Tool — Claude Max Runtime
                </p>
              </div>
              <div className="font-mono text-[10px] text-pi-muted/40 space-y-0.5 text-right">
                <p>Orchestrator: Opus 4.6 · 1M ctx</p>
                <p>Specialist: Sonnet 4.6 · complex impl</p>
                <p>Worker: Haiku 4.5 · discrete tasks</p>
              </div>
            </div>
          </footer>
        </div>
      </main>
    </div>
  );
}
