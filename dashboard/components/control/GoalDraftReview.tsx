"use client";

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

const inputBase: React.CSSProperties = {
  background: "var(--panel-hover)",
  color: "var(--text)",
  border: "1px solid var(--border)",
  fontFamily: "var(--font-mono, monospace)",
  fontSize: "11px",
  outline: "none",
};

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

  function patch(index: number, patch: Partial<DraftTicket>) {
    onChange(analysis.tickets.map((t, i) => (i === index ? { ...t, ...patch } : t)));
  }

  return (
    <div className="flex flex-col gap-3">
      <p className="text-[11px] font-mono" style={{ color: "var(--text-muted)" }}>
        Linear has not been written. Review the drafts, then approve.
      </p>
      {analysis.fallback ? (
        <p className="text-[11px] font-mono" style={{ color: "var(--warning)" }}>
          Model analysis unavailable — showing the original goal as one ticket.
        </p>
      ) : null}
      {analysis.summary ? (
        <p className="text-[12px]" style={{ color: "var(--text)" }}>{analysis.summary}</p>
      ) : null}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
        {analysis.product ? (
          <section className="rounded-md p-3" style={{ background: "var(--panel)", border: "1px solid var(--border)" }}>
            <h3 className="text-[10px] uppercase tracking-widest mb-1" style={{ color: "var(--text-muted)" }}>Product</h3>
            <p className="text-[11px]" style={{ color: "var(--text)" }}>{analysis.product}</p>
          </section>
        ) : null}
        {analysis.engineering ? (
          <section className="rounded-md p-3" style={{ background: "var(--panel)", border: "1px solid var(--border)" }}>
            <h3 className="text-[10px] uppercase tracking-widest mb-1" style={{ color: "var(--text-muted)" }}>Engineering</h3>
            <p className="text-[11px]" style={{ color: "var(--text)" }}>{analysis.engineering}</p>
          </section>
        ) : null}
      </div>
      {analysis.split_reason ? (
        <p className="text-[11px] font-mono" style={{ color: "var(--text-dim)" }}>
          Split: {analysis.split_reason}
        </p>
      ) : null}

      {analysis.tickets.map((ticket, index) => (
        <article
          key={`${ticket.title}-${index}`}
          className="rounded-md p-3 flex flex-col gap-2"
          style={{ background: "var(--panel)", border: "1px solid var(--border)", opacity: ticket.selected ? 1 : 0.55 }}
        >
          <label className="flex items-center gap-2 text-[11px] font-mono" style={{ color: "var(--text)" }}>
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
            className="w-full h-8 px-2.5 rounded-md"
            style={inputBase}
            aria-label={`Title ${index + 1}`}
          />
          <textarea
            value={ticket.goal}
            disabled={filing || !ticket.selected}
            onChange={(e) => patch(index, { goal: e.target.value })}
            rows={2}
            className="w-full px-2.5 py-2 rounded-md resize-none"
            style={inputBase}
            aria-label={`Goal ${index + 1}`}
          />
          <textarea
            value={ticket.acceptance}
            disabled={filing || !ticket.selected}
            onChange={(e) => patch(index, { acceptance: e.target.value })}
            rows={2}
            className="w-full px-2.5 py-2 rounded-md resize-none"
            style={inputBase}
            aria-label={`Acceptance ${index + 1}`}
          />
          {ticket.rationale ? (
            <p className="text-[11px]" style={{ color: "var(--text-muted)" }}>{ticket.rationale}</p>
          ) : null}
        </article>
      ))}

      {confirming ? (
        <div className="rounded-md p-3 flex flex-col gap-2" style={{ border: "1px solid var(--accent)" }}>
          <p className="text-[12px]" style={{ color: "var(--text)" }}>
            File {count} ticket{count === 1 ? "" : "s"} to Linear Backlog? This writes to Linear.
          </p>
          <div className="flex items-center gap-2">
            <button
              onClick={onApprove}
              disabled={filing || count === 0}
              className="h-8 px-3 rounded-md text-xs font-mono font-medium disabled:opacity-30"
              style={{ background: "var(--accent)", color: "var(--on-accent)" }}
            >
              {filing ? "filing…" : "approve and file"}
            </button>
            <button
              onClick={onCancelConfirm}
              disabled={filing}
              className="h-8 px-3 rounded-md text-xs font-mono"
              style={{ color: "var(--text-muted)", border: "1px solid var(--border)" }}
            >
              back
            </button>
          </div>
        </div>
      ) : (
        <div className="flex items-center gap-2">
          <button
            onClick={onRequestFile}
            disabled={filing || count === 0}
            className="h-8 px-3 rounded-md text-xs font-mono font-medium disabled:opacity-30"
            style={{ background: "var(--accent)", color: "var(--on-accent)" }}
          >
            file {count} on linear
          </button>
          <button
            onClick={onDiscard}
            disabled={filing}
            className="h-8 px-3 rounded-md text-xs font-mono"
            style={{ color: "var(--text-muted)", border: "1px solid var(--border)" }}
          >
            discard
          </button>
        </div>
      )}
    </div>
  );
}
