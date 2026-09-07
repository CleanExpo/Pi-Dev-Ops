"use client";

import type { GoalStage } from "@/lib/control/goalStage";
import styles from "./control-deck.module.css";

const STAGES: Array<{ n: GoalStage; label: string }> = [
  { n: 1, label: "Compose" },
  { n: 2, label: "Analyze" },
  { n: 3, label: "Write" },
];

export default function GoalStagePills({ stage }: { stage: GoalStage }) {
  return (
    <div className={styles.stageRow} aria-label="Goal filing stages">
      {STAGES.map((s) => (
        <div key={s.n} className={`${styles.stage} ${stage === s.n ? styles.stageOn : ""}`}>
          <div className={styles.stageNum}>Stage {s.n}</div>
          <div className={styles.stageLabel}>{s.label}</div>
        </div>
      ))}
    </div>
  );
}
