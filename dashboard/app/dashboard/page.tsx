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
    <header
      className="h-12 flex items-center justify-between px-6 shrink-0"
      style={{
        background: "rgba(10,10,10,0.95)",
        borderBottom: "1px solid rgba(232,117,26,0.15)",
        backdropFilter: "blur(8px)",
      }}
    >
      {/* Left — hero mini logo */}
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-1">
          <span
            className="font-bebas text-base leading-none"
            style={{ color: "#E8751A" }}
          >
            π
          </span>
          <span className="font-bebas text-base tracking-widest text-white leading-none">
            i CEO
          </span>
        </div>
        <span className="text-white/20 text-xs">·</span>
        <div className="flex items-center gap-1.5">
          <span
            className="w-1.5 h-1.5 rounded-full status-dot-active"
            style={{ backgroundColor: "#4CAF82" }}
          />
          <span className="font-mono text-[10px] text-white/40 uppercase tracking-wider">
            Connected
          </span>
        </div>
        <span className="font-mono text-[10px] text-white/20 hidden sm:block truncate max-w-[180px]">
          {API_BASE}
        </span>
      </div>

      {/* Right — tier legend */}
      <div className="hidden md:flex items-center gap-4 font-mono text-[10px]">
        <span>
          <span style={{ color: "#E8751A" }}>Opus</span>
          <span className="text-white/30"> · Orchestrator</span>
        </span>
        <span>
          <span style={{ color: "#6B8CFF" }}>Sonnet</span>
          <span className="text-white/30"> · Specialist</span>
        </span>
        <span>
          <span style={{ color: "#4CAF82" }}>Haiku</span>
          <span className="text-white/30"> · Worker</span>
        </span>
      </div>
    </header>
  );
}

function HeroBanner() {
  return (
    <div
      className="relative overflow-hidden mx-6 mt-6 rounded-xl"
      style={{ height: "160px" }}
    >
      {/* Background image */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src="/pi-ceo-hero.jpg"
        alt="Pi CEO"
        className="absolute inset-0 w-full h-full object-cover object-top"
        style={{ filter: "brightness(0.4)" }}
      />
      {/* Gradient overlay */}
      <div
        className="absolute inset-0"
        style={{
          background:
            "linear-gradient(90deg, rgba(10,10,10,0.85) 0%, rgba(10,10,10,0.3) 50%, rgba(10,10,10,0.7) 100%)",
        }}
      />
      {/* Orange center glow */}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          background:
            "radial-gradient(ellipse 60% 80% at 50% 50%, rgba(232,117,26,0.2) 0%, transparent 70%)",
        }}
      />

      {/* Content */}
      <div className="relative h-full flex items-center px-8 gap-6">
        <div>
          <div className="flex items-baseline gap-1 mb-1">
            <span
              className="font-bebas text-4xl leading-none"
              style={{ color: "#E8751A" }}
            >
              π
            </span>
            <span className="font-bebas text-4xl tracking-widest text-white leading-none">
              i CEO
            </span>
          </div>
          <p className="font-barlow text-white/70 text-sm font-medium tracking-wide">
            Solo DevOps Tool
          </p>
          <p className="font-barlow text-white/40 text-xs tracking-wider">
            Powered by Claude Harness
          </p>
        </div>

        {/* Divider */}
        <div
          className="hidden sm:block w-px self-stretch my-4"
          style={{ background: "rgba(232,117,26,0.3)" }}
        />

        {/* Tier summary */}
        <div className="hidden sm:flex flex-col gap-2">
          {[
            { model: "Opus 4.6", role: "Orchestrator — Plans & delegates", color: "#E8751A" },
            { model: "Sonnet 4.6", role: "Specialist — Complex impl", color: "#6B8CFF" },
            { model: "Haiku 4.5", role: "Worker — Discrete tasks", color: "#4CAF82" },
          ].map(({ model, role, color }) => (
            <div key={model} className="flex items-center gap-2">
              <span
                className="font-mono text-[10px] font-medium"
                style={{ color }}
              >
                {model}
              </span>
              <span className="font-mono text-[10px] text-white/35">{role}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export default function DashboardPage() {
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);

  return (
    <div className="flex flex-col flex-1 min-h-0">
      <TopBar />

      <main className="flex-1 overflow-y-auto">
        <HeroBanner />

        <div className="max-w-[1400px] mx-auto px-6 py-6 space-y-8">

          {/* Tier Status Cards */}
          <section>
            <TierCards />
          </section>

          {/* Task Runner + Terminal */}
          <section className="grid grid-cols-1 xl:grid-cols-2 gap-6">
            <TaskRunner onSessionCreated={(id) => setActiveSessionId(id)} />
            <LiveTerminal activeSessionId={activeSessionId} />
          </section>

          {/* File Tree + Skills */}
          <section className="grid grid-cols-1 xl:grid-cols-2 gap-6">
            <FileTree />
            <div className="min-h-[480px]">
              <SkillsPanel />
            </div>
          </section>

          {/* Footer */}
          <footer
            className="border-t pt-6 pb-4"
            style={{ borderColor: "rgba(232,117,26,0.15)" }}
          >
            <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
              <div>
                <div className="flex items-baseline gap-1 mb-0.5">
                  <span
                    className="font-bebas text-base leading-none"
                    style={{ color: "#E8751A" }}
                  >
                    π
                  </span>
                  <span className="font-bebas text-base tracking-widest text-white/40 leading-none">
                    i CEO
                  </span>
                </div>
                <p className="font-mono text-[10px] text-white/25">
                  Solo DevOps Tool — Claude Max Runtime
                </p>
              </div>
              <div className="font-mono text-[10px] text-white/25 text-right space-y-0.5">
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
