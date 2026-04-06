"use client";

import { useState } from "react";

const SKILLS = [
  // Core
  { name: "tier-architect", layer: "Core", status: "✅", desc: "Design model-to-role tier hierarchy" },
  { name: "tier-orchestrator", layer: "Core", status: "✅", desc: "Top-tier planning + fan-out delegation" },
  { name: "tier-worker", layer: "Core", status: "✅", desc: "Discrete execution, escalation rules" },
  { name: "tier-evaluator", layer: "Core", status: "✅", desc: "QA grading with 4 dimensions" },
  { name: "context-compressor", layer: "Core", status: "✅", desc: "Truncate/extract at tier boundaries" },
  { name: "token-budgeter", layer: "Core", status: "⚠️", desc: "Track token spend per tier" },
  { name: "auto-generator", layer: "Core", status: "✅", desc: "Generate tier configs from briefs" },
  // Frameworks
  { name: "piter-framework", layer: "Framework", status: "✅", desc: "5-pillar AFK setup (P/I/T/E/R)" },
  { name: "afk-agent", layer: "Framework", status: "✅", desc: "Bounded unattended runs" },
  { name: "closed-loop-prompt", layer: "Framework", status: "✅", desc: "Self-correcting with verification" },
  { name: "hooks-system", layer: "Framework", status: "✅", desc: "6 lifecycle hooks for observability" },
  { name: "agent-workflow", layer: "Framework", status: "✅", desc: "ADW templates (feature/bug/chore)" },
  { name: "agentic-review", layer: "Framework", status: "✅", desc: "6-dimension quality review" },
  // Strategic
  { name: "zte-maturity", layer: "Strategic", status: "✅", desc: "3-level ZTE maturity model" },
  { name: "agent-expert", layer: "Strategic", status: "⚠️", desc: "Act-Learn-Reuse cycle" },
  { name: "leverage-audit", layer: "Strategic", status: "⚠️", desc: "12-point diagnostic" },
  { name: "agentic-loop", layer: "Strategic", status: "✅", desc: "Two-prompt infinite loop" },
  { name: "agentic-layer", layer: "Strategic", status: "✅", desc: "Dual-interface product design" },
  // Foundation
  { name: "big-three", layer: "Foundation", status: "✅", desc: "Model/Prompt/Context framework" },
  { name: "claude-max-runtime", layer: "Foundation", status: "✅", desc: "Tier mapping for Max plan" },
  { name: "pi-integration", layer: "Foundation", status: "✅", desc: "Multi-provider bridge" },
  // Meta
  { name: "ceo-mode", layer: "Meta", status: "✅", desc: "Strategic decision-making" },
  { name: "tao-skills", layer: "Meta", status: "✅", desc: "Master skill index" },
];

const LAYERS = ["All", "Core", "Framework", "Strategic", "Foundation", "Meta"];

const LAYER_COLORS: Record<string, string> = {
  Core: "#E8751A",
  Framework: "#6B8CFF",
  Strategic: "#C0AAFF",
  Foundation: "#4CAF82",
  Meta: "#FFD166",
};

export default function SkillsPanel() {
  const [filter, setFilter] = useState("All");
  const [search, setSearch] = useState("");

  const visible = SKILLS.filter(
    (s) =>
      (filter === "All" || s.layer === filter) &&
      (search === "" ||
        s.name.includes(search.toLowerCase()) ||
        s.desc.toLowerCase().includes(search.toLowerCase()))
  );

  return (
    <div id="skills" className="bg-pi-dark-2 border border-pi-border rounded-lg">
      <div className="px-4 py-3 border-b border-pi-border flex flex-col sm:flex-row sm:items-center gap-2">
        <div className="flex items-center gap-2">
          <span className="text-pi-orange text-sm">◆</span>
          <h2 className="font-bebas text-xl tracking-widest text-pi-cream/80">
            Skills
          </h2>
          <span className="font-mono text-[10px] text-pi-muted ml-1">
            {SKILLS.length} loaded
          </span>
        </div>
        <div className="flex-1 sm:flex sm:justify-end gap-2">
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search skills…"
            className="bg-pi-dark-3 border border-pi-border rounded px-2.5 py-1 font-mono text-[11px] text-pi-cream placeholder:text-pi-muted/40 focus:border-pi-orange w-full sm:w-40"
          />
        </div>
      </div>

      {/* Layer filter */}
      <div className="px-4 py-2 border-b border-pi-border flex gap-1.5 flex-wrap">
        {LAYERS.map((l) => (
          <button
            key={l}
            onClick={() => setFilter(l)}
            className={`px-2.5 py-0.5 rounded text-[10px] font-mono transition-all duration-150 border ${
              filter === l
                ? "border-pi-orange bg-pi-orange/10 text-pi-orange"
                : "border-pi-border text-pi-muted hover:text-pi-cream"
            }`}
          >
            {l}
          </button>
        ))}
      </div>

      {/* Skills grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-px bg-pi-border p-px">
        {visible.map((skill) => {
          const color = LAYER_COLORS[skill.layer] ?? "#888";
          return (
            <div
              key={skill.name}
              className="bg-pi-dark-2 p-3 hover:bg-pi-dark-3 transition-colors group"
            >
              <div className="flex items-start justify-between gap-2">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5 mb-0.5">
                    <span
                      className="font-mono text-[11px] font-medium text-pi-cream truncate"
                    >
                      {skill.name}
                    </span>
                  </div>
                  <p className="font-mono text-[9px] text-pi-muted leading-relaxed">
                    {skill.desc}
                  </p>
                </div>
                <div className="shrink-0 flex flex-col items-end gap-1">
                  <span className="text-[10px]">{skill.status}</span>
                  <span
                    className="font-mono text-[8px] px-1.5 py-0.5 rounded"
                    style={{ color, backgroundColor: color + "15" }}
                  >
                    {skill.layer}
                  </span>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {visible.length === 0 && (
        <div className="px-4 py-8 text-center font-mono text-xs text-pi-muted">
          No skills match your filter.
        </div>
      )}
    </div>
  );
}
