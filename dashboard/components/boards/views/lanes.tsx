"use client";
// Claude lanes — one row per Claude Code session reporting through the mc-lane mod.

import type { LanesView } from "@/lib/control/mesh-lanes";
import { useSource } from "@/lib/boards/sources";
import { ago, useNow } from "@/lib/boards/use-now";
import { Dot, Nothing, Unexpected } from "./charts";
import styles from "./views.module.css";

/** A lane with no event in this long is shown as quiet, not working. */
const QUIET_AFTER_MS = 10 * 60_000;

function pct(v: number | null): string {
  return v === null ? "—" : `${Math.round(v)}%`;
}

export function LaneList() {
  const source = useSource<LanesView>("mesh-lanes");
  const now = useNow(1_000);
  const view = source.value ?? source.lastGood;
  if (!view || view.status !== "ok" || !Array.isArray(view.lanes)) return <Unexpected what="lanes" />;
  if (view.lanes.length === 0) {
    return <Nothing text="No lane has reported yet. Lanes report once the mc-lane mod is installed and configured on a machine." />;
  }
  return (
    <div className={styles.rows}>
      {view.lanes.map((lane) => {
        const heard = lane.lastAt ? Date.parse(lane.lastAt) : null;
        const quiet = heard === null || now - heard > QUIET_AFTER_MS;
        const tone = lane.ended ? "idle" : quiet ? "warn" : "ok";
        const label = lane.ended ? "Ended" : quiet ? "Quiet" : "Working";
        const cost = lane.costUsd === null ? "cost unknown" : `$${lane.costUsd.toFixed(2)}`;
        return (
          <div key={lane.sessionId} className={styles.row} title={`${lane.host} · ${lane.model ?? "model unknown"} · session ${lane.sessionId}`}>
            <Dot tone={tone} label={label} />
            <span className={styles.truncate}>
              {lane.host}{lane.repo ? ` · ${lane.repo}` : ""}{lane.lastTool ? ` · ${lane.lastTool}` : ""}
            </span>
            <span className={styles.meta}>
              ctx {pct(lane.ctxPct)} · limit {pct(lane.ratePct)} · {cost} · {lane.toolCalls} calls{lane.toolFails ? ` (${lane.toolFails} failed)` : ""}{lane.agents ? ` · ${lane.agents} ${lane.agents === 1 ? "agent" : "agents"}` : ""} · {ago(heard, now)}
            </span>
          </div>
        );
      })}
      <p className={styles.empty}>Counts cover the newest {view.windowEvents} events.</p>
    </div>
  );
}
