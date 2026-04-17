// components/control/HealthGrid.tsx — Panel 3: Pi-SEO portfolio health tiles + sparklines (RA-1092)
// RA-1100: drill-down modal with finding detail + "Fix with Claude" build trigger.
"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Sparkline from "./Sparkline";

interface ProjectHealth {
  project_id: string;
  repo: string;
  overall_health: number;
  scores: Record<string, number>;
  findings_count: Record<string, number>;
  deployments: Record<string, string>;
}

interface Finding {
  scan_type: string;
  severity: "critical" | "high" | "medium" | "low" | "info";
  title: string;
  description: string;
  file_path: string;
  line_number: number | null;
  auto_fixable: boolean;
}

interface FindingsResponse {
  project_id: string;
  scans: Array<{ scan_type: string; finished_at?: string; finding_count?: number; error?: string }>;
  findings: Finding[];
  total_findings: number;
  truncated: boolean;
  error?: string;
}

// Use theme-aware CSS vars so contrast stays WCAG-AA on both platinum
// (light) and zinc (dark). Globals define darker values on light theme
// (--success:#16a34a, --warning:#ca8a04, --error:#dc2626) and brighter
// ones on dark (--success:#22c55e, --warning:#eab308, --error:#ef4444).
function healthColour(score: number | undefined): string {
  if (score === undefined) return "var(--text-dim)";
  if (score >= 80) return "var(--success)";
  if (score >= 60) return "var(--warning)";
  return "var(--error)";
}

const SEVERITY_COLOUR: Record<Finding["severity"], string> = {
  critical: "var(--error)",
  high:     "var(--accent)",   // amber — distinct from error + theme-aware
  medium:   "var(--warning)",
  low:      "var(--text-muted)",
  info:     "var(--text-dim)",
};

// Empty state with terminal aesthetic
function EmptyState({ message }: { message: string }) {
  return (
    <div className="flex flex-col items-start gap-1 py-4 px-1 font-mono">
      <span className="text-[11px]" style={{ color: "var(--text-dim)" }}>
        <span style={{ color: "var(--accent)" }}>$ </span>
        pi-ceo health --portfolio
      </span>
      <span className="text-[11px]" style={{ color: "var(--text-muted)" }}>
        {message}
      </span>
      <span
        className="text-[10px] inline-block w-1.5 h-3 align-middle"
        style={{ background: "var(--text-dim)", animation: "pi-cursor-blink 1.1s step-end infinite" }}
        aria-hidden="true"
      />
    </div>
  );
}

export default function HealthGrid() {
  const [projects, setProjects] = useState<ProjectHealth[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<ProjectHealth | null>(null);

  // Rolling health history buffer: project_id → last 10 scores
  const historyRef = useRef<Map<string, number[]>>(new Map());

  const fetchHealth = useCallback(async () => {
    try {
      const res = await fetch("/api/pi-ceo/api/projects/health");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = (await res.json()) as ProjectHealth[];
      const arr = Array.isArray(data) ? data : [];

      // Append to rolling history (max 12 samples)
      arr.forEach((p) => {
        const prev = historyRef.current.get(p.project_id) ?? [];
        const next = [...prev, p.overall_health].slice(-12);
        historyRef.current.set(p.project_id, next);
      });

      setProjects(arr);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load project health");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchHealth();
    const t = setInterval(() => void fetchHealth(), 60_000);
    return () => clearInterval(t);
  }, [fetchHealth]);

  const avg = projects.length
    ? Math.round(projects.reduce((s, p) => s + p.overall_health, 0) / projects.length)
    : null;

  return (
    <section
      className="flex flex-col h-full"
      style={{ background: "var(--panel)", border: "1px solid var(--border)", borderRadius: 8 }}
      aria-label="Portfolio health"
    >
      <style>{`
        @keyframes pi-cursor-blink {
          0%, 100% { opacity: 1; }
          50%       { opacity: 0; }
        }
      `}</style>

      <header
        className="flex items-center justify-between px-4 py-2.5"
        style={{ borderBottom: "1px solid var(--border)" }}
      >
        <h2 className="text-xs font-semibold uppercase tracking-widest" style={{ color: "var(--text-muted)" }}>
          Portfolio Health
        </h2>
        {avg !== null && (
          <span
            className="text-[10px] font-mono px-2 py-0.5 rounded"
            style={{
              color: healthColour(avg),
              background: "var(--panel-hover)",
              border: `1px solid ${healthColour(avg)}33`,
            }}
          >
            avg {avg}/100
          </span>
        )}
      </header>

      <div className="flex-1 overflow-auto p-4">
        {loading && (
          <p className="text-xs" style={{ color: "var(--text-dim)" }}>
            Loading…
          </p>
        )}

        {error && !loading && (
          <p className="text-xs font-mono" style={{ color: "var(--error)" }}>
            <span aria-hidden="true">⚠ </span>{error}
          </p>
        )}

        {!loading && !error && projects.length === 0 && (
          <EmptyState message="No projects registered." />
        )}

        {!loading && !error && projects.length > 0 && (
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
            {projects.map((p) => {
              const history = historyRef.current.get(p.project_id) ?? [p.overall_health];
              return (
                <button
                  key={p.project_id}
                  onClick={() => setSelected(p)}
                  className="text-left p-2.5 rounded transition-colors"
                  style={{
                    background: "var(--panel-hover)",
                    border: "1px solid var(--border)",
                  }}
                  onMouseEnter={(e) => {
                    (e.currentTarget as HTMLButtonElement).style.borderColor = `${healthColour(p.overall_health)}66`;
                  }}
                  onMouseLeave={(e) => {
                    (e.currentTarget as HTMLButtonElement).style.borderColor = "var(--border)";
                  }}
                  aria-label={`${p.project_id} health ${p.overall_health} out of 100`}
                >
                  <div className="flex items-center gap-1.5 mb-1">
                    <span
                      className="w-1.5 h-1.5 rounded-full shrink-0"
                      style={{ background: healthColour(p.overall_health) }}
                      aria-hidden="true"
                    />
                    <span className="text-[11px] font-medium truncate flex-1" style={{ color: "var(--text)" }}>
                      {p.project_id}
                    </span>
                  </div>
                  <div className="flex items-end justify-between">
                    <div className="font-mono text-sm leading-none" style={{ color: healthColour(p.overall_health) }}>
                      {p.overall_health}
                      <span className="text-[10px]" style={{ color: "var(--text-dim)" }}>
                        /100
                      </span>
                    </div>
                    <Sparkline
                      data={history}
                      colour={healthColour(p.overall_health)}
                    />
                  </div>
                </button>
              );
            })}
          </div>
        )}
      </div>

      {/* RA-1100 drill-down modal */}
      {selected && <ProjectDrillDown project={selected} onClose={() => setSelected(null)} />}
    </section>
  );
}

// ─── Drill-down modal — RA-1100 ───────────────────────────────────────────
function ProjectDrillDown({
  project,
  onClose,
}: {
  project: ProjectHealth;
  onClose: () => void;
}) {
  const [data, setData] = useState<FindingsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [fixing, setFixing] = useState<string | null>(null); // finding title being fixed
  const [fixResult, setFixResult] = useState<string | null>(null);
  // RA-1108: track the active session so we can stream its live output inline,
  // turning "fire-and-forget silence" into "watch it work live".
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [activeFindingTitle, setActiveFindingTitle] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch(`/api/pi-ceo/api/projects/${encodeURIComponent(project.project_id)}/findings?limit=25`)
      .then((r) => r.ok ? r.json() : Promise.reject(`HTTP ${r.status}`))
      .then((d: FindingsResponse) => { if (!cancelled) { setData(d); setError(null); } })
      .catch((e) => { if (!cancelled) setError(String(e)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [project.project_id]);

  async function fixWithClaude(finding: Finding) {
    setFixing(finding.title);
    setFixResult(null);
    try {
      const brief = [
        `Fix this ${finding.severity}-severity ${finding.scan_type} finding:`,
        ``,
        `**${finding.title}**`,
        finding.description,
        finding.file_path ? `\nFile: ${finding.file_path}${finding.line_number ? `:${finding.line_number}` : ""}` : "",
        ``,
        `Auto-fixable: ${finding.auto_fixable ? "yes" : "no — please diagnose carefully before fixing"}`,
      ].filter(Boolean).join("\n");
      const res = await fetch("/api/pi-ceo/api/build", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          repo_url: project.repo.startsWith("http") ? project.repo : `https://github.com/${project.repo}`,
          brief,
          intent: "fix",
        }),
      });
      const body = await res.text();
      if (res.ok) {
        const j = JSON.parse(body) as { id?: string; session_id?: string };
        const sid = j.id ?? j.session_id ?? "unknown";
        setFixResult(`✅ Build session ${sid.slice(0, 12)} started`);
        // RA-1108: open inline live-log streamer so the user SEES it running
        if (sid !== "unknown") {
          setActiveSessionId(sid);
          setActiveFindingTitle(finding.title);
        }
      } else {
        setFixResult(`❌ HTTP ${res.status} — ${body.slice(0, 200)}`);
      }
    } catch (e) {
      setFixResult(`❌ ${String(e)}`);
    } finally {
      setFixing(null);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: "rgba(0,0,0,0.7)" }}
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label={`${project.project_id} health details`}
    >
      <div
        className="w-full max-w-2xl max-h-[85vh] overflow-hidden rounded-lg flex flex-col"
        style={{ background: "var(--panel)", border: "1px solid var(--border)" }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <header
          className="flex items-start justify-between gap-3 p-5 shrink-0"
          style={{ borderBottom: "1px solid var(--border)" }}
        >
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 mb-1">
              <span
                className="w-2 h-2 rounded-full shrink-0"
                style={{ background: healthColour(project.overall_health) }}
                aria-hidden="true"
              />
              <h3 className="text-sm font-semibold truncate" style={{ color: "var(--text)" }}>
                {project.project_id}
              </h3>
              <span className="text-base font-mono ml-auto" style={{ color: healthColour(project.overall_health) }}>
                {project.overall_health}<span className="text-[10px]" style={{ color: "var(--text-dim)" }}>/100</span>
              </span>
            </div>
            <p className="text-[11px] font-mono truncate" style={{ color: "var(--text-dim)" }}>
              {project.repo}
            </p>
            {/* Per-scan-type score row */}
            <div className="flex flex-wrap gap-x-3 gap-y-1 mt-2">
              {Object.entries(project.scores).map(([k, v]) => (
                <span key={k} className="text-[10px] font-mono">
                  <span style={{ color: "var(--text-dim)" }}>{k}: </span>
                  <span style={{ color: healthColour(v) }}>{v}</span>
                </span>
              ))}
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-sm shrink-0 -mt-1 -mr-1 px-2 py-1 hover:opacity-70"
            style={{ color: "var(--text-muted)" }}
            aria-label="Close"
          >
            ✕
          </button>
        </header>

        {/* Findings body — scrollable */}
        <div className="flex-1 overflow-y-auto p-4">
          {loading && (
            <p className="text-xs" style={{ color: "var(--text-dim)" }}>Loading findings…</p>
          )}
          {error && (
            <p className="text-xs font-mono" style={{ color: "var(--error)" }}>
              <span aria-hidden="true">⚠ </span>{error}
            </p>
          )}
          {data && data.findings.length === 0 && !loading && (
            <p className="text-xs" style={{ color: "var(--text-dim)" }}>
              {data.error ?? "No findings — this project is clean. 🎉"}
            </p>
          )}
          {data && data.findings.length > 0 && (
            <>
              <div className="text-[10px] font-mono mb-2" style={{ color: "var(--text-dim)" }}>
                {data.total_findings} finding{data.total_findings === 1 ? "" : "s"}
                {data.truncated && ` (showing top ${data.findings.length})`}
                {" · "}sorted by severity
              </div>
              <ul className="space-y-2">
                {data.findings.map((f, i) => (
                  <li
                    key={`${f.scan_type}-${f.title}-${i}`}
                    className="rounded p-2.5"
                    style={{
                      background: "var(--panel-hover)",
                      border: `1px solid ${SEVERITY_COLOUR[f.severity]}33`,
                    }}
                  >
                    <div className="flex items-start gap-2 mb-1">
                      <span
                        className="text-[9px] font-mono uppercase px-1.5 py-0.5 rounded shrink-0"
                        style={{
                          color: SEVERITY_COLOUR[f.severity],
                          background: `${SEVERITY_COLOUR[f.severity]}1A`,
                        }}
                      >
                        {f.severity}
                      </span>
                      <span className="text-[10px] font-mono" style={{ color: "var(--text-muted)" }}>
                        {f.scan_type}
                      </span>
                      {f.auto_fixable && (
                        <span
                          className="text-[9px] font-mono ml-auto shrink-0"
                          style={{ color: "var(--success)" }}
                          title="Auto-fixable per scanner classification"
                        >
                          auto-fixable
                        </span>
                      )}
                    </div>
                    <div className="text-[12px] mb-1" style={{ color: "var(--text)" }}>
                      {f.title}
                    </div>
                    {f.description && (
                      <p className="text-[10px] mb-1.5" style={{ color: "var(--text-dim)" }}>
                        {f.description}
                      </p>
                    )}
                    {f.file_path && (
                      <p className="text-[10px] font-mono mb-1.5" style={{ color: "var(--text-muted)" }}>
                        {f.file_path}{f.line_number ? `:${f.line_number}` : ""}
                      </p>
                    )}
                    <button
                      onClick={() => void fixWithClaude(f)}
                      disabled={fixing !== null}
                      className="text-[10px] font-mono px-2 py-1 rounded disabled:opacity-50"
                      style={{
                        background: "var(--accent)",
                        color: "#fff",
                      }}
                    >
                      {fixing === f.title ? "Spawning…" : "▶ Fix with Claude"}
                    </button>
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>

        {/* Footer status — error case only. Success shows the live streamer below. */}
        {fixResult && !activeSessionId && (
          <div
            className="px-4 py-2 text-[11px] font-mono shrink-0"
            style={{
              borderTop: "1px solid var(--border)",
              color: fixResult.startsWith("✅") ? "var(--success)" : "var(--error)",
            }}
          >
            {fixResult}
          </div>
        )}

        {/* RA-1108 live session streamer — shows output from /api/sessions/{sid}/logs */}
        {activeSessionId && (
          <FixSessionLive
            sessionId={activeSessionId}
            findingTitle={activeFindingTitle ?? ""}
            onClose={() => {
              setActiveSessionId(null);
              setActiveFindingTitle(null);
            }}
            onFixNext={(() => {
              // RA-1181 — pick the next unfixed finding (by position after the
              // one currently in the streamer) and kick off a new session.
              if (!data) return undefined;
              const idx = data.findings.findIndex((x) => x.title === activeFindingTitle);
              const next = idx >= 0 ? data.findings.slice(idx + 1).find(Boolean) : data.findings[0];
              if (!next) return undefined;
              return () => {
                setActiveSessionId(null);
                setActiveFindingTitle(null);
                // Defer one tick so the unmount completes, then spawn next
                setTimeout(() => { void fixWithClaude(next); }, 100);
              };
            })()}
          />
        )}
      </div>
    </div>
  );
}

// ─── RA-1108 Live session streamer ────────────────────────────────────────
// Opens an SSE connection to /api/pi-ceo/api/sessions/{sid}/logs and prints
// each event as it arrives. Status chip at top shows building / done / error.
// This is what makes "Fix with Claude" feel like it's actually doing something.
interface SessionEvent {
  i?: number;
  type?: string;
  text?: string;
  reason?: string;
}

// RA-1181 — Poll-backed completion detection. SSE drops often on Vercel
// proxy (10 s AbortSignal) but the session keeps running server-side.
// Rather than flipping to "error" on drop, poll /api/sessions for the
// session's actual status and update accordingly.
interface PollSession {
  id: string;
  status: string;
  last_phase?: string;
  evaluator_score?: number | null;
  files_modified?: number;
}

function FixSessionLive({
  sessionId,
  findingTitle,
  onClose,
  onFixNext,
}: {
  sessionId: string;
  findingTitle: string;
  onClose: () => void;
  onFixNext?: () => void;
}) {
  const [events, setEvents] = useState<SessionEvent[]>([]);
  const [status, setStatus] = useState<
    "connecting" | "running" | "done" | "error" | "reconnecting"
  >("connecting");
  const [err, setErr] = useState<string | null>(null);
  const [pollState, setPollState] = useState<PollSession | null>(null);
  const logRef = useRef<HTMLDivElement>(null);

  // SSE stream — best-effort, always-live
  useEffect(() => {
    const es = new EventSource(`/api/pi-ceo/api/sessions/${sessionId}/logs`);
    setStatus("running");

    es.onmessage = (e) => {
      try {
        const ev: SessionEvent = JSON.parse(e.data);
        // RA-1181 — detect true completion from text patterns the server
        // actually emits ("=== SESSION COMPLETE ===", phase=Summary).
        const text = (ev.text ?? "").toString();
        if (
          ev.type === "closed" ||
          ev.type === "done" ||
          /SESSION\s+COMPLETE/i.test(text)
        ) {
          setStatus("done");
          // keep events visible; don't close es here — server emits Summary events after
        }
        setEvents((prev) => [...prev, ev]);
      } catch {
        // Ignore JSON parse errors on keepalives
      }
    };

    es.onerror = () => {
      // RA-1181 — DO NOT flip to "error" on SSE drop. The session almost
      // always keeps running server-side (Vercel proxy has a 10 s timeout
      // but Railway is happy). Mark as "reconnecting" and let the poller
      // below surface the real status.
      setStatus((prev) => (prev === "done" ? "done" : "reconnecting"));
      es.close();
    };

    return () => es.close();
  }, [sessionId]);

  // RA-1181 — /api/sessions poller. Source of truth when SSE drops.
  useEffect(() => {
    let alive = true;
    async function poll() {
      try {
        const res = await fetch(`/api/pi-ceo/api/sessions`, { cache: "no-store" });
        if (!res.ok) return;
        const data = (await res.json()) as PollSession[];
        if (!alive) return;
        const mine = data.find((s) => s.id === sessionId);
        if (mine) {
          setPollState(mine);
          if (mine.status === "complete") setStatus("done");
          else if (mine.status === "failed" || mine.status === "killed") {
            setStatus("error");
            setErr(`Session ended: ${mine.status}`);
          }
        }
      } catch {
        // Ignore transient errors
      }
    }
    void poll();
    const id = setInterval(poll, 4000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [sessionId]);

  // Auto-scroll to bottom on new events
  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [events]);

  const statusColour: Record<typeof status, string> = {
    connecting:   "var(--text-dim)",
    running:      "var(--accent)",
    reconnecting: "var(--warning)",
    done:         "var(--success)",
    error:        "var(--error)",
  };
  const statusLabel: Record<typeof status, string> = {
    connecting:   "connecting…",
    running:      "● running",
    reconnecting: "◌ reconnecting (backend still running)",
    done:         "✓ Complete",
    error:        "⚠ session ended with error",
  };

  return (
    <div
      className="shrink-0 flex flex-col"
      style={{
        borderTop: `2px solid var(--accent)`,
        background: "var(--panel)",
        maxHeight: "35vh",
      }}
    >
      {/* Header */}
      <div
        className="flex items-center justify-between px-4 py-2 shrink-0"
        style={{ borderBottom: "1px solid var(--border)", background: "var(--panel-hover)" }}
      >
        <div className="flex items-center gap-2 min-w-0">
          <span
            className="text-[10px] font-mono font-semibold"
            style={{ color: statusColour[status] }}
          >
            {statusLabel[status]}
          </span>
          <span className="text-[10px] font-mono truncate" style={{ color: "var(--text-dim)" }}>
            · sid <span style={{ color: "var(--text)" }}>{sessionId.slice(0, 12)}</span>
          </span>
          <span className="hidden sm:inline text-[10px] truncate" style={{ color: "var(--text-muted)" }}>
            · {findingTitle.slice(0, 60)}
          </span>
        </div>
        <button
          onClick={onClose}
          className="text-[10px] font-mono px-2 py-0.5 rounded hover:opacity-70"
          style={{ color: "var(--text-muted)", background: "var(--border)" }}
        >
          close
        </button>
      </div>

      {/* RA-1181 — Success banner on completion. Shown ABOVE the log so
          the user gets an immediate clear signal + action path. */}
      {status === "done" && (
        <div
          className="flex items-center justify-between px-4 py-3 shrink-0 gap-3"
          style={{
            background: "rgba(21, 128, 61, 0.08)",
            borderBottom: "1px solid var(--success)",
          }}
        >
          <div className="flex items-center gap-3 min-w-0">
            <span style={{ fontSize: 20, lineHeight: 1 }} aria-hidden="true">✅</span>
            <div className="min-w-0">
              <div
                className="text-[12px] font-semibold font-mono"
                style={{ color: "var(--success)" }}
              >
                Complete
              </div>
              <div
                className="text-[10px] font-mono truncate"
                style={{ color: "var(--text-muted)" }}
              >
                {pollState?.evaluator_score != null && (
                  <>score {pollState.evaluator_score.toFixed(1)}/10 · </>
                )}
                {pollState?.files_modified != null && pollState.files_modified > 0 && (
                  <>{pollState.files_modified} file{pollState.files_modified > 1 ? "s" : ""} modified · </>
                )}
                branch <span style={{ color: "var(--text)" }}>pidev/auto-{sessionId.slice(0, 8)}</span>
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {onFixNext && (
              <button
                onClick={onFixNext}
                className="text-[11px] font-mono font-semibold px-3 py-1.5 rounded transition-opacity hover:opacity-90"
                style={{ background: "var(--accent)", color: "#fff" }}
              >
                Fix next ↗
              </button>
            )}
            <button
              onClick={onClose}
              className="text-[11px] font-mono px-3 py-1.5 rounded"
              style={{
                background: "var(--panel-hover)",
                color: "var(--text-muted)",
                border: "1px solid var(--border)",
              }}
            >
              Done
            </button>
          </div>
        </div>
      )}

      {/* Live log */}
      <div
        ref={logRef}
        className="flex-1 overflow-y-auto p-3 font-mono text-[10px] leading-tight"
        style={{ background: "var(--background)", minHeight: 120 }}
      >
        {events.length === 0 && (
          <span style={{ color: "var(--text-dim)" }}>
            Waiting for session output…
          </span>
        )}
        {events.map((ev, i) => (
          <div key={i} style={{ color: eventColour(ev.type) }}>
            <span style={{ color: "var(--text-dim)" }}>[{ev.type ?? "?"}]</span>{" "}
            {(ev.text ?? "").toString()}
          </div>
        ))}
        {status === "reconnecting" && (
          <div style={{ color: "var(--warning)" }} className="mt-2">
            ◌ SSE stream closed — polling for session status. Build continues on server.
          </div>
        )}
        {err && status === "error" && (
          <div style={{ color: "var(--error)" }} className="mt-2">
            ⚠ {err}
          </div>
        )}
      </div>
    </div>
  );
}

function eventColour(type: string | undefined): string {
  switch (type) {
    case "error":   return "var(--error)";
    case "success": return "var(--success)";
    case "phase":   return "var(--accent)";
    case "tool":    return "var(--text-muted)";
    case "system":  return "var(--text-dim)";
    default:        return "var(--text)";
  }
}
