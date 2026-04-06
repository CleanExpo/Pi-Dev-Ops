// components/ActionsPanel.tsx — post-analysis actions: board notes, CoWork, GitHub Issues, Dockerfile
"use client";

import { useState } from "react";
import type { AnalysisResult } from "@/lib/types";

type ActionId = "board_notes" | "cowork_brief" | "github_issues" | "dockerfile";

const ACTIONS: { id: ActionId; label: string; desc: string; icon: string }[] = [
  {
    id: "board_notes",
    label: "BOARD NOTES",
    desc: "Generate executive board meeting notes from the analysis",
    icon: "▦",
  },
  {
    id: "cowork_brief",
    label: "COWORK BRIEF",
    desc: "Generate a Claude Desktop CoWork session brief",
    icon: "◈",
  },
  {
    id: "github_issues",
    label: "CREATE ISSUES",
    desc: "Create GitHub issues from gap analysis findings",
    icon: "⊕",
  },
  {
    id: "dockerfile",
    label: "DOCKERFILE",
    desc: "Generate a production Dockerfile + docker-compose.yml",
    icon: "◻",
  },
];

interface Props {
  result: Partial<AnalysisResult>;
}

export default function ActionsPanel({ result }: Props) {
  const [activeAction, setActiveAction] = useState<ActionId | null>(null);
  const [output, setOutput] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);

  const hasResults = result.repoName && (result.executiveSummary || result.techStack);

  async function runAction(id: ActionId) {
    if (loading) return;
    setActiveAction(id);
    setOutput("");
    setError("");
    setLoading(true);
    setCopied(false);

    try {
      const body: Record<string, unknown> = { action: id, result };

      // For GitHub issues, extract owner/repo from repoUrl
      if (id === "github_issues" && result.repoUrl) {
        const match = result.repoUrl.match(/github\.com\/([^/]+)\/([^/]+)/);
        if (match) {
          body.repoOwner = match[1];
          body.repoName = match[2];
        }
      }

      const res = await fetch("/api/actions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });

      const data = await res.json() as { output?: string; error?: string };
      if (!res.ok || data.error) throw new Error(data.error ?? `HTTP ${res.status}`);
      setOutput(data.output ?? "");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Action failed");
    } finally {
      setLoading(false);
    }
  }

  function copy() {
    navigator.clipboard.writeText(output).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  function openInClaude() {
    // Open Claude Desktop with the output as context
    const encoded = encodeURIComponent(output.slice(0, 2000));
    window.open(`claude://chat?text=${encoded}`, "_blank");
  }

  if (!hasResults) {
    return (
      <div className="px-4 py-8 text-center">
        <p className="font-mono text-[10px]" style={{ color: "#888480" }}>
          Run an analysis first to unlock actions.
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col" style={{ minHeight: "100%" }}>
      {/* Repo context */}
      <div className="px-3 py-2" style={{ borderBottom: "1px solid #2A2727" }}>
        <p className="font-mono text-[10px]" style={{ color: "#C8C5C0" }}>
          {result.repoName} · ZTE L{result.zteLevel ?? "?"} · {(result.techStack ?? []).slice(0, 3).join(", ")}
        </p>
      </div>

      {/* Action buttons */}
      <div className="grid grid-cols-2 gap-px" style={{ background: "#2A2727" }}>
        {ACTIONS.map((a) => (
          <button
            key={a.id}
            onClick={() => runAction(a.id)}
            disabled={loading}
            className="flex flex-col items-start px-3 py-3 text-left transition-colors disabled:opacity-40"
            style={{
              background: activeAction === a.id ? "#181616" : "#111111",
              borderBottom: activeAction === a.id ? "1px solid #E8751A" : "1px solid transparent",
            }}
          >
            <div className="flex items-center gap-1.5 mb-1">
              <span className="font-mono text-[12px]" style={{ color: "#E8751A" }}>{a.icon}</span>
              <span className="font-mono text-[9px] tracking-widest" style={{ color: "#F0EDE8" }}>
                {a.label}
              </span>
              {loading && activeAction === a.id && (
                <span className="font-mono text-[8px]" style={{ color: "#E8751A" }}>…</span>
              )}
            </div>
            <p className="font-mono text-[8px] leading-relaxed" style={{ color: "#888480" }}>
              {a.desc}
            </p>
          </button>
        ))}
      </div>

      {/* Error */}
      {error && (
        <div className="px-3 py-2 font-mono text-[10px]" style={{ background: "#1a0808", color: "#F87171" }}>
          ✗ {error}
        </div>
      )}

      {/* Output */}
      {output && (
        <div className="flex flex-col flex-1 min-h-0">
          {/* Output toolbar */}
          <div
            className="flex items-center justify-between px-3 py-1.5 shrink-0"
            style={{ borderTop: "1px solid #2A2727", borderBottom: "1px solid #2A2727" }}
          >
            <span className="font-mono text-[9px] uppercase tracking-widest" style={{ color: "#C8C5C0" }}>
              {ACTIONS.find((a) => a.id === activeAction)?.label} OUTPUT
            </span>
            <div className="flex items-center gap-3">
              <button
                onClick={openInClaude}
                className="font-mono text-[9px] tracking-wider"
                style={{ color: "#E8751A" }}
              >
                OPEN IN CLAUDE ↗
              </button>
              <button
                onClick={copy}
                className="font-mono text-[9px] tracking-wider"
                style={{ color: copied ? "#4ADE80" : "#C8C5C0" }}
              >
                {copied ? "COPIED ✓" : "COPY"}
              </button>
            </div>
          </div>

          {/* Output content */}
          <div
            className="flex-1 overflow-y-auto px-3 py-2 font-mono text-[11px] leading-relaxed whitespace-pre-wrap"
            style={{ color: "#E8E4DE", background: "#0C0C0C" }}
          >
            {output}
          </div>
        </div>
      )}

      {/* Claude Desktop status */}
      <div
        className="px-3 py-2 shrink-0 font-mono text-[8px]"
        style={{ borderTop: "1px solid #2A2727", color: "#888480" }}
      >
        <span style={{ color: "#4ADE80" }}>●</span> Claude Desktop MCP registered · pi-ceo server active
        <br />
        Ask Claude: <span style={{ color: "#C8C5C0" }}>&ldquo;get_last_analysis&rdquo;</span> or <span style={{ color: "#C8C5C0" }}>&ldquo;generate_board_notes&rdquo;</span>
      </div>
    </div>
  );
}
