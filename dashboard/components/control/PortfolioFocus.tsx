"use client";

import { useState, type ReactNode } from "react";
import { useSource } from "@/lib/boards/sources";
import type { MissionControlLive, MCSession } from "@/lib/control/mission-control-live";
import { latestPipelineForRepo, PATHWAY, stageEvidence, type PipelineSummary } from "@/lib/control/project-pathway";
import FounderNorthStarReadout from "./FounderNorthStarReadout";
import styles from "./portfolio-focus.module.css";

interface ProjectHealth {
  project_id: string;
  repo: string;
  overall_health?: number;
  scores?: Record<string, number>;
}

export function observedScanScore(project: ProjectHealth): number | null {
  const scores = project.scores;
  return scores && Object.values(scores).some((value) => typeof value === "number" && Number.isFinite(value))
    && typeof project.overall_health === "number" && Number.isFinite(project.overall_health)
    ? project.overall_health : null;
}

function matchingSession(project: ProjectHealth, sessions: MCSession[]): MCSession | undefined {
  return sessions.find((session) => session.repo && session.repo.toLowerCase() === project.repo.toLowerCase());
}

export default function PortfolioFocus({ children }: { children?: ReactNode }) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  // RA-7898: three shared pollers — projects/health (30 s), mission-control/live
  // (5 s) and pipelines (30 s) — each shared with every other reader on screen.
  const projectSource = useSource<ProjectHealth[]>("projects-health");
  const liveSource = useSource<MissionControlLive>("mc-live");
  const pipelineSource = useSource<PipelineSummary[]>("pipelines");
  const loading = projectSource.seq === 0 || liveSource.seq === 0 || pipelineSource.seq === 0;
  const list = Array.isArray(projectSource.value)
    ? projectSource.value.filter((item) => item && typeof item.project_id === "string" && typeof item.repo === "string")
    : null;
  const projectError = list === null;
  const projects = list ?? [];
  const live = liveSource.value && !liveSource.value.error ? liveSource.value : null;
  const activityError = live === null;
  const pipelineList = Array.isArray(pipelineSource.value) ? pipelineSource.value : null;
  const pipelines = pipelineList ?? [];
  const pipelineError = pipelineList === null;

  const selected = projects.find((project) => project.project_id === selectedId) ?? projects[0];
  const session = selected && live ? matchingSession(selected, live.active_sessions ?? []) : undefined;
  const pipeline = selected ? latestPipelineForRepo(selected.repo, pipelines) : null;
  const score = selected ? observedScanScore(selected) : null;

  return (
    <section className={styles.surface} aria-label="Portfolio focus">
      <div className={styles.topline}>
        <span className={styles.brand}>π <span>PI DEV OPS / MISSION CONTROL</span></span>
        <span className={styles.viewLabel}>● &nbsp; Portfolio view</span>
      </div>
      <div className={styles.heading}>
        <div>
          <h2>Choose a project. See the work.</h2>
          <p>Scan health and observed work are shown separately. Release progress needs its own evidence.</p>
        </div>
        <span className={styles.truthMark}>EVIDENCE FIRST</span>
      </div>
      <FounderNorthStarReadout live={live} />

      {loading ? <p className={styles.notice} role="status">Loading portfolio…</p> : projectError ? (
        <p className={styles.notice} role="status">Portfolio source unavailable. Project status is unknown.</p>
      ) : projects.length === 0 ? (
        <p className={styles.notice}>No projects returned by the project health source.</p>
      ) : (
        <>
          <div className={styles.fan} role="group" aria-label="Select project">
            {projects.map((project, index) => {
              const raised = selected?.project_id === project.project_id;
              const active = live && matchingSession(project, live.active_sessions ?? []);
              const scanScore = observedScanScore(project);
              const activityLabel = activityError ? "activity unknown" : active ? "work observed" : "no active work observed";
              return (
                <button
                  data-mc-data="project"
                  type="button"
                  key={`${project.project_id}-${index}`}
                  className={`${styles.card} ${raised ? styles.raised : ""}`}
                  style={{ backgroundPosition: `${projects.length > 1 ? (index / (projects.length - 1)) * 100 : 50}% center` }}
                  onClick={() => setSelectedId(project.project_id)}
                  aria-pressed={raised}
                  aria-label={`${project.project_id}, ${activityLabel}`}
                >
                  <span className={styles.cardTop}><span>{String(index + 1).padStart(2, "0")}</span><span>{activityError ? "UNKNOWN" : active ? "WORKING" : "NO ACTIVE WORK"}</span></span>
                  <strong>{project.project_id}</strong>
                  <span className={styles.cardRepo}>{project.repo}</span>
                  <span className={styles.cardFoot}>SCAN HEALTH {scanScore === null ? "UNKNOWN" : `${scanScore}/100`}</span>
                </button>
              );
            })}
          </div>

          {selected && (
            <div className={styles.focus} aria-live="polite">
              <div className={styles.focusHead}>
                <div>
                  <p className={styles.eyebrow}>Selected project</p>
                  <h3>{selected.project_id}</h3>
                  <p className={styles.repo}>{selected.repo}</p>
                </div>
                <div className={styles.focusActions}>
                  <div className={styles.attention}>Needs Phill <strong>unknown</strong></div>
                  <div className={styles.metric}>
                    <span>SCAN HEALTH</span>
                    <strong>{score === null ? "Unknown" : `${score}/100`}</strong>
                    <small>{score === null ? "No scan evidence" : "Code scans · not release progress"}</small>
                  </div>
                </div>
              </div>

              <div className={styles.work}>
                <div>
                  <span className={styles.eyebrow}>Observed now</span>
                  {activityError ? <p>Activity source unavailable. Current work is unknown.</p>
                    : session ? <p><strong>{session.phase || session.status || "Session active"}</strong> · {session.issue_id || session.id}</p>
                    : <p>No active session observed for this repository.</p>}
                </div>
                <div>
                  <span className={styles.eyebrow}>Release evidence</span>
                  <p>{pipelineError ? "Pipeline source unavailable. Pathway status unknown."
                    : pipeline ? `Latest matched pipeline ${pipeline.pipeline_id} · next phase ${pipeline.current_phase}. Recorded phases are shown below; live deployment is unverified.`
                    : "Pathway status unknown. No pipeline matched to this repository."}</p>
                </div>
              </div>
              <div className={styles.path} aria-label="Idea to live pathway; statuses from the latest matched pipeline">
                {PATHWAY.map((stage, index) => {
                  const evidence = stageEvidence(stage.label, pipeline);
                  return <span key={stage.label} className={styles.stage}><i aria-hidden="true">{index + 1}</i>{stage.label}<small className={evidence === "unverified" ? undefined : styles.verified}>{evidence}</small></span>;
                })}
              </div>
            </div>
          )}
        </>
      )}
      {children}
    </section>
  );
}
