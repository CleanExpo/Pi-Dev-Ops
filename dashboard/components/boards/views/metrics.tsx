"use client";
// RA-7898 — second views for Model routing (bars, ring, table) and Business
// health (bars, heat, leaderboard).

import { useSource, type FabricStatus } from "@/lib/boards/sources";
import { fabricLanes, fabricTotals, scoredProjects, WEAK_SCORE } from "@/lib/boards/views/shapes";
import { Bars, Nothing, Ring, Unexpected } from "./charts";
import styles from "./views.module.css";

function useFabric() {
  return useSource<FabricStatus>("model-fabric").value;
}

export function ModelBars() {
  const totals = fabricTotals(useFabric());
  if (!totals) return <Unexpected what="model fabric" />;
  return <Bars bars={totals.map((t) => ({ ...t, tone: t.label === "Failures" && t.value > 0 ? "bad" as const : undefined }))} />;
}

export function ModelRing() {
  const totals = fabricTotals(useFabric());
  if (!totals) return <Unexpected what="model fabric" />;
  const calls = totals[0].value, failures = totals[1].value;
  const ok = Math.max(0, calls - failures);
  return (
    <Ring center={calls === 0 ? "—" : `${Math.round((ok / calls) * 100)}%`} sub="calls succeeded"
      slices={[{ label: "Succeeded", value: ok, color: "var(--board-accent)" }, { label: "Failed", value: failures, color: "var(--board-bad)" }]} />
  );
}

export function ModelTable() {
  const lanes = fabricLanes(useFabric());
  if (!lanes) return <Unexpected what="model fabric" />;
  if (lanes.length === 0) return <Nothing text="The fabric reports no lanes." />;
  return (
    <div className={styles.scroll}>
      <table className={styles.table}>
        <thead><tr><th>Lane</th><th>Model</th><th>Allowed</th></tr></thead>
        <tbody>
          {lanes.map((l) => (
            <tr key={l.lane}><td>{l.lane}</td><td>{l.model}</td><td>{l.banned ? "Banned" : "Yes"}</td></tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function useProjects() {
  return scoredProjects(useSource<unknown>("projects-health").value);
}

export function PortfolioBars() {
  const projects = useProjects();
  if (!projects) return <Unexpected what="project health" />;
  const scored = projects.filter((p) => p.score !== null);
  if (scored.length === 0) return <Nothing text="No project has a measured scan score yet." />;
  return <Bars max={100} bars={scored.map((p) => ({ label: p.id, value: p.score!, tone: p.score! < WEAK_SCORE ? "bad" as const : undefined }))} />;
}

export function PortfolioHeat() {
  const projects = useProjects();
  if (!projects) return <Unexpected what="project health" />;
  if (projects.length === 0) return <Nothing text="No projects returned." />;
  return (
    <div className={styles.heat}>
      {projects.map((p) => (
        <div key={p.id} className={styles.cell} data-weak={p.score !== null && p.score < WEAK_SCORE}
          title={p.score === null ? `${p.id}: no scan evidence` : `${p.id}: ${p.score}/100`}>
          <span className={styles.truncate}>{p.id}</span>
          <span className={styles.cellScore}>{p.score ?? "—"}</span>
          <span className={styles.meta}>{p.score === null ? "no scan yet" : p.score < WEAK_SCORE ? "needs attention" : "scan score"}</span>
        </div>
      ))}
    </div>
  );
}

export function PortfolioLeaderboard() {
  const projects = useProjects();
  if (!projects) return <Unexpected what="project health" />;
  if (projects.length === 0) return <Nothing text="No projects returned." />;
  return (
    <div className={styles.rows}>
      {projects.map((p, i) => (
        <div key={p.id} className={styles.row}>
          <span className={styles.meta}>{p.score === null ? "–" : i + 1}</span>
          <span className={styles.truncate}>{p.id}</span>
          <b>{p.score === null ? "no scan" : p.score}</b>
        </div>
      ))}
    </div>
  );
}
