"use client";

import { useState } from "react";

type FileNode =
  | { type: "file"; name: string; note?: string }
  | { type: "dir"; name: string; note?: string; children: FileNode[] };

// Pi Dev Ops project structure — static representation
const TREE: FileNode[] = [
  {
    type: "dir", name: "app", note: "Web server",
    children: [
      {
        type: "dir", name: "server", children: [
          { type: "file", name: "main.py", note: "FastAPI app, routes, WebSocket" },
          { type: "file", name: "auth.py", note: "HMAC tokens, rate limiting" },
          { type: "file", name: "config.py", note: "Env-var config" },
          { type: "file", name: "sessions.py", note: "Build lifecycle, subprocess" },
        ]
      },
      { type: "dir", name: "static", children: [{ type: "file", name: "index.html" }] },
      { type: "dir", name: "workspaces", children: [{ type: "file", name: "(ephemeral clones)" }] },
      { type: "file", name: "run.ps1", note: "Windows launcher" },
    ]
  },
  {
    type: "dir", name: "skills", note: "23 TAO skills",
    children: [
      { type: "dir", name: "Core (7)", children: [
        { type: "file", name: "tier-architect" }, { type: "file", name: "tier-orchestrator" },
        { type: "file", name: "tier-worker" }, { type: "file", name: "tier-evaluator" },
        { type: "file", name: "context-compressor" }, { type: "file", name: "token-budgeter" },
        { type: "file", name: "auto-generator" },
      ]},
      { type: "dir", name: "Frameworks (6)", children: [
        { type: "file", name: "piter-framework" }, { type: "file", name: "afk-agent" },
        { type: "file", name: "closed-loop-prompt" }, { type: "file", name: "hooks-system" },
        { type: "file", name: "agent-workflow" }, { type: "file", name: "agentic-review" },
      ]},
      { type: "dir", name: "Strategic (5)", children: [
        { type: "file", name: "zte-maturity" }, { type: "file", name: "agent-expert" },
        { type: "file", name: "leverage-audit" }, { type: "file", name: "agentic-loop" },
        { type: "file", name: "agentic-layer" },
      ]},
      { type: "dir", name: "Foundation (3)", children: [
        { type: "file", name: "big-three" }, { type: "file", name: "claude-max-runtime" },
        { type: "file", name: "pi-integration" },
      ]},
      { type: "dir", name: "Meta (2)", children: [
        { type: "file", name: "ceo-mode" }, { type: "file", name: "tao-skills" },
      ]},
    ]
  },
  {
    type: "dir", name: "src/tao", note: "Python orchestration engine",
    children: [
      { type: "dir", name: "schemas", children: [{ type: "file", name: "artifacts.py", note: "TaskSpec, TaskResult" }] },
      { type: "dir", name: "tiers", children: [{ type: "file", name: "config.py", note: "TierConfig, YAML loader" }] },
      { type: "dir", name: "budget", children: [{ type: "file", name: "tracker.py", note: "BudgetTracker" }] },
      { type: "dir", name: "agents", children: [{ type: "file", name: "__init__.py", note: "⚠ stub" }] },
      { type: "file", name: "skills.py", note: "Skill registry" },
    ]
  },
  {
    type: "dir", name: ".harness", note: "Harness state",
    children: [
      { type: "file", name: "config.yaml", note: "Agent config" },
      { type: "file", name: "spec.md", note: "Product spec (generated)" },
      { type: "file", name: "handoff.md", note: "Cross-session state" },
      { type: "file", name: "lessons.jsonl", note: "Agent-expert knowledge" },
    ]
  },
  { type: "file", name: "CLAUDE.md", note: "Project instructions" },
  { type: "file", name: "pyproject.toml", note: "Python deps" },
  { type: "file", name: "_deploy.py", note: "Bootstrap script" },
];

function FileIcon({ type, name }: { type: "file" | "dir"; name: string }) {
  if (type === "dir") return <span className="text-pi-orange/70">◻</span>;
  if (name.endsWith(".py")) return <span className="text-[#6B8CFF]">⬡</span>;
  if (name.endsWith(".md")) return <span className="text-[#4CAF82]">◈</span>;
  if (name.endsWith(".yaml") || name.endsWith(".json") || name.endsWith(".jsonl")) return <span className="text-[#FFD166]">◇</span>;
  if (name.endsWith(".ps1")) return <span className="text-[#C0AAFF]">▷</span>;
  return <span className="text-pi-muted/60">◻</span>;
}

function Node({ node, depth = 0 }: { node: FileNode; depth?: number }) {
  const [open, setOpen] = useState(depth < 1);

  if (node.type === "file") {
    return (
      <div
        className="flex items-center gap-1.5 py-0.5 px-2 rounded hover:bg-pi-dark-3 group"
        style={{ paddingLeft: `${8 + depth * 14}px` }}
      >
        <FileIcon type="file" name={node.name} />
        <span className="font-mono text-[11px] text-pi-muted group-hover:text-pi-cream transition-colors truncate">
          {node.name}
        </span>
        {node.note && (
          <span className="font-mono text-[9px] text-pi-muted/40 truncate hidden group-hover:block">
            — {node.note}
          </span>
        )}
      </div>
    );
  }

  return (
    <div>
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-1.5 py-0.5 px-2 w-full text-left rounded hover:bg-pi-dark-3 group transition-colors"
        style={{ paddingLeft: `${8 + depth * 14}px` }}
      >
        <span className="font-mono text-[9px] text-pi-muted/60 w-3 text-center">
          {open ? "▾" : "▸"}
        </span>
        <FileIcon type="dir" name={node.name} />
        <span className="font-mono text-[11px] text-pi-cream/70 group-hover:text-pi-cream transition-colors">
          {node.name}
        </span>
        {node.note && (
          <span className="font-mono text-[9px] text-pi-muted/40 ml-1 hidden group-hover:block">
            {node.note}
          </span>
        )}
      </button>
      {open && (
        <div>
          {node.children.map((child, i) => (
            <Node key={i} node={child} depth={depth + 1} />
          ))}
        </div>
      )}
    </div>
  );
}

export default function FileTree() {
  return (
    <div
      id="files"
      className="bg-pi-dark-2 border border-pi-border rounded-lg flex flex-col"
      style={{ height: "480px" }}
    >
      {/* Header */}
      <div className="px-4 py-3 border-b border-pi-border flex items-center gap-2 shrink-0">
        <span className="text-pi-muted text-sm">◻</span>
        <h2 className="font-bebas text-lg tracking-widest text-pi-cream/80">
          File Tree
        </h2>
        <span className="ml-auto font-mono text-[9px] text-pi-muted">
          Pi Dev Ops
        </span>
      </div>

      {/* Tree */}
      <div className="flex-1 overflow-y-auto py-2">
        {TREE.map((node, i) => (
          <Node key={i} node={node} />
        ))}
      </div>

      {/* Legend */}
      <div className="px-4 py-2 border-t border-pi-border flex items-center gap-4 shrink-0">
        {[
          { icon: "⬡", label: ".py", color: "#6B8CFF" },
          { icon: "◈", label: ".md", color: "#4CAF82" },
          { icon: "◇", label: ".yaml/.json", color: "#FFD166" },
          { icon: "◻", label: "dir", color: "#E8751A" },
        ].map(({ icon, label, color }) => (
          <span key={label} className="flex items-center gap-1">
            <span style={{ color }} className="text-[10px]">{icon}</span>
            <span className="font-mono text-[9px] text-pi-muted">{label}</span>
          </span>
        ))}
      </div>
    </div>
  );
}
