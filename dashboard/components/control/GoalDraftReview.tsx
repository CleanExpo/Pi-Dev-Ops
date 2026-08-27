"use client";

import GoalAnalysisOverview, {
  type AnalysisOverview,
  type FinalReviewBlock,
  type FlowBlock,
  type GoalAnalysisBlock,
  type OrderStep,
} from "./GoalAnalysisOverview";
import {
  ALWAYS_SHOW,
  DRAFT_AREAS,
  draftsFromAnalyze,
  filePayloadFromDraft,
  type DraftTicket,
} from "./GoalDraftFields";
import styles from "./control-deck.module.css";

export type { DraftTicket };
export { draftsFromAnalyze, filePayloadFromDraft };

export interface AnalysisPayload extends AnalysisOverview {
  fallback: boolean;
  tickets: DraftTicket[];
  goal_analysis?: GoalAnalysisBlock;
  user_flow?: FlowBlock;
  technical_flow?: FlowBlock;
  implementation_order?: OrderStep[];
  final_review?: FinalReviewBlock;
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
    <div className="flex flex-col gap-4">
      <GoalAnalysisOverview analysis={analysis} />

      <div className={styles.fieldLabel}>Draft Linear tickets</div>
      {analysis.tickets.map((ticket, index) => (
        <article
          key={`${ticket.ticket_id || ticket.title}-${index}`}
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
            {ticket.ticket_id || `Ticket ${index + 1}`} of {analysis.tickets.length}
            {ticket.priority ? ` · ${ticket.priority}` : ""}
          </label>
          {ticket.ticket_id || ticket.priority ? (
            <div className="grid gap-3 sm:grid-cols-2">
              <label className={styles.field}>
                <span className={styles.fieldLabel}>ID</span>
                <input
                  value={ticket.ticket_id}
                  disabled={filing || !ticket.selected}
                  onChange={(e) => patch(index, { ticket_id: e.target.value })}
                  className={styles.input}
                  aria-label={`ID ${index + 1}`}
                />
              </label>
              <label className={styles.field}>
                <span className={styles.fieldLabel}>Priority</span>
                <input
                  value={ticket.priority}
                  disabled={filing || !ticket.selected}
                  onChange={(e) => patch(index, { priority: e.target.value })}
                  className={styles.input}
                  aria-label={`Priority ${index + 1}`}
                />
              </label>
            </div>
          ) : null}
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
          {DRAFT_AREAS.filter(
            (field) =>
              ALWAYS_SHOW.includes(field.key) || String(ticket[field.key] ?? "").trim(),
          ).map((field) => (
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
