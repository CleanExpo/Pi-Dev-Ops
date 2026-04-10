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
  if (score === undefined) return <span style={{ color: "#888480", fontFamily: "monospace" }}>not scanned</span>;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
      <div style={{ width: 60, height: 4, background: "#2A2727", borderRadius: 2, overflow: "hidden" }}>
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
      style={{ height: "calc(100vh - 40px)", overflow: "auto", background: "#0A0A0A" }}
    >
      {/* ── Header ── */}
      <div
        className="flex items-center justify-between px-4 py-3 shrink-0"
        style={{ borderBottom: "1px solid #2A2727", background: "#0D0D0D" }}
      >
        <div className="flex items-center gap-3">
          <span className="font-mono text-[11px] font-bold" style={{ color: "#E8751A", letterSpacing: "0.1em" }}>
            PI-SEO
          </span>
          <span className="font-mono text-[11px]" style={{ color: "#888480" }}>PROJECT HEALTH</span>
          {avgHealth !== null && (
            <span
              className="font-mono text-[11px] px-2 py-0.5"
              style={{ background: "#1A1A1A", color: healthColor(avgHealth), border: `1px solid ${healthColor(avgHealth)}33` }}
            >
              avg {avgHealth}/100
            </span>
          )}
        </div>
        <div className="flex items-center gap-3">
          {lastUpdated && (
            <span className="font-mono text-[10px]" style={{ color: "#555" }}>
              updated {lastUpdated.toLocaleTimeString()}
            </span>
          )}
          <button
            onClick={() => triggerScan()}
            disabled={scanning}
            className="font-mono text-[10px] px-3 py-1 disabled:opacity-40"
            style={{ background: scanning ? "#1A1A1A" : "#1A1A1A", color: "#E8751A", border: "1px solid #E8751A44" }}
          >
            {scanning ? "SCANNING…" : "SCAN ALL"}
          </button>
          <button
            onClick={fetchHealth}
            className="font-mono text-[10px] px-3 py-1"
            style={{ background: "#1A1A1A", color: "#888480", border: "1px solid #2A2727" }}
          >
            REFRESH
          </button>
        </div>
      </div>

      {error && (
        <div className="px-4 py-2 font-mono text-[11px]" style={{ background: "#1a0808", color: "#F87171", borderBottom: "1px solid #F8717133" }}>
          ✗ {error}
        </div>
      )}

      {/* ── Table ── */}
      <div className="flex-1 overflow-auto">
        {loading ? (
          <div className="flex items-center justify-center h-32 font-mono text-[11px]" style={{ color: "#555" }}>
            loading…
          </div>
        ) : (
          <table className="w-full font-mono text-[11px]" style={{ borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ borderBottom: "1px solid #2A2727" }}>
                <th className="text-left px-4 py-2" style={{ color: "#555", fontWeight: 400 }}>PROJECT</th>
                <th className="text-left px-4 py-2" style={{ color: "#555", fontWeight: 400 }}>OVERALL</th>
                {SCAN_TYPES.map(st => (
                  <th key={st} className="text-left px-4 py-2" style={{ color: "#555", fontWeight: 400 }}>
                    {SCAN_LABELS[st].toUpperCase()}
                  </th>
                ))}
                <th className="text-left px-4 py-2" style={{ color: "#555", fontWeight: 400 }}>DEPLOYMENTS</th>
                <th className="px-4 py-2" />
              </tr>
            </thead>
            <tbody>
              {projects.map((proj, i) => (
                <tr
                  key={proj.project_id}
                  style={{
                    borderBottom: "1px solid #1A1A1A",
                    background: i % 2 === 0 ? "transparent" : "#0D0D0D",
                  }}
                >
                  <td className="px-4 py-2.5">
                    <div style={{ color: "#F0EDE8" }}>{proj.project_id}</div>
                    <div style={{ color: "#555", fontSize: 10 }}>{proj.repo.split("/")[1]}</div>
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
                        <div style={{ color: "#555", fontSize: 10, marginTop: 2 }}>
                          {proj.findings_count[st]} finding{proj.findings_count[st] !== 1 ? "s" : ""}
                        </div>
                      )}
                    </td>
                  ))}
                  <td className="px-4 py-2.5">
                    {Object.entries(proj.deployments).map(([name, url]) => (
                      <div key={name} style={{ color: "#4ADE80", fontSize: 10 }}>
                        {name}: <span style={{ color: "#555" }}>{url.replace("https://", "")}</span>
                      </div>
                    ))}
                    {Object.keys(proj.deployments).length === 0 && (
                      <span style={{ color: "#333" }}>—</span>
                    )}
                  </td>
                  <td className="px-4 py-2.5">
                    <button
                      onClick={() => triggerScan(proj.project_id)}
                      disabled={scanning}
                      className="font-mono text-[10px] px-2 py-0.5 disabled:opacity-30"
                      style={{ background: "transparent", color: "#E8751A", border: "1px solid #E8751A44" }}
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
