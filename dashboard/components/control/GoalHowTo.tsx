"use client";

import { useState } from "react";
import { HOW_TO_GET_THE_GOAL } from "@/lib/control/goalCopy";
import styles from "./control-deck.module.css";

export default function GoalHowTo() {
  const [open, setOpen] = useState(true);
  return (
    <section className={`${styles.card} mb-4`} aria-label="How to get the full goal">
      <button type="button" onClick={() => setOpen(!open)} className={styles.ghost}>
        {open ? "Hide how to use Goal" : "How to get the full goal from this path"}
      </button>
      {open ? (
        <>
          <p className="mt-3 text-[13px]" style={{ color: "var(--text-muted)" }}>
            Tickets land in Backlog. This page never starts the build. A stranger must still
            be able to pass every acceptance without asking the author. Analyze never writes.
          </p>
          <ol className="mt-3 pl-5 flex flex-col gap-2 text-[13px]" style={{ color: "var(--text)" }}>
            {HOW_TO_GET_THE_GOAL.map((step) => (
              <li key={step}>{step}</li>
            ))}
          </ol>
        </>
      ) : null}
    </section>
  );
}
