// components/control/HealthGrid.tsx — Panel 3: Pi-SEO portfolio health tiles (RA-1092)
"use client";

import { useCallback, useEffect, useState } from "react";

interface ProjectHealth {
  project_id: string;
  repo: string;
  overall_health: number;
  scores: Record<string, number>;
  findings_count: Record<string, number>;
  deployments: Record<string, string>;
}

function healthColour(score: number | undefined): string {
  if (score === undefined) return "var(--text-dim)";
  if (score >= 80) return "#4ADE80";
  if (score >= 60) return "#FFD166";
  return "#F87171";
}

export default function HealthGrid() {
  const [projects, setProjects] = useState<ProjectHealth[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<ProjectHealth | null>(null);

  const fetchHealth = useCallback(async () => {
    try {
      const res = await fetch("/api/pi-ceo/api/projects/health");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = (await res.json()) as ProjectHealth[];
      setProjects(Array.isArray(data) ? data : []);
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
          <p className="text-xs" style={{ color: "var(--error)" }}>
            {error}
          </p>
        )}

        {!loading && !error && projects.length === 0 && (
          <p className="text-xs" style={{ color: "var(--text-dim)" }}>
            No projects registered yet.
          </p>
        )}

        {!loading && !error && projects.length > 0 && (
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
            {projects.map((p) => (
              <button
                key={p.project_id}
                onClick={() => setSelected(p)}
                className="text-left p-2.5 rounded transition-colors hover:opacity-90"
                style={{
                  background: "var(--panel-hover)",
                  border: "1px solid var(--border)",
                }}
                aria-label={`${p.project_id} health ${p.overall_health} out of 100`}
              >
                <div className="flex items-center gap-1.5 mb-1">
                  <span
                    className="w-1.5 h-1.5 rounded-full shrink-0"
                    style={{ background: healthColour(p.overall_health) }}
                    aria-hidden="true"
                  />
                  <span className="text-[11px] font-medium truncate" style={{ color: "var(--text)" }}>
                    {p.project_id}
                  </span>
                </div>
                <div className="font-mono text-sm" style={{ color: healthColour(p.overall_health) }}>
                  {p.overall_health}
                  <span className="text-[10px]" style={{ color: "var(--text-dim)" }}>
                    /100
                  </span>
                </div>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Detail popover */}
      {selected && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4"
          style={{ background: "rgba(0,0,0,0.6)" }}
          onClick={() => setSelected(null)}
          role="dialog"
          aria-modal="true"
          aria-label={`${selected.project_id} health details`}
        >
          <div
            className="w-full max-w-md rounded-lg p-5 space-y-3"
            style={{ background: "var(--panel)", border: "1px solid var(--border)" }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <h3 className="text-sm font-semibold" style={{ color: "var(--text)" }}>
                  {selected.project_id}
                </h3>
                <p className="text-[11px] font-mono" style={{ color: "var(--text-dim)" }}>
                  {selected.repo}
                </p>
              </div>
              <button
                onClick={() => setSelected(null)}
                className="text-xs"
                style={{ color: "var(--text-muted)" }}
                aria-label="Close"
              >
                ✕
              </button>
            </div>

            <div
              className="flex items-center gap-2 pt-2"
              style={{ borderTop: "1px solid var(--border)" }}
            >
              <span
                className="w-2 h-2 rounded-full"
                style={{ background: healthColour(selected.overall_health) }}
                aria-hidden="true"
              />
              <span className="text-lg font-mono" style={{ color: healthColour(selected.overall_health) }}>
                {selected.overall_health}/100
              </span>
            </div>

            <div className="space-y-1.5">
              {Object.entries(selected.scores).map(([k, v]) => (
                <div key={k} className="flex items-center justify-between text-[11px] font-mono">
                  <span style={{ color: "var(--text-dim)" }}>{k}</span>
                  <span style={{ color: healthColour(v) }}>{v}/100</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
