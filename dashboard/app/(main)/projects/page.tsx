"use client";
// app/(main)/projects/page.tsx — Pi-SEO project health dashboard (RA-538)
// Shows health scores for all 10 registered projects from /api/projects/health

import { useEffect, useState, useCallback } from "react";

interface ProjectHealth {
  project_id: string;
  repo: string;
  overall_health: number;
  scores: Record<string, number>;
  findings_count: Record<string, number>;
  deployments: Record<string, string>;
}

const SCAN_TYPES = ["security", "code_quality", "dependencies", "deployment_health"] as const;
const SCAN_LABELS: Record<string, string> = {
  security: "Security",
  code_quality: "Code Quality",
  dependencies: "Dependencies",
  deployment_health: "Deployment",
};

function healthColor(score: number | undefined): string {
  if (score === undefined) return "#888480";
  if (score >= 80) return "#4ADE80";
  if (score >= 60) return "#FFD166";
  return "#F87171";
}

function healthIndicator(score: number | undefined): string {
  if (score === undefined) return "—";
  if (score >= 80) return "●";
  if (score >= 60) return "●";
  return "●";
}

function ScoreBar({ score }: { score: number | undefined }) {
  if (score === undefined) return <span style={{ color: "var(--text-muted)", fontFamily: "monospace" }}>not scanned</span>;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
      <div style={{ width: 60, height: 4, background: "var(--border)", borderRadius: 2, overflow: "hidden" }}>
        <div style={{ width: `${score}%`, height: "100%", background: healthColor(score), transition: "width 0.3s" }} />
      </div>
      <span style={{ color: healthColor(score), fontFamily: "monospace", fontSize: 11 }}>{score}</span>
    </div>
  );
}

export default function ProjectsPage() {
  const [projects, setProjects] = useState<ProjectHealth[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [scanning, setScanning] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const fetchHealth = useCallback(async () => {
    try {
      const res = await fetch("/api/pi-ceo/api/projects/health");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setProjects(data);
      setLastUpdated(new Date());
      setError("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load project health");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchHealth();
    const interval = setInterval(fetchHealth, 60_000);
    return () => clearInterval(interval);
  }, [fetchHealth]);

  async function triggerScan(projectId?: string) {
    setScanning(true);
    try {
      await fetch("/api/pi-ceo/api/scan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ project_id: projectId, dry_run: false }),
      });
      setTimeout(fetchHealth, 5000);
    } catch {
      // scan runs async, ignore errors here
    } finally {
      setTimeout(() => setScanning(false), 2000);
    }
  }

  const avgHealth = projects.length
    ? Math.round(projects.reduce((s, p) => s + p.overall_health, 0) / projects.length)
    : null;

  return (
    <div
      className="flex flex-col"
      style={{ height: "calc(100vh - 40px)", overflow: "auto", background: "var(--background)" }}
    >
      {/* ── Header ── */}
      <div
        className="flex items-center justify-between px-4 py-3 shrink-0"
        style={{ borderBottom: "1px solid var(--border)", background: "var(--panel)" }}
      >
        <div className="flex items-center gap-3">
          <span className="font-mono text-[11px] font-bold" style={{ color: "var(--accent)", letterSpacing: "0.1em" }}>
            PI-SEO
          </span>
          <span className="font-mono text-[11px]" style={{ color: "var(--text-muted)" }}>PROJECT HEALTH</span>
          {avgHealth !== null && (
            <span
              className="font-mono text-[11px] px-2 py-0.5"
              style={{ background: "var(--panel-hover)", color: healthColor(avgHealth), border: `1px solid ${healthColor(avgHealth)}33` }}
            >
              avg {avgHealth}/100
            </span>
          )}
        </div>
        <div className="flex items-center gap-3">
          {lastUpdated && (
            <span className="font-mono text-[10px]" style={{ color: "var(--text-dim)" }}>
              updated {lastUpdated.toLocaleTimeString()}
            </span>
          )}
          <button
            onClick={() => triggerScan()}
            disabled={scanning}
            className="font-mono text-[10px] px-3 py-1 disabled:opacity-40"
            style={{ background: "var(--panel-hover)", color: "var(--accent)", border: "1px solid var(--accent)44" }}
          >
            {scanning ? "SCANNING…" : "SCAN ALL"}
          </button>
          <button
            onClick={fetchHealth}
            className="font-mono text-[10px] px-3 py-1"
            style={{ background: "var(--panel-hover)", color: "var(--text-muted)", border: "1px solid var(--border)" }}
          >
            REFRESH
          </button>
        </div>
      </div>

      {error && (
        <div className="px-4 py-2 font-mono text-[11px]" style={{ background: "var(--panel)", color: "#F87171", borderBottom: "1px solid #F8717133" }}>
          ✗ {error}
        </div>
      )}

      {/* ── Table ── */}
      <div className="flex-1 overflow-auto">
        {loading ? (
          <div className="flex items-center justify-center h-32 font-mono text-[11px]" style={{ color: "var(--text-dim)" }}>
            loading…
          </div>
        ) : (
          <table className="w-full font-mono text-[11px]" style={{ borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ borderBottom: "1px solid var(--border)" }}>
                <th className="text-left px-4 py-2" style={{ color: "var(--text-dim)", fontWeight: 400 }}>PROJECT</th>
                <th className="text-left px-4 py-2" style={{ color: "var(--text-dim)", fontWeight: 400 }}>OVERALL</th>
                {SCAN_TYPES.map(st => (
                  <th key={st} className="text-left px-4 py-2" style={{ color: "var(--text-dim)", fontWeight: 400 }}>
                    {SCAN_LABELS[st].toUpperCase()}
                  </th>
                ))}
                <th className="text-left px-4 py-2" style={{ color: "var(--text-dim)", fontWeight: 400 }}>DEPLOYMENTS</th>
                <th className="px-4 py-2" />
              </tr>
            </thead>
            <tbody>
              {projects.map((proj, i) => (
                <tr
                  key={proj.project_id}
                  style={{
                    borderBottom: "1px solid var(--border-subtle)",
                    background: i % 2 === 0 ? "transparent" : "var(--panel)",
                  }}
                >
                  <td className="px-4 py-2.5">
                    <div style={{ color: "var(--text)" }}>{proj.project_id}</div>
                    <div style={{ color: "var(--text-dim)", fontSize: 10 }}>{proj.repo.split("/")[1]}</div>
                  </td>
                  <td className="px-4 py-2.5">
                    <div className="flex items-center gap-2">
                      <span style={{ color: healthColor(proj.overall_health), fontSize: 10 }}>
                        {healthIndicator(proj.overall_health)}
                      </span>
                      <span style={{ color: healthColor(proj.overall_health), fontWeight: 600 }}>
                        {proj.overall_health}/100
                      </span>
                    </div>
                  </td>
                  {SCAN_TYPES.map(st => (
                    <td key={st} className="px-4 py-2.5">
                      <ScoreBar score={proj.scores[st]} />
                      {proj.findings_count[st] !== undefined && (
                        <div style={{ color: "var(--text-dim)", fontSize: 10, marginTop: 2 }}>
                          {proj.findings_count[st]} finding{proj.findings_count[st] !== 1 ? "s" : ""}
                        </div>
                      )}
                    </td>
                  ))}
                  <td className="px-4 py-2.5">
                    {Object.entries(proj.deployments).map(([name, url]) => (
                      <div key={name} style={{ color: "#4ADE80", fontSize: 10 }}>
                        {name}: <span style={{ color: "var(--text-dim)" }}>{url.replace("https://", "")}</span>
                      </div>
                    ))}
                    {Object.keys(proj.deployments).length === 0 && (
                      <span style={{ color: "var(--text-dim)" }}>—</span>
                    )}
                  </td>
                  <td className="px-4 py-2.5">
                    <button
                      onClick={() => triggerScan(proj.project_id)}
                      disabled={scanning}
                      className="font-mono text-[10px] px-2 py-0.5 disabled:opacity-30"
                      style={{ background: "transparent", color: "var(--accent)", border: "1px solid var(--accent)44" }}
                    >
                      scan
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
