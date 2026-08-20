"use client";

import styles from "./control-deck.module.css";

export interface DraftTicket {
  title: string;
  goal: string;
  acceptance: string;
  rationale: string;
  selected: boolean;
}

export interface AnalysisPayload {
  summary: string;
  product: string;
  engineering: string;
  split_reason: string;
  fallback: boolean;
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

function selectedCount(tickets: DraftTicket[]): number {
  return tickets.filter((t) => t.selected).length;
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
    <div className="flex flex-col gap-3">
      <p className={styles.note}>Linear has not been written. Review the drafts, then approve.</p>
      {analysis.fallback ? (
        <p className={styles.note} style={{ color: "var(--warning)" }}>
          Model analysis unavailable — original goal kept as one ticket.
        </p>
      ) : null}
      {analysis.summary ? <p style={{ color: "var(--text)", fontSize: 14, lineHeight: 1.5 }}>{analysis.summary}</p> : null}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
        {analysis.product ? (
          <section className={styles.card}>
            <div className={styles.fieldLabel}>Product</div>
            <p className="mt-2 text-[13px]" style={{ color: "var(--text)" }}>{analysis.product}</p>
          </section>
        ) : null}
        {analysis.engineering ? (
          <section className={styles.card}>
            <div className={styles.fieldLabel}>Engineering</div>
            <p className="mt-2 text-[13px]" style={{ color: "var(--text)" }}>{analysis.engineering}</p>
          </section>
        ) : null}
      </div>
      {analysis.split_reason ? <p className={styles.note}>Split · {analysis.split_reason}</p> : null}

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
          <input
            value={ticket.title}
            disabled={filing || !ticket.selected}
            onChange={(e) => patch(index, { title: e.target.value })}
            className={`${styles.input} mt-2`}
            aria-label={`Title ${index + 1}`}
          />
          <textarea
            value={ticket.goal}
            disabled={filing || !ticket.selected}
            onChange={(e) => patch(index, { goal: e.target.value })}
            rows={2}
            className={`${styles.input} mt-2`}
            aria-label={`Goal ${index + 1}`}
          />
          <textarea
            value={ticket.acceptance}
            disabled={filing || !ticket.selected}
            onChange={(e) => patch(index, { acceptance: e.target.value })}
            rows={2}
            className={`${styles.input} mt-2`}
            aria-label={`Acceptance ${index + 1}`}
          />
          {ticket.rationale ? <p className={`${styles.note} mt-2`}>{ticket.rationale}</p> : null}
        </article>
      ))}

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
