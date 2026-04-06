"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import type { Model } from "@/lib/types";
import { TIER_INFO } from "@/lib/types";

const MODELS: Model[] = ["opus", "sonnet", "haiku"];

const ADW_TEMPLATES = [
  { label: "Feature Build", brief: "Decompose this brief into features. Build each feature. Write tests. Review the output. Open a PR." },
  { label: "Bug Fix", brief: "Reproduce the bug. Diagnose the root cause. Fix it. Verify the fix. Commit the changes." },
  { label: "Code Review", brief: "Read the full diff. Analyze for correctness, security, and style. Produce a detailed review report in .harness/review.md." },
  { label: "Research Spike", brief: "Research this topic thoroughly. Summarize findings. Produce a recommendation in .harness/spike.md." },
  { label: "Full Analysis", brief: "Analyze this codebase fully. Read every skill in skills/. Read the engine in src/tao/. Produce a detailed analysis in .harness/spec.md. Suggest improvements. Git commit changes." },
];

interface TaskRunnerProps {
  onSessionCreated?: (sessionId: string) => void;
}

export default function TaskRunner({ onSessionCreated }: TaskRunnerProps) {
  const [repoUrl, setRepoUrl] = useState("https://github.com/CleanExpo/Pi-Dev-Ops.git");
  const [brief, setBrief] = useState("");
  const [model, setModel] = useState<Model>("sonnet");
  const [launching, setLaunching] = useState(false);
  const [result, setResult] = useState<{ id: string; status: string } | null>(null);
  const [error, setError] = useState("");

  async function launch() {
    if (!repoUrl || !brief) return;
    setError("");
    setResult(null);
    setLaunching(true);
    try {
      const res = await api.build({ repo_url: repoUrl, brief, model });
      setResult({ id: res.session_id, status: res.status });
      onSessionCreated?.(res.session_id);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Launch failed");
    } finally {
      setLaunching(false);
    }
  }

  function applyTemplate(t: { label: string; brief: string }) {
    setBrief(t.brief);
  }

  return (
    <div id="build" className="bg-pi-dark-2 border border-pi-border rounded-lg p-5">
      <div className="flex items-center gap-2 mb-5">
        <span className="text-pi-orange text-sm">⚡</span>
        <h2 className="font-bebas text-xl tracking-widest text-pi-cream/80">
          Task Runner
        </h2>
      </div>

      <div className="space-y-4">
        {/* Repo URL */}
        <div>
          <label className="block font-mono text-[10px] text-pi-muted uppercase tracking-wider mb-1.5">
            Repository URL
          </label>
          <input
            type="text"
            value={repoUrl}
            onChange={(e) => setRepoUrl(e.target.value)}
            placeholder="https://github.com/org/repo.git"
            className="w-full bg-pi-dark-3 border border-pi-border rounded px-3 py-2.5 font-mono text-sm text-pi-cream placeholder:text-pi-muted/40 focus:border-pi-orange transition-colors"
          />
        </div>

        {/* Model selector */}
        <div>
          <label className="block font-mono text-[10px] text-pi-muted uppercase tracking-wider mb-1.5">
            Tier / Model
          </label>
          <div className="flex gap-2">
            {MODELS.map((m) => {
              const info = TIER_INFO[m];
              const active = model === m;
              return (
                <button
                  key={m}
                  onClick={() => setModel(m)}
                  className={`flex-1 px-3 py-2 rounded border text-xs font-barlow font-medium transition-all duration-150 ${
                    active
                      ? "border-pi-orange bg-pi-orange/10 text-pi-orange"
                      : "border-pi-border text-pi-muted hover:border-pi-border/60 hover:text-pi-cream"
                  }`}
                >
                  <div className="font-bebas text-sm tracking-wider">{info.label}</div>
                  <div className="font-mono text-[9px] opacity-60">{info.badge}</div>
                </button>
              );
            })}
          </div>
        </div>

        {/* ADW Templates */}
        <div>
          <label className="block font-mono text-[10px] text-pi-muted uppercase tracking-wider mb-1.5">
            Workflow Templates (ADW)
          </label>
          <div className="flex flex-wrap gap-1.5">
            {ADW_TEMPLATES.map((t) => (
              <button
                key={t.label}
                onClick={() => applyTemplate(t)}
                className="px-2.5 py-1 rounded border border-pi-border text-[10px] font-mono text-pi-muted hover:border-pi-orange/40 hover:text-pi-orange/80 transition-all duration-150"
              >
                {t.label}
              </button>
            ))}
          </div>
        </div>

        {/* Brief */}
        <div>
          <label className="block font-mono text-[10px] text-pi-muted uppercase tracking-wider mb-1.5">
            Brief (plain English)
          </label>
          <textarea
            value={brief}
            onChange={(e) => setBrief(e.target.value)}
            placeholder="Describe what you want Claude to do with this repo…"
            rows={5}
            className="w-full bg-pi-dark-3 border border-pi-border rounded px-3 py-2.5 font-mono text-sm text-pi-cream placeholder:text-pi-muted/40 focus:border-pi-orange transition-colors resize-none"
          />
        </div>

        {/* Error */}
        {error && (
          <p className="font-mono text-xs text-red-400 bg-red-400/10 border border-red-400/20 rounded px-3 py-2">
            ✗ {error}
          </p>
        )}

        {/* Success */}
        {result && (
          <div className="font-mono text-xs bg-green-400/10 border border-green-400/20 rounded px-3 py-2 space-y-0.5">
            <p className="text-green-400">✓ Session created</p>
            <p className="text-pi-muted">
              ID:{" "}
              <span className="text-pi-cream">{result.id}</span>
            </p>
          </div>
        )}

        {/* Launch */}
        <button
          onClick={launch}
          disabled={launching || !repoUrl || !brief}
          className="w-full bg-pi-orange text-pi-dark font-barlow font-bold text-sm tracking-wider uppercase py-3 rounded transition-all duration-200 hover:bg-pi-orange/90 disabled:opacity-40 disabled:cursor-not-allowed active:scale-[0.99] flex items-center justify-center gap-2"
        >
          {launching ? (
            <>
              <span className="inline-block w-3.5 h-3.5 border-2 border-pi-dark/40 border-t-pi-dark rounded-full animate-spin" />
              Launching…
            </>
          ) : (
            <>⚡ Launch Build</>
          )}
        </button>
      </div>
    </div>
  );
}
