"use client";
// RA-7898 — second views for Fleet (heartbeat strip, compact list) and Ship
// chain (station row, ring).

import type { FleetView } from "@/lib/control/mesh-fleet";
import { useSource } from "@/lib/boards/sources";
import { ago, useNow } from "@/lib/boards/use-now";
import { CHIP_TONE, fleetRows, stationCounts } from "@/lib/boards/views/shapes";
import { displayChip, isSnapshotStale } from "@/lib/wall/client";
import type { WallSnapshot } from "@/lib/wall/snapshot";
import { Dot, Nothing, Ring, Unexpected } from "./charts";
import styles from "./views.module.css";

/** A machine counts as fresh for five minutes after its heartbeat. */
const FRESH_WINDOW_MS = 5 * 60_000;

function useFleetRows() {
  return fleetRows(useSource<FleetView>("mesh-fleet").value);
}

export function FleetStrip() {
  const rows = useFleetRows();
  const now = useNow(1_000);
  if (!rows) return <Unexpected what="fleet" />;
  if (rows.length === 0) return <Nothing text="No machines enrolled." />;
  return (
    <div className={styles.bars}>
      {rows.map((m) => {
        const age = m.heardMs === null ? null : now - m.heardMs;
        const share = age === null ? 0 : Math.max(0, 1 - age / FRESH_WINDOW_MS);
        return (
          <div key={m.host} className={styles.bar} title={`${m.host}: heartbeat ${ago(m.heardMs, now)}`}>
            <span className={styles.truncate}>{m.host}</span>
            <div className={styles.track}><div className={styles.fill} data-tone={m.stale ? "bad" : undefined} style={{ width: `${share * 100}%` }} /></div>
            <span className={styles.value}>{m.stale ? "stale" : ago(m.heardMs, now).replace(" ago", "")}</span>
          </div>
        );
      })}
    </div>
  );
}

export function FleetList() {
  const rows = useFleetRows();
  const now = useNow(1_000);
  if (!rows) return <Unexpected what="fleet" />;
  if (rows.length === 0) return <Nothing text="No machines enrolled." />;
  return (
    <div className={styles.rows}>
      {rows.map((m) => (
        <div key={m.host} className={styles.row}>
          <Dot tone={m.stale ? "warn" : "ok"} label={m.stale ? "Stale" : "Fresh"} />
          <span className={styles.truncate}>{m.host}{m.claim ? ` · ${m.claim}` : ""}</span>
          <span className={styles.meta}>{m.stale ? "stale · " : ""}{ago(m.heardMs, now)}</span>
        </div>
      ))}
    </div>
  );
}

function useStations() {
  const source = useSource<WallSnapshot | null>("wall");
  const now = useNow(1_000);
  const snap = source.value ?? source.lastGood;
  if (!snap || !Array.isArray(snap.stations)) return null;
  const stale = isSnapshotStale(snap.generated_at, now);
  return snap.stations.map((s) => ({ ...s, chip: displayChip(s.chip, stale) }));
}

export function ChainRow() {
  const stations = useStations();
  if (!stations) return <Unexpected what="ship chain" />;
  return (
    <div className={styles.chain}>
      {stations.map((s) => (
        <div key={s.id} className={styles.station} title={`${s.name}: ${s.reason}`}>
          <span className={styles.bead} data-tone={CHIP_TONE[s.chip]} />
          <span className={styles.stationName}>{s.name}</span>
          <span className={styles.meta}>{s.chip === "GREY" ? "no source" : s.chip === "RED" ? "failing" : "live"}</span>
        </div>
      ))}
    </div>
  );
}

export function ChainRing() {
  const stations = useStations();
  if (!stations) return <Unexpected what="ship chain" />;
  const c = stationCounts(stations);
  return (
    <Ring center={`${c.green}/${stations.length}`} sub="live"
      slices={[
        { label: "Live", value: c.green, color: "var(--board-accent)" },
        { label: "Failing", value: c.red, color: "var(--board-bad)" },
        { label: "No source yet", value: c.grey, color: "var(--board-line-2)" },
      ]} />
  );
}
