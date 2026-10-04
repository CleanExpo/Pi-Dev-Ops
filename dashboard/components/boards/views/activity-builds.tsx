"use client";
// RA-7898 — second views for Live activity (timeline, pulse) and Builds
// (table, big number).

import type { MissionControlLive } from "@/lib/control/mission-control-live";
import { useSource } from "@/lib/boards/sources";
import { ago, useNow } from "@/lib/boards/use-now";
import { runningCount } from "@/lib/boards/views/builds";
import { activityEvents, pulse } from "@/lib/boards/views/shapes";
import { useBuildRows } from "./builds";
import { Dot, Nothing, Unexpected } from "./charts";
import styles from "./views.module.css";

function useLive() {
  return useSource<MissionControlLive>("mc-live").value;
}

export function ActivityTimeline() {
  const events = activityEvents(useLive());
  const now = useNow(1_000);
  if (!events) return <Unexpected what="live activity" />;
  if (events.length === 0) return <Nothing text="Nothing running and nothing completed recently." />;
  return (
    <div className={styles.timeline}>
      {events.slice(0, 12).map((e) => (
        <div key={e.key} className={styles.event}>
          <Dot tone={e.tone} label={e.tone === "ok" ? "Completed" : "Running"} />
          <div>{e.text}</div>
          <div className={styles.meta}>{e.meta} · {ago(e.atMs, now)}</div>
        </div>
      ))}
    </div>
  );
}

export function ActivityPulse() {
  const p = pulse(useLive());
  if (!p) return <Unexpected what="live activity" />;
  const top = Math.max(1, ...p.hourly);
  return (
    <div className={styles.hero}>
      <span className={styles.big}>{p.total}</span>
      <span className={styles.sub}>completions in the last 24 hours</span>
      <div className={styles.ticks} role="img" aria-label="Completions per hour, last 24 hours">
        {p.hourly.map((n, i) => <i key={i} title={`${n} in hour ${i + 1}`} style={{ height: `${Math.max(6, (n / top) * 100)}%` }} />)}
      </div>
    </div>
  );
}

export function BuildsTable() {
  const rows = useBuildRows();
  const now = useNow(1_000);
  if (!rows) return <Unexpected what="sessions" />;
  if (rows.length === 0) return <Nothing text="No sessions reported." />;
  return (
    <div className={styles.scroll}>
      <table className={styles.table}>
        <thead><tr><th>Session</th><th>Repo</th><th>Stage</th><th>Started</th></tr></thead>
        <tbody>
          {rows.slice(0, 20).map((r) => (
            <tr key={r.id}>
              <td className={styles.mono}>{r.id.slice(0, 8)}</td>
              <td>{r.repo}</td>
              <td>{r.stage}{r.last_phase ? ` · ${r.last_phase}` : ""}</td>
              <td>{ago(Number.isNaN(r.startedMs) ? null : r.startedMs, now)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function BuildsNumber() {
  const rows = useBuildRows();
  if (!rows) return <Unexpected what="sessions" />;
  const stopped = rows.filter((r) => r.stage === "Stopped").length;
  return (
    <div className={styles.hero}>
      <span className={styles.big}>{runningCount(rows)}</span>
      <span className={styles.sub}>running now · {rows.length} reported{stopped ? ` · ${stopped} stopped` : ""}</span>
    </div>
  );
}
