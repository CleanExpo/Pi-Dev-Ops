import type { ReactNode } from "react";
import type { SourceState } from "@/lib/boards/sources";
import type { Tone } from "@/lib/control/command-wall";
import styles from "./command-wall.module.css";

/** Plain-words label for a feed state. "live" only when the source itself answered. */
export const STATE_TEXT: Record<SourceState, string> = {
  loading: "connecting",
  live: "live",
  stale: "stale",
  unreachable: "unavailable",
  no_source: "not connected",
};

export const STATE_TONE: Record<SourceState, Tone> = {
  loading: "idle",
  live: "ok",
  stale: "warn",
  unreachable: "bad",
  no_source: "idle",
};

export function Dot({ tone }: { tone: Tone }) {
  return <span className={styles.dot} data-tone={tone} aria-hidden="true" />;
}

interface Props {
  id: string;
  title: string;
  area: "fleet" | "prs" | "flow" | "rev" | "ticker";
  /** The panel's own source state, shown in plain words beside the title. */
  stateText: string;
  tone: Tone;
  children: ReactNode;
}

export default function WallPanel({ id, title, area, stateText, tone, children }: Props) {
  return (
    <section className={`${styles.panel} ${styles[area]}`} data-tone={tone} aria-labelledby={id}>
      <header className={styles.panelHead}>
        <h2 id={id} className={styles.panelTitle}>{title}</h2>
        <span className={styles.state}><Dot tone={tone} />{stateText}</span>
      </header>
      <div className={styles.panelBody}>{children}</div>
    </section>
  );
}
