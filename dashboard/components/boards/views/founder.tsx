"use client";
// RA-7898 — North Star (static text) and Brisbane clock (this screen's clock).

import { useNow } from "@/lib/boards/use-now";
import styles from "./views.module.css";

/** Quoted from docs/governance/NEXUS-NORTH-STAR.md (founder approved 29 Sept 2026). */
export const NORTH_STAR = {
  source: "docs/governance/NEXUS-NORTH-STAR.md",
  title: "Built for the Hard Day",
  line: "Build a group of businesses, people and systems that earn trust when conditions are hardest.",
} as const;

export function NorthStarBanner() {
  return (
    <div className={styles.northStar}>
      <h2>{NORTH_STAR.title}</h2>
      <p>{NORTH_STAR.line}</p>
    </div>
  );
}

export function NorthStarCompact() {
  return <div className={styles.northStar}><h2>{NORTH_STAR.title}</h2></div>;
}

export function brisbaneParts(now: number): { h: number; m: number; s: number; label: string } {
  const parts = new Intl.DateTimeFormat("en-AU", {
    timeZone: "Australia/Brisbane", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false,
    weekday: "long", day: "numeric", month: "long",
  }).formatToParts(new Date(now));
  const get = (t: string) => parts.find((p) => p.type === t)?.value ?? "";
  return { h: Number(get("hour")) % 24, m: Number(get("minute")), s: Number(get("second")), label: `${get("weekday")} ${get("day")} ${get("month")}` };
}

const pad = (n: number) => String(n).padStart(2, "0");

export function ClockDigital() {
  const t = brisbaneParts(useNow(1_000));
  return (
    <div className={styles.hero} data-testid="clock">
      <span className={styles.clock}>{pad(t.h)}:{pad(t.m)}<span className={styles.dim}>:{pad(t.s)}</span></span>
      <span className={styles.sub}>{t.label}</span>
    </div>
  );
}
