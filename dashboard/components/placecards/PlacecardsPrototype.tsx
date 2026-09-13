"use client";

import { advanceLabel } from "@/lib/placecards/model";
import { GateFields } from "./GateFields";
import { SidePanels } from "./SidePanels";
import styles from "./placecards.module.css";
import { usePlacecard } from "./usePlacecard";

const TABS = [
  { id: "intake", label: "Intake" },
  { id: "sketch", label: "Sketch" },
  { id: "evidence", label: "Evidence" },
  { id: "recipe", label: "Recipe" },
  { id: "goal", label: "Goal" },
  { id: "decision", label: "Decision" },
] as const;

export function PlacecardsPrototype() {
  const board = usePlacecard();
  const { card } = board;

  return (
    <main className={styles.page}>
      <div className={styles.kicker}>Pi CEO · Mission Control</div>
      <h1 className={styles.title}>Placecards</h1>
      <p className={styles.lede}>
        Spark through graduate. Gates block a move until the checklist is filled.
        A decision is recorded here, never executed.
      </p>
      {!board.open ? (
        <button
          type="button"
          data-testid="card-tile-c1"
          className={styles.tile}
          onClick={board.openCard}
        >
          <span className={styles.tileTitle}>{card.title}</span>
          <span className={styles.tileBlurb}>{card.blurb}</span>
        </button>
      ) : (
        <div className={styles.workspace}>
          <div className={styles.top}>
            <span data-testid="chip-stage" className={styles.chip}>
              Stage: {card.stage}
            </span>
            <button
              type="button"
              data-testid="advance-btn"
              className={styles.advance}
              disabled={!board.advanceEnabled}
              onClick={board.advance}
            >
              {advanceLabel(card)}
            </button>
          </div>
          <div className={styles.tabs}>
            {TABS.map((tab) => (
              <button
                key={tab.id}
                type="button"
                data-testid={`tab-${tab.id}`}
                className={`${styles.tab} ${board.tab === tab.id ? styles.tabActive : ""}`}
                onClick={() => board.setTab(tab.id)}
              >
                {tab.label}
              </button>
            ))}
          </div>
          <div className={styles.grid}>
            <GateFields board={board} />
            <SidePanels board={board} />
          </div>
          <section className={styles.panel} aria-label="Move log">
            <ul data-testid="move-log" className={styles.list}>
              {card.moves.map((move, index) => (
                <li key={`${move}-${index}`}>{move}</li>
              ))}
            </ul>
          </section>
        </div>
      )}
    </main>
  );
}
