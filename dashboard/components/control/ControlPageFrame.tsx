import type { ReactNode } from "react";
import styles from "./control-deck.module.css";

export default function ControlPageFrame({
  kicker = "Control",
  title,
  hint,
  children,
}: {
  kicker?: string;
  title: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    // tabIndex: a scrolling region must be keyboard-reachable when its content
    // has no focusable element (axe scrollable-region-focusable, RA-7843).
    <div className="flex-1 overflow-auto min-h-0" role="region" aria-label={title} tabIndex={0}>
      <header className={styles.hero}>
        <div>
          <div className={styles.kicker}>{kicker}</div>
          <h1 className={styles.title}>{title}</h1>
          {hint ? <p className={styles.lede}>{hint}</p> : null}
        </div>
      </header>
      <div className="px-5 pb-8 pt-2">{children}</div>
    </div>
  );
}
