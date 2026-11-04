import type { ReactNode } from "react";
import { STATE_TEXT, STATE_TONE, type Tone } from "@/lib/control/command-wall";
import styles from "./command-wall.module.css";

export { STATE_TEXT, STATE_TONE };

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
