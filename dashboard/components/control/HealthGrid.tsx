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

function healthColour(score: number | undefined): string {
  if (score === undefined) return "var(--text-dim)";
  if (score >= 80) return "#4ADE80";
  if (score >= 60) return "#FFD166";
  return "#F87171";
}

const SEVERITY_COLOUR: Record<Finding["severity"], string> = {
  critical: "#F87171",
  high:     "#FFA94D",
  medium:   "#FFD166",
  low:      "#A3A3A3",
  info:     "#71717A",
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
      } else {
        setFixResult(`❌ HTTP ${res.status} — ${body.slice(0, 120)}`);
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

        {/* Footer status */}
        {fixResult && (
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
      </div>
    </div>
  );
}
