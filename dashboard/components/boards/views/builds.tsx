"use client";
// RA-7898 — Builds module views, from the shared `sessions` feed.

import { useSource } from "@/lib/boards/sources";
import { buildRows, STAGES, type BuildRow } from "@/lib/boards/views/builds";
import styles from "./views.module.css";

export function useBuildRows(): BuildRow[] | null {
  const source = useSource<unknown>("sessions");
  return buildRows(source.value);
}

export function BuildsBoard() {
  const rows = useBuildRows();
  if (!rows) return <p className={styles.empty}>The sessions source answered with something that is not a session list.</p>;
  if (rows.length === 0) return <p className={styles.empty}>No sessions reported.</p>;
  return (
    <div className={styles.lanes}>
      {STAGES.map((stage) => {
        const items = rows.filter((r) => r.stage === stage);
        return (
          <div key={stage} className={styles.lane}>
            <h4><span>{stage}</span><span>{items.length}</span></h4>
            {items.slice(0, 6).map((r) => (
              <div key={r.id} className={styles.ticket}>
                <span className={styles.mono}>{r.id.slice(0, 8)}{r.last_phase ? ` · ${r.last_phase}` : ""}</span>
                <span className={styles.truncate}>{r.repo}</span>
              </div>
            ))}
          </div>
        );
      })}
    </div>
  );
}
