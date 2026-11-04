import { ageText, type FleetScreenTile } from "@/lib/control/command-wall";
import styles from "./command-wall.module.css";
import { Dot } from "./WallPanel";

function claimText(claim: FleetScreenTile["claim"]): string {
  if (claim === undefined) return "job claims unreadable";
  return claim ? `working on ${claim}` : "no job claimed";
}

function Machine({ tile }: { tile: FleetScreenTile }) {
  return (
    <article className={styles.machine} data-tone={tile.tone} aria-label={`${tile.label}: ${tile.status}`}>
      <div className={styles.machineHead}>
        <Dot tone={tile.tone} />
        <span className={styles.machineName}>{tile.label}</span>
        <span className={`${styles.machineHost} ${styles.mono}`}>{tile.host}</span>
      </div>
      <div className={styles.machineFacts}>
        <span>{tile.status}</span>
        <span className={styles.mono}>heartbeat {ageText(tile.ageSeconds)}{tile.ageSeconds === null ? "" : " ago"}</span>
        {tile.load1 !== null && <span className={styles.mono}>load {tile.load1.toFixed(2)}</span>}
        <span>{claimText(tile.claim)}</span>
      </div>
      {tile.agents.length > 0 && (
        <div className={styles.agents} aria-label={`${tile.label} agents`}>
          {tile.agents.map((a, i) => (
            <span key={`${a.runtime}-${i}`} className={styles.agent}>
              <Dot tone={a.fresh ? "ok" : "idle"} />{a.runtime} · {a.fresh ? a.state : "no signal"}
            </span>
          ))}
        </div>
      )}
    </article>
  );
}

export default function FleetScreen({ tiles, failure }: { tiles: FleetScreenTile[]; failure: string | null }) {
  if (tiles.length === 0) {
    return <p className={`${styles.note} ${failure ? styles.noteBad : ""}`}>{failure ?? "Waiting for the first fleet heartbeat read."}</p>;
  }
  return (
    <div className={styles.machines}>
      {tiles.map((t) => <Machine key={t.host} tile={t} />)}
      <p className={styles.footnote}>Heartbeats are self-reported by each machine. Fresh means seen in the last 60 seconds.</p>
    </div>
  );
}
