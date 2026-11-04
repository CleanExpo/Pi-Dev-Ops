"use client";
import { useEffect, useState } from "react";
import type { Alert } from "@/lib/control/command-wall";
import styles from "./command-wall.module.css";
import { Dot } from "./WallPanel";

function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReduced(query.matches);
    const onChange = (e: MediaQueryListEvent) => setReduced(e.matches);
    query.addEventListener?.("change", onChange);
    return () => query.removeEventListener?.("change", onChange);
  }, []);
  return reduced;
}

function Items({ alerts, copy }: { alerts: Alert[]; copy: boolean }) {
  return (
    <>
      {alerts.map((a) => (
        <li key={`${copy ? "copy-" : ""}${a.id}`} className={styles.tickerItem} aria-hidden={copy || undefined}>
          <Dot tone={a.tone} />{a.text}
        </li>
      ))}
    </>
  );
}

/**
 * Scrolls only when there is something to scroll and motion is allowed. The
 * second copy exists only to make the loop seamless and is hidden from readers.
 */
export default function AlertTicker({ alerts, allClearText }: { alerts: Alert[]; allClearText: string }) {
  const reduced = usePrefersReducedMotion();
  const scroll = !reduced && alerts.length > 1;
  const items = alerts.length > 0 ? alerts : [{ id: "clear", tone: "ok" as const, text: allClearText }];
  return (
    <section className={`${styles.panel} ${styles.ticker}`} aria-label="Alerts and incidents">
      <div className={styles.tickerRow}>
        <span className={styles.tickerLabel}>Alerts {alerts.length > 0 ? `· ${alerts.length}` : ""}</span>
        <div className={styles.tickerViewport} tabIndex={0} aria-label="Alert list, pauses on hover or focus">
          <ul
            className={styles.tickerTrack}
            data-static={!scroll}
            style={{ ["--ticker-duration" as string]: `${Math.max(20, items.length * 7)}s` }}
          >
            <Items alerts={items} copy={false} />
            {scroll && <Items alerts={items} copy />}
          </ul>
        </div>
      </div>
    </section>
  );
}
