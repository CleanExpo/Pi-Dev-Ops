"use client";

import styles from "./control-deck.module.css";

export interface DraftTicket {
  title: string;
  goal: string;
  acceptance: string;
  rationale: string;
  context: string;
  user_story: string;
  current_behaviour: string;
  expected_behaviour: string;
  technical_requirements: string;
  edge_cases: string;
  testing: string;
  dependencies: string;
  selected: boolean;
}

export interface AnalysisPayload {
  summary: string;
  split_reason: string;
  fallback: boolean;
  code_inspected: boolean;
  code_limitation: string;
  tickets: DraftTicket[];
}

interface Props {
  analysis: AnalysisPayload;
  confirming: boolean;
  filing: boolean;
  onChange: (tickets: DraftTicket[]) => void;
  onDiscard: () => void;
  onRequestFile: () => void;
  onCancelConfirm: () => void;
  onApprove: () => void;
}

const AREAS: Array<{ key: keyof DraftTicket; label: string; rows: number }> = [
  { key: "context", label: "Context", rows: 3 },
  { key: "user_story", label: "User story", rows: 2 },
  { key: "current_behaviour", label: "Current behaviour", rows: 3 },
  { key: "expected_behaviour", label: "Expected behaviour", rows: 3 },
  { key: "technical_requirements", label: "Technical requirements", rows: 4 },
  { key: "acceptance", label: "Acceptance criteria", rows: 4 },
  { key: "edge_cases", label: "Edge cases", rows: 3 },
  { key: "testing", label: "Testing", rows: 3 },
  { key: "dependencies", label: "Dependencies", rows: 2 },
];

function selectedCount(tickets: DraftTicket[]): number {
  return tickets.filter((t) => t.selected).length;
}

export function draftsFromAnalyze(raw: Array<Partial<DraftTicket>>): DraftTicket[] {
  const blank: Omit<DraftTicket, "selected"> = {
    title: "",
    goal: "",
    acceptance: "",
    rationale: "",
    context: "",
    user_story: "",
    current_behaviour: "",
    expected_behaviour: "",
    technical_requirements: "",
    edge_cases: "",
    testing: "",
    dependencies: "",
  };
  return raw.flatMap((t) => {
    const expected = (t.expected_behaviour || t.goal || "").trim();
    const acceptance = (t.acceptance || "").trim();
    const title = (t.title || "").trim();
    if (!title || !expected || !acceptance) return [];
    return [{ ...blank, ...t, title, goal: expected, expected_behaviour: expected, acceptance, selected: true }];
  });
}

export default function GoalDraftReview({
  analysis,
  confirming,
  filing,
  onChange,
  onDiscard,
  onRequestFile,
  onCancelConfirm,
  onApprove,
}: Props) {
  const count = selectedCount(analysis.tickets);

  function patch(index: number, next: Partial<DraftTicket>) {
    onChange(analysis.tickets.map((t, i) => (i === index ? { ...t, ...next } : t)));
  }

  return (
    <div className="flex flex-col gap-4">
      <section className={styles.card}>
        <div className={styles.fieldLabel}>Goal analysis</div>
        <p className="mt-2 text-[14px] leading-relaxed" style={{ color: "var(--text)" }}>
          {analysis.summary || "No analysis text returned."}
        </p>
        {!analysis.code_inspected && analysis.code_limitation ? (
          <p className="mt-2 text-[13px]" style={{ color: "var(--warning)" }}>
            {analysis.code_limitation}
          </p>
        ) : (
          <p className={`${styles.note} mt-2`}>Repo excerpt was used. Paths still need a human check.</p>
        )}
      </section>

      <section className={styles.card}>
        <div className={styles.fieldLabel}>Implementation breakdown</div>
        <p className="mt-2 text-[14px] leading-relaxed" style={{ color: "var(--text)" }}>
          {analysis.split_reason || "Split reason was not returned."}
        </p>
      </section>

      <div className={styles.fieldLabel}>Draft Linear tickets</div>
      {analysis.tickets.map((ticket, index) => (
        <article
          key={`${ticket.title}-${index}`}
          className={styles.card}
          style={{ opacity: ticket.selected ? 1 : 0.5 }}
        >
          <label className="flex items-center gap-2 text-[12px] font-mono" style={{ color: "var(--text)" }}>
            <input
              type="checkbox"
              checked={ticket.selected}
              disabled={filing}
              onChange={(e) => patch(index, { selected: e.target.checked })}
              aria-label={`Include ticket ${index + 1}`}
            />
            Ticket {index + 1} of {analysis.tickets.length}
          </label>
          <label className={styles.field}>
            <span className={styles.fieldLabel}>Title</span>
            <input
              value={ticket.title}
              disabled={filing || !ticket.selected}
              onChange={(e) => patch(index, { title: e.target.value })}
              className={styles.input}
              aria-label={`Title ${index + 1}`}
            />
          </label>
          {AREAS.map((field) => (
            <label key={field.key} className={styles.field}>
              <span className={styles.fieldLabel}>{field.label}</span>
              <textarea
                value={String(ticket[field.key] ?? "")}
                disabled={filing || !ticket.selected}
                onChange={(e) => {
                  const next: Partial<DraftTicket> = { [field.key]: e.target.value };
                  if (field.key === "expected_behaviour") next.goal = e.target.value;
                  patch(index, next);
                }}
                rows={field.rows}
                className={styles.input}
                aria-label={`${field.label} ${index + 1}`}
              />
            </label>
          ))}
        </article>
      ))}

      <p className={styles.note}>Draft only — nothing has been written to Linear.</p>

      {confirming ? (
        <div className={`${styles.card} ${styles.confirm}`}>
          <p style={{ color: "var(--text)", fontSize: 14 }}>
            File {count} ticket{count === 1 ? "" : "s"} to Linear Backlog? This writes to Linear.
          </p>
          <div className="flex flex-wrap gap-2 mt-3">
            <button onClick={onApprove} disabled={filing || count === 0} className={styles.primary}>
              {filing ? "Filing…" : "Approve and file"}
            </button>
            <button onClick={onCancelConfirm} disabled={filing} className={styles.ghost}>Back</button>
          </div>
        </div>
      ) : (
        <div className="flex flex-wrap gap-2">
          <button onClick={onRequestFile} disabled={filing || count === 0} className={styles.primary}>
            File {count} on Linear
          </button>
          <button onClick={onDiscard} disabled={filing} className={styles.ghost}>Discard</button>
        </div>
      )}
    </div>
  );
}
