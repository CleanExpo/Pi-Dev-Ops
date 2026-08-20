"use client";

import GoalAnalysisOverview, {
  type AnalysisOverview,
  type FinalReviewBlock,
  type FlowBlock,
  type GoalAnalysisBlock,
  type OrderStep,
} from "./GoalAnalysisOverview";
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
  ticket_id: string;
  priority: string;
  summary: string;
  scope: string;
  user_flow: string;
  technical_flow: string;
  examples: string;
  implementation_notes: string;
  risks: string;
  review: string;
  ui_ux: string;
  data_state: string;
  affected_surfaces: string;
  selected: boolean;
}

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

const AREAS: Array<{ key: keyof DraftTicket; label: string; rows: number }> = [
  { key: "summary", label: "Summary", rows: 2 },
  { key: "context", label: "Context", rows: 3 },
  { key: "user_story", label: "User story", rows: 2 },
  { key: "current_behaviour", label: "Current behaviour", rows: 3 },
  { key: "expected_behaviour", label: "Expected behaviour", rows: 3 },
  { key: "scope", label: "Scope", rows: 3 },
  { key: "affected_surfaces", label: "Affected surfaces", rows: 2 },
  { key: "technical_requirements", label: "Technical requirements", rows: 4 },
  { key: "implementation_notes", label: "Implementation notes", rows: 3 },
  { key: "ui_ux", label: "UI / UX", rows: 3 },
  { key: "data_state", label: "Data / state", rows: 3 },
  { key: "user_flow", label: "User flow", rows: 4 },
  { key: "technical_flow", label: "Technical flow", rows: 4 },
  { key: "examples", label: "Examples", rows: 3 },
  { key: "acceptance", label: "Acceptance criteria", rows: 4 },
  { key: "edge_cases", label: "Edge cases", rows: 3 },
  { key: "testing", label: "Testing", rows: 3 },
  { key: "dependencies", label: "Dependencies", rows: 2 },
  { key: "risks", label: "Risks", rows: 2 },
  { key: "review", label: "Review", rows: 3 },
  { key: "rationale", label: "Why this ticket", rows: 2 },
];

function selectedCount(tickets: DraftTicket[]): number {
  return tickets.filter((t) => t.selected).length;
}

const BLANK: Omit<DraftTicket, "selected"> = {
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
  ticket_id: "",
  priority: "",
  summary: "",
  scope: "",
  user_flow: "",
  technical_flow: "",
  examples: "",
  implementation_notes: "",
  risks: "",
  review: "",
  ui_ux: "",
  data_state: "",
  affected_surfaces: "",
};

export function draftsFromAnalyze(raw: Array<Partial<DraftTicket>>): DraftTicket[] {
  return raw.flatMap((t) => {
    const expected = (t.expected_behaviour || t.goal || "").trim();
    const acceptance = (t.acceptance || "").trim();
    const title = (t.title || "").trim();
    if (!title || !expected || !acceptance) return [];
    const next: DraftTicket = { ...BLANK, selected: true };
    (Object.keys(BLANK) as Array<keyof typeof BLANK>).forEach((key) => {
      const value = t[key];
      next[key] = typeof value === "string" ? value : BLANK[key];
    });
    next.title = title;
    next.goal = expected;
    next.expected_behaviour = expected;
    next.acceptance = acceptance;
    next.selected = true;
    return [next];
  });
}

export function filePayloadFromDraft(
  t: DraftTicket,
  sanitize: (value: string) => string,
): Record<string, string> {
  const s = (value: string) => sanitize(value.trim());
  return {
    title: s(t.title),
    goal: s(t.goal || t.expected_behaviour),
    acceptance: s(t.acceptance),
    rationale: s(t.rationale),
    context: s(t.context),
    user_story: s(t.user_story),
    current_behaviour: s(t.current_behaviour),
    expected_behaviour: s(t.expected_behaviour),
    technical_requirements: s(t.technical_requirements),
    edge_cases: s(t.edge_cases),
    testing: s(t.testing),
    dependencies: s(t.dependencies),
    ticket_id: s(t.ticket_id),
    priority: s(t.priority),
    summary: s(t.summary),
    scope: s(t.scope),
    user_flow: s(t.user_flow),
    technical_flow: s(t.technical_flow),
    examples: s(t.examples),
    implementation_notes: s(t.implementation_notes),
    risks: s(t.risks),
    review: s(t.review),
    ui_ux: s(t.ui_ux),
    data_state: s(t.data_state),
    affected_surfaces: s(t.affected_surfaces),
  };
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
