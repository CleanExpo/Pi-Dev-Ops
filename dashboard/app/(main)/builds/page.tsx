"use client";
// app/(main)/builds/page.tsx — Pi CEO build sessions (fan-out + evaluator scores)
// Polls the FastAPI Pi CEO server via the /api/pi-ceo proxy every 5s.

import { useEffect, useState, useCallback } from "react";

interface PiSession {
  id: string;
  repo: string;
  status: string;
  started: number;
  lines: number;
  parent: string | null;
  last_phase: string;
  evaluator_score: number | null;
  retry_count: number;
  evaluator_status: string;
}

const PHASES = ["clone", "analyze", "claude_check", "sandbox", "generator", "evaluator", "push"];
const PHASE_LABELS = ["Clone", "Analyze", "Check", "Sandbox", "Generate", "Evaluate", "Push"];

const STATUS_COLOR: Record<string, string> = {
  created:    "#888480",
  cloning:    "#E8751A",
  building:   "#E8751A",
  evaluating: "#FFD166",
  complete:   "#4ADE80",
  failed:     "#F87171",
  interrupted:"#888480",
  killed:     "#888480",
};

const EVAL_COLOR: Record<string, string> = {
  passed: "#4ADE80",
  warned: "#FFD166",
  pending: "#888480",
};

function repoName(url: string): string {
  return url.replace(/\.git$/, "").split("/").slice(-2).join("/");
}

function elapsed(started: number): string {
  if (!started) return "—";
  const s = Math.floor(Date.now() / 1000 - started);
  if (s < 60) return `${s}s`;
  return `${Math.floor(s / 60)}m ${s % 60}s`;
}

function PhaseBar({ lastPhase, status }: { lastPhase: string; status: string }) {
  const doneIdx = PHASES.indexOf(lastPhase);
  const isRunning = ["cloning", "building", "evaluating"].includes(status);
  return (
    <div className="flex gap-0.5 mt-1">
      {PHASES.map((p, i) => {
        const done = doneIdx >= i;
        const active = isRunning && doneIdx + 1 === i;
        return (
          <div
            key={p}
            title={PHASE_LABELS[i]}
            className="h-1 flex-1 rounded-sm"
            style={{
              background: done ? "#4ADE80" : active ? "#E8751A" : "#2A2727",
              opacity: done || active ? 1 : 0.4,
            }}
          />
        );
      })}
    </div>
  );
}

function ScoreBadge({ score, evalStatus }: { score: number | null; evalStatus: string }) {
  if (score === null) return null;
  const color = score >= 8 ? "#4ADE80" : score >= 6 ? "#FFD166" : "#F87171";
  return (
    <span
      className="font-mono text-[10px] px-1.5 py-0.5 rounded"
      style={{ background: "#1E1C1C", color, border: `1px solid ${EVAL_COLOR[evalStatus] ?? "#2A2727"}` }}
    >
      {score.toFixed(1)}/10
    </span>
  );
}

function SessionCard({ s, isChild }: { s: PiSession; isChild?: boolean }) {
  return (
    <div
      className="px-4 py-3 transition-colors"
      style={{
        borderBottom: "1px solid #1E1C1C",
        borderLeft: isChild ? "2px solid #2A2727" : "none",
        marginLeft: isChild ? "20px" : 0,
        background: "transparent",
      }}
    >
      <div className="flex items-start justify-between gap-4">
        {/* Left: repo + id */}
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-mono text-[11px] truncate" style={{ color: "#F0EDE8" }}>
              {repoName(s.repo)}
            </span>
            {isChild && (
              <span className="font-mono text-[9px]" style={{ color: "#888480" }}>
                [child]
              </span>
            )}
            <span className="font-mono text-[9px]" style={{ color: "#888480" }}>
              {s.id}
            </span>
          </div>
          <PhaseBar lastPhase={s.last_phase} status={s.status} />
        </div>

        {/* Right: badges */}
        <div className="flex items-center gap-2 shrink-0">
          {s.retry_count > 0 && (
            <span className="font-mono text-[9px] px-1 py-0.5 rounded" style={{ background: "#2A2727", color: "#FFD166" }}>
              {s.retry_count}x retry
            </span>
          )}
          <ScoreBadge score={s.evaluator_score} evalStatus={s.evaluator_status} />
          <span
            className="font-mono text-[9px] uppercase"
            style={{ color: STATUS_COLOR[s.status] ?? "#888480" }}
          >
            {s.status}
          </span>
        </div>
      </div>

      {/* Footer: meta */}
      <div className="flex items-center gap-3 mt-1">
        <span className="font-mono text-[9px]" style={{ color: "#888480" }}>
          {elapsed(s.started)} ago
        </span>
        <span className="font-mono text-[9px]" style={{ color: "#888480" }}>
          {s.lines} lines
        </span>
        {s.last_phase && (
          <span className="font-mono text-[9px]" style={{ color: "#888480" }}>
            last: {s.last_phase}
          </span>
        )}
      </div>
    </div>
  );
}

export default function BuildsPage() {
  const [sessions, setSessions] = useState<PiSession[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [lastFetch, setLastFetch] = useState<number>(0);

  const fetchSessions = useCallback(async () => {
    try {
      const res = await fetch("/api/pi-ceo/api/sessions");
      if (!res.ok) {
        const body = await res.json().catch(() => ({ error: res.statusText }));
        setError(body.error ?? `HTTP ${res.status}`);
        return;
      }
      const data: PiSession[] = await res.json();
      setSessions(data.sort((a, b) => b.started - a.started));
      setError(null);
      setLastFetch(Date.now());
    } catch (e) {
      setError(String(e));
    }
  }, []);

  useEffect(() => {
    fetchSessions();
    const t = setInterval(fetchSessions, 5000);
    return () => clearInterval(t);
  }, [fetchSessions]);

  // Group: parents + their children
  const parents = sessions.filter((s) => !s.parent);
  const childrenOf = (pid: string) => sessions.filter((s) => s.parent === pid);

  const activeCount = sessions.filter((s) =>
    ["cloning", "building", "evaluating"].includes(s.status)
  ).length;

  return (
    <div className="flex flex-col flex-1">
      {/* Header */}
      <div
        className="flex items-center justify-between px-4 py-2 shrink-0"
        style={{ borderBottom: "1px solid #2A2727" }}
      >
        <div className="flex items-center gap-3">
          <span className="font-mono text-[10px] uppercase tracking-widest" style={{ color: "#C8C5C0" }}>
            Pi CEO Builds — {sessions.length} sessions
          </span>
          {activeCount > 0 && (
            <span className="font-mono text-[9px] px-2 py-0.5 rounded" style={{ background: "#1E1C1C", color: "#E8751A" }}>
              {activeCount} active
            </span>
          )}
        </div>
        <div className="flex items-center gap-3">
          {lastFetch > 0 && (
            <span className="font-mono text-[9px]" style={{ color: "#888480" }}>
              updated {new Date(lastFetch).toLocaleTimeString()}
            </span>
          )}
          <button
            onClick={fetchSessions}
            className="font-mono text-[9px] px-2 py-1 transition-opacity hover:opacity-70"
            style={{ border: "1px solid #2A2727", color: "#C8C5C0" }}
          >
            REFRESH
          </button>
        </div>
      </div>

      {/* Error state */}
      {error && (
        <div className="px-4 py-3" style={{ borderBottom: "1px solid #2A2727" }}>
          <span className="font-mono text-[11px]" style={{ color: "#F87171" }}>
            {error.includes("unreachable") || error.includes("502")
              ? "Pi CEO server offline. Start with: cd app && uvicorn server.main:app --host 127.0.0.1 --port 7777"
              : error}
          </span>
          <div className="mt-1">
            <span className="font-mono text-[10px]" style={{ color: "#888480" }}>
              Set PI_CEO_URL and PI_CEO_PASSWORD in dashboard .env.local
            </span>
          </div>
        </div>
      )}

      {/* Empty state */}
      {!error && sessions.length === 0 && (
        <div className="flex flex-col flex-1 items-center justify-center">
          <p className="font-mono text-[12px]" style={{ color: "#C8C5C0" }}>No build sessions yet.</p>
          <p className="font-mono text-[10px] mt-2" style={{ color: "#888480" }}>
            Trigger a build via POST /api/build on the Pi CEO server.
          </p>
        </div>
      )}

      {/* Session list */}
      {parents.length > 0 && (
        <div className="overflow-y-auto flex-1">
          {parents.map((s) => {
            const children = childrenOf(s.id);
            return (
              <div key={s.id}>
                <SessionCard s={s} />
                {children.map((c) => (
                  <SessionCard key={c.id} s={c} isChild />
                ))}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
