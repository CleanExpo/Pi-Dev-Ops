"use client";
import { useEffect, useState } from "react";
import { BRISBANE_LABEL, brisbaneTime } from "@/lib/brisbane-time";
import styles from "./command-wall.module.css";
import { Dot } from "./WallPanel";

/** Renders after mount only, so server and browser never disagree on the first paint. */
function Clock() {
  const [now, setNow] = useState<number | null>(null);
  useEffect(() => {
    setNow(Date.now());
    const t = setInterval(() => setNow(Date.now()), 1_000);
    return () => clearInterval(t);
  }, []);
  return (
    <span className={styles.clock} aria-label="Brisbane time" role="timer">
      {now === null ? "--:--:--" : brisbaneTime(now, true)}
      <span className={styles.clockZone}>{BRISBANE_LABEL}</span>
    </span>
  );
}

export default function StatusBar({ live, total }: { live: number; total: number }) {
  const tone = live === total ? "ok" : live === 0 ? "bad" : "warn";
  return (
    <header className={`${styles.panel} ${styles.status}`}>
      <div className={styles.brand}>
        <span className={styles.kicker}>Unite-Group Nexus</span>
        <h1 className={styles.title}>Mission Control</h1>
      </div>
      <div className={styles.statusMeta}>
        <span className={styles.state}><Dot tone={tone} />{live} of {total} sources live</span>
        <a
          className={styles.statusLink}
          href="https://github.com/CleanExpo/Pi-Dev-Ops/blob/main/docs/governance/NEXUS-NORTH-STAR.md"
          target="_blank"
          rel="noopener noreferrer"
        >
          North Star: Built for the Hard Day
        </a>
      </div>
      <Clock />
    </header>
  );
}
