"use client";
// app/(main)/builds/page.tsx — Pi CEO build sessions with live log streaming

import { useEffect, useState, useCallback, useRef } from "react";

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

interface LogLine {
  i: number;
  type: string;
  text: string;
  ts: number;
  // phase_metric extras (optional fields present only for type === "phase_metric")
  phase?: string;
  duration_s?: number;
  cost_usd?: number;
}

interface PhaseMetric {
  duration_s: number;
  cost_usd: number;
}

const PHASES = ["clone", "analyze", "claude_check", "sandbox", "generator", "evaluator", "push"];
const PHASE_LABELS = ["Clone", "Analyze", "Check", "Sandbox", "Generate", "Evaluate", "Push"];
// Map backend metric phase names to PHASES array keys
const METRIC_PHASE_MAP: Record<string, string> = {
  clone:    "clone",
  analyze:  "analyze",
  plan:     "claude_check",
  generate: "generator",
  evaluate: "evaluator",
  push:     "push",
};

const STATUS_COLOR: Record<string, string> = {
  created:    "var(--text-dim)",
  cloning:    "var(--accent)",
  building:   "var(--accent)",
  evaluating: "#FFD166",
  complete:   "#4ADE80",
  done:       "#4ADE80",
  failed:     "#F87171",
  interrupted:"var(--text-dim)",
  killed:     "var(--text-dim)",
};

const LINE_COLOR: Record<string, string> = {
  phase:   "var(--accent)",
  success: "#4ADE80",
  error:   "#F87171",
  tool:    "#6B8CFF",
  agent:   "var(--text-muted)",
  metric:  "#FFD166",
  system:  "var(--text-dim)",
  output:  "var(--text-dim)",
  stderr:  "#F87171",
  done:    "#4ADE80",
};

const EVAL_COLOR: Record<string, string> = {
  passed: "#4ADE80",
  warned: "#FFD166",
  pending: "var(--text-dim)",
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

function PhaseBar({
  lastPhase,
  status,
  phaseMetrics,
}: {
  lastPhase: string;
  status: string;
  phaseMetrics: Record<string, PhaseMetric>;
}) {
  const doneIdx = PHASES.indexOf(lastPhase);
  const isRunning = ["cloning", "building", "evaluating"].includes(status);
  return (
    <div className="flex gap-1 mt-1.5 flex-wrap">
      {PHASES.map((p, i) => {
        const done = doneIdx >= i;
        const active = isRunning && doneIdx + 1 === i;
        const metric = phaseMetrics[p];
        return (
          <div key={p} className="flex items-center gap-0.5">
            <div
              title={PHASE_LABELS[i]}
              className="h-1 w-8 rounded-sm"
              style={{
                background: done ? "#4ADE80" : active ? "var(--accent)" : "var(--border)",
                opacity: done || active ? 1 : 0.4,
              }}
            />
            {metric && (
              <span
                className="font-mono text-[9px]"
                style={{ color: "var(--text-dim)" }}
                title={`${PHASE_LABELS[i]}: ${metric.duration_s}s · $${metric.cost_usd.toFixed(4)}`}
              >
                {metric.duration_s}s{metric.cost_usd > 0 ? ` · $${metric.cost_usd.toFixed(2)}` : ""}
              </span>
            )}
          </div>
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
      style={{ background: "var(--panel)", color, border: `1px solid ${EVAL_COLOR[evalStatus] ?? "var(--border)"}` }}
    >
      {score.toFixed(1)}/10
    </span>
  );
}

function LogPanel({
  sid,
  status,
  onPhaseMetric,
}: {
  sid: string;
  status: string;
  onPhaseMetric: (phase: string, metric: PhaseMetric) => void;
}) {
  const [lines, setLines] = useState<LogLine[]>([]);
  const [streaming, setStreaming] = useState(true);
  const bottomRef = useRef<HTMLDivElement>(null);
  const esRef = useRef<EventSource | null>(null);
  const cursorRef = useRef(0);
  const onPhaseMetricRef = useRef(onPhaseMetric);
  useEffect(() => { onPhaseMetricRef.current = onPhaseMetric; });

  useEffect(() => {
    const terminal = new Set(["done", "complete", "failed", "killed"]);

    function openStream() {
      esRef.current?.close();
      const es = new EventSource(`/api/pi-ceo/api/sessions/${sid}/logs?after=${cursorRef.current}`);
      esRef.current = es;

      es.onmessage = (e) => {
        try {
          const line: LogLine = JSON.parse(e.data);
          if (line.type === "done") {
            setStreaming(false);
            es.close();
            return;
          }
          cursorRef.current = line.i + 1;
          // Surface phase_metric events to the parent card
          if (line.type === "phase_metric" && line.phase && line.duration_s !== undefined) {
            const mappedPhase = METRIC_PHASE_MAP[line.phase] ?? line.phase;
            onPhaseMetricRef.current(mappedPhase, {
              duration_s: line.duration_s,
              cost_usd: line.cost_usd ?? 0,
            });
          }
          setLines((prev) => [...prev, line]);
        } catch { /* ignore parse errors */ }
      };

      es.onerror = () => {
        es.close();
        if (!terminal.has(status)) {
          setTimeout(openStream, 2000);
        } else {
          setStreaming(false);
        }
      };
    }

    openStream();
    return () => esRef.current?.close();
  }, [sid, status]); // eslint-disable-line react-hooks/exhaustive-deps

  // Auto-scroll
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [lines]);

  return (
    <div
      className="font-mono text-xs overflow-y-auto"
      style={{
        background: "#0c0c0c",
        borderTop: "1px solid var(--border)",
        maxHeight: "240px",
        padding: "8px 12px",
      }}
    >
      {lines.length === 0 && streaming && (
        <span style={{ color: "var(--text-dim)" }}>Connecting…</span>
      )}
      {lines.map((l, idx) => (
        <div key={idx} style={{ color: LINE_COLOR[l.type] ?? "var(--text-dim)", lineHeight: "1.5" }}>
          {l.text}
        </div>
      ))}
      {!streaming && lines.length > 0 && (
        <div style={{ color: "var(--text-dim)", marginTop: "4px" }}>— stream closed —</div>
      )}
      <div ref={bottomRef} />
    </div>
  );
}

function ResumeButton({ s, onResumed }: { s: PiSession; onResumed: () => void }) {
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function resume() {
    setLoading(true);
    setErr(null);
    try {
      const res = await fetch(`/api/pi-ceo/api/sessions/${s.id}/resume`, { method: "POST" });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        setErr(body.detail ?? `HTTP ${res.status}`);
      } else {
        onResumed();
      }
    } catch (e) {
      setErr(String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex items-center gap-2 flex-wrap">
      <button
        onClick={(e) => { e.stopPropagation(); void resume(); }}
        disabled={loading}
        className="font-mono text-[10px] px-2 min-h-[36px] rounded transition-opacity hover:opacity-70 disabled:opacity-40"
        style={{ border: "1px solid var(--accent)", color: "var(--accent)", background: "transparent" }}
      >
        {loading ? "…" : `RESUME from ${s.last_phase || "start"}`}
      </button>
      {err && <span className="font-mono text-[10px]" style={{ color: "#F87171" }}>{err}</span>}
    </div>
  );
}

function SessionCard({ s, isChild, onRefresh }: { s: PiSession; isChild?: boolean; onRefresh: () => void }) {
  const [expanded, setExpanded] = useState(false);
  const [phaseMetrics, setPhaseMetrics] = useState<Record<string, PhaseMetric>>({});
  const isActive = ["cloning", "building", "evaluating"].includes(s.status);

  const handlePhaseMetric = useCallback((phase: string, metric: PhaseMetric) => {
    setPhaseMetrics((prev) => ({ ...prev, [phase]: metric }));
  }, []);

  return (
    <div
      style={{
        borderBottom: "1px solid var(--border)",
        borderLeft: isChild ? "2px solid var(--border)" : "none",
        marginLeft: isChild ? "12px" : 0,
      }}
    >
      {/* Card header — clickable to expand */}
      <div
        className="px-3 sm:px-4 py-3 cursor-pointer transition-colors"
        style={{ background: "transparent" }}
        onMouseEnter={(e) => (e.currentTarget.style.background = "var(--panel-hover)")}
        onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
        onClick={() => setExpanded((v) => !v)}
      >
        {/* Top row: repo name + status/chevron */}
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-mono text-xs sm:text-[11px] break-all" style={{ color: "var(--text)" }}>
                {repoName(s.repo)}
              </span>
              {isChild && (
                <span className="font-mono text-[10px]" style={{ color: "var(--text-dim)" }}>[child]</span>
              )}
              {isActive && (
                <span className="font-mono text-[10px] px-1 rounded" style={{ background: "var(--panel)", color: "var(--accent)" }}>
                  LIVE
                </span>
              )}
            </div>
            <PhaseBar lastPhase={s.last_phase} status={s.status} phaseMetrics={phaseMetrics} />
          </div>

          <div className="flex items-center gap-2 shrink-0">
            {s.retry_count > 0 && (
              <span className="font-mono text-[10px] px-1 py-0.5 rounded hidden sm:inline" style={{ background: "var(--panel)", color: "#FFD166" }}>
                {s.retry_count}x
              </span>
            )}
            <ScoreBadge score={s.evaluator_score} evalStatus={s.evaluator_status} />
            <span className="font-mono text-[10px] uppercase" style={{ color: STATUS_COLOR[s.status] ?? "var(--text-dim)" }}>
              {s.status}
            </span>
            <span className="font-mono text-[10px]" style={{ color: "var(--text-dim)" }}>
              {expanded ? "▲" : "▼"}
            </span>
          </div>
        </div>

        {/* Meta row */}
        <div className="flex items-center gap-3 mt-1.5 flex-wrap">
          <span className="font-mono text-[10px]" style={{ color: "var(--text-dim)" }}>
            {elapsed(s.started)} ago
          </span>
          <span className="font-mono text-[10px] hidden sm:inline" style={{ color: "var(--text-dim)" }}>
            {s.lines} lines
          </span>
          {s.last_phase && (
            <span className="font-mono text-[10px]" style={{ color: "var(--text-dim)" }}>
              {s.last_phase}
            </span>
          )}
          <span className="font-mono text-[9px] sm:hidden" style={{ color: "var(--text-dim)" }}>
            {s.id.slice(0, 8)}
          </span>
        </div>

        {/* Resume button (only when interrupted) */}
        {s.status === "interrupted" && (
          <div className="mt-2">
            <ResumeButton s={s} onResumed={() => { onRefresh(); setExpanded(true); }} />
          </div>
        )}
      </div>

      {/* Log panel */}
      {expanded && <LogPanel sid={s.id} status={s.status} onPhaseMetric={handlePhaseMetric} />}
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
    void fetchSessions();
    const t = setInterval(fetchSessions, 5000);
    return () => clearInterval(t);
  }, [fetchSessions]);

  const parents = sessions.filter((s) => !s.parent);
  const childrenOf = (pid: string) => sessions.filter((s) => s.parent === pid);

  const activeCount = sessions.filter((s) =>
    ["cloning", "building", "evaluating"].includes(s.status)
  ).length;

  return (
    <div className="flex flex-col flex-1">
      {/* Header */}
      <div
        className="flex items-center justify-between px-3 sm:px-4 py-2 shrink-0 flex-wrap gap-2"
        style={{ borderBottom: "1px solid var(--border)" }}
      >
        <div className="flex items-center gap-3">
          <span className="font-mono text-xs uppercase tracking-widest" style={{ color: "var(--text-muted)" }}>
            Builds
            <span className="hidden sm:inline"> — {sessions.length} sessions</span>
            <span className="sm:hidden"> ({sessions.length})</span>
          </span>
          {activeCount > 0 && (
            <span className="font-mono text-[10px] px-2 py-0.5 rounded" style={{ background: "var(--panel)", color: "var(--accent)" }}>
              {activeCount} active
            </span>
          )}
        </div>
        <div className="flex items-center gap-3">
          {lastFetch > 0 && (
            <span className="font-mono text-[10px] hidden sm:inline" style={{ color: "var(--text-dim)" }}>
             {new Date(lastFetch).toLocaleTimeString()}
            </span>
          )}
          <button
            onClick={() => void fetchSessions()}
            className="font-mono text-[10px] px-3 min-h-[36px] transition-opacity hover:opacity-70"
            style={{ border: "1px solid var(--border)", color: "var(--text-muted)" }}
          >
            REFRESH
          </button>
        </div>
      </div>

      {/* Error state */}
      {error && (
        <div className="px-3 sm:px-4 py-3" style={{ borderBottom: "1px solid var(--border)" }}>
          <span className="font-mono text-xs" style={{ color: "#F87171" }}>
            {error.includes("unreachable") || error.includes("502")
              ? "Pi CEO server offline. Start with: cd app && uvicorn server.main:app --host 127.0.0.1 --port 7777"
              : error}
          </span>
          <div className="mt-1">
            <span className="font-mono text-[10px]" style={{ color: "var(--text-dim)" }}>
              Set PI_CEO_URL and PI_CEO_PASSWORD in dashboard .env.local
            </span>
          </div>
        </div>
      )}

      {/* Empty state */}
      {!error && sessions.length === 0 && (
        <div className="flex flex-col flex-1 items-center justify-center px-4 text-center">
          <p className="font-mono text-xs" style={{ color: "var(--text-muted)" }}>No build sessions yet.</p>
          <p className="font-mono text-[10px] mt-2" style={{ color: "var(--text-dim)" }}>
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
                <SessionCard s={s} onRefresh={fetchSessions} />
                {children.map((c) => (
                  <SessionCard key={c.id} s={c} isChild onRefresh={fetchSessions} />
                ))}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
