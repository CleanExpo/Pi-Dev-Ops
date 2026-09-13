"use client";

import styles from "./placecards.module.css";
import type { usePlacecard } from "./usePlacecard";

type Board = ReturnType<typeof usePlacecard>;

function SketchPanel({ board }: { board: Board }) {
  return (
    <section className={styles.panel} aria-label="Sketch">
      <div className={styles.sketchPad} aria-hidden="true" />
      <button type="button" data-testid="sketch-save" className={styles.ghost} onClick={board.saveSketch}>
        Save scene
      </button>
      <p data-testid="sketch-status" className={styles.status}>
        {board.card.sketchSaved ? "Scene saved to the card." : "Draw, then save the scene to the card."}
      </p>
    </section>
  );
}

function EvidencePanel({ board }: { board: Board }) {
  return (
    <section className={styles.panel} aria-label="Evidence">
      <ul data-testid="evidence-list" className={styles.list}>
        {board.card.evidence.map((item, index) => (
          <li key={`${item.kind}-${index}`}>
            {item.kind} <span className="tag">{item.tag}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

function RecipePanel({ board }: { board: Board }) {
  return (
    <section className={styles.panel} aria-label="Recipe">
      <p className={styles.note}>
        Schema and Gherkin live in the gate column so a sketch tab cannot hide them.
      </p>
      <ul className={styles.list}>
        {board.card.schemaLines.map((line) => (
          <li key={line}>{line}</li>
        ))}
        {board.card.gherkin.map((line) => (
          <li key={line}>{line}</li>
        ))}
      </ul>
    </section>
  );
}

function GoalPanel({ board }: { board: Board }) {
  return (
    <section className={styles.panel} aria-label="Goal card">
      <label className={styles.label}>
        <span>
          <input
            data-testid="goal-arm"
            type="checkbox"
            checked={board.card.goalArmed}
            onChange={(event) => board.setGoalArmed(event.target.checked)}
          />{" "}
          Arm goal card
        </span>
      </label>
      <div className={styles.row}>
        <input
          data-testid="promise-input"
          className={styles.input}
          value={board.promiseDraft}
          onChange={(event) => board.setPromiseDraft(event.target.value)}
          placeholder="Promise"
        />
        <button type="button" data-testid="promise-add" className={styles.ghost} onClick={board.addPromise}>
          Log promise
        </button>
      </div>
      <ul className={styles.list}>
        {board.card.promises.map((promise) => (
          <li key={promise}>{promise}</li>
        ))}
      </ul>
    </section>
  );
}

function DecisionPanel({ board }: { board: Board }) {
  const summary = board.card.decision
    ? `${board.card.decision.verdict}: ${board.card.decision.reason}`
    : "No decision recorded.";
  return (
    <section className={styles.panel} aria-label="Decision">
      <label className={styles.label}>
        <span>
          <input
            data-testid="decision-go"
            type="checkbox"
            checked={board.decisionGo}
            onChange={(event) => board.setDecisionGo(event.target.checked)}
          />{" "}
          Record a go
        </span>
      </label>
      <label className={styles.label}>
        Reason
        <textarea
          data-testid="decision-reason"
          className={styles.textarea}
          rows={3}
          value={board.decisionReason}
          onChange={(event) => board.setDecisionReason(event.target.value)}
        />
      </label>
      <button type="button" data-testid="decision-record" className={styles.ghost} onClick={board.recordDecision}>
        Record decision
      </button>
      <p data-testid="decision-summary" className={styles.status}>{summary}</p>
      <p className={styles.note}>Recording stays on this origin. Nothing is executed.</p>
    </section>
  );
}

export function SidePanels({ board }: { board: Board }) {
  if (board.tab === "sketch") return <SketchPanel board={board} />;
  if (board.tab === "evidence") return <EvidencePanel board={board} />;
  if (board.tab === "recipe") return <RecipePanel board={board} />;
  if (board.tab === "goal") return <GoalPanel board={board} />;
  if (board.tab === "decision") return <DecisionPanel board={board} />;
  return (
    <section className={styles.panel} aria-label="Intake">
      <p className={styles.note}>{board.card.blurb}</p>
      <p className={styles.note}>
        {board.remaining.length === 0
          ? "Gate clear. Advance when ready."
          : `Still needed: ${board.remaining.map((gate) => gate.label).join(", ")}.`}
      </p>
    </section>
  );
}
