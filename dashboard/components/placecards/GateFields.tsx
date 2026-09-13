"use client";

import styles from "./placecards.module.css";
import type { usePlacecard } from "./usePlacecard";

type Board = ReturnType<typeof usePlacecard>;

export function GateFields({ board }: { board: Board }) {
  const { card, fenceDraft, setFenceDraft, schemaDraft, setSchemaDraft, gherkinDraft, setGherkinDraft } = board;

  return (
    <section className={styles.panel} aria-label="Stage gates">
      <label className={styles.label}>
        Customer
        <textarea
          data-testid="ans-customer"
          className={styles.textarea}
          rows={2}
          value={card.answers.customer}
          onChange={(event) => board.patchAnswers("customer", event.target.value)}
        />
      </label>
      <label className={styles.label}>
        Metric
        <textarea
          data-testid="ans-metric"
          className={styles.textarea}
          rows={2}
          value={card.answers.metric}
          onChange={(event) => board.patchAnswers("metric", event.target.value)}
        />
      </label>
      <label className={styles.label}>
        Problem
        <textarea
          data-testid="ans-problem"
          className={styles.textarea}
          rows={2}
          value={card.answers.problem}
          onChange={(event) => board.patchAnswers("problem", event.target.value)}
        />
      </label>
      <label className={styles.label}>
        Appetite
        <select
          data-testid="appetite-select"
          className={styles.select}
          value={card.appetite}
          onChange={(event) => board.setAppetite(event.target.value)}
        >
          <option value="">Choose appetite</option>
          <option value="small_batch">Small batch</option>
          <option value="big_batch">Big batch</option>
          <option value="research">Research</option>
        </select>
      </label>
      <div className={styles.row}>
        <input
          data-testid="fence-input"
          className={styles.input}
          value={fenceDraft}
          onChange={(event) => setFenceDraft(event.target.value)}
          placeholder="Add a fence"
        />
        <button type="button" data-testid="fence-add" className={styles.ghost} onClick={board.addFence}>
          Add fence
        </button>
      </div>
      <ul className={styles.list}>
        {card.fences.map((fence) => (
          <li key={fence}>{fence}</li>
        ))}
      </ul>
      <div className={styles.row}>
        <input
          data-testid="schema-text"
          className={styles.input}
          value={schemaDraft}
          onChange={(event) => setSchemaDraft(event.target.value)}
          placeholder="Schema line"
        />
        <button type="button" data-testid="schema-add" className={styles.ghost} onClick={board.addSchema}>
          Add schema
        </button>
      </div>
      <div className={styles.row}>
        <input
          data-testid="gherkin-text"
          className={styles.input}
          value={gherkinDraft}
          onChange={(event) => setGherkinDraft(event.target.value)}
          placeholder="Gherkin scenario"
        />
        <button type="button" data-testid="gherkin-add" className={styles.ghost} onClick={board.addGherkin}>
          Add scenario
        </button>
      </div>
      <p data-testid="gherkin-count" className={styles.status}>
        {card.gherkin.length} scenarios
      </p>
    </section>
  );
}
