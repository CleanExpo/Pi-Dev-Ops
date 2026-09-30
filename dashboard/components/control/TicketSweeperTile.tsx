// Ticket Sweeper tile — audit #17. Reads `ticket_sweeper` from /api/mission-control/live.
// Never-run and incomplete runs are shown as such, never as a clean zero.
import type { MCTicketSweeper } from "@/lib/control/mission-control-live";
import { brisbaneDateTime } from "@/lib/brisbane-time";

const ROWS: { key: keyof NonNullable<MCTicketSweeper["counts"]>; label: string }[] = [
  { key: "stale_to_todo", label: "Stale → Todo" },
  { key: "stale_labelled", label: "Stale, labelled only" },
  { key: "review_red_pr", label: "In Review, red / unreviewed PR" },
  { key: "review_unknown", label: "In Review, PR unreadable" },
  { key: "failed_to_ready", label: "Failed build → Ready (retry)" },
  { key: "failed_to_blocked", label: "Failed build → Blocked" },
];

export default function TicketSweeperTile({ sweeper }: { sweeper?: MCTicketSweeper }) {
  const counts = sweeper?.counts ?? null;
  const status = !sweeper
    ? "No data"
    : !sweeper.last_run_at || !counts
      ? "Never run"
      : `${sweeper.dry_run ? "Dry run" : "Live"} · ${brisbaneDateTime(new Date(sweeper.last_run_at))}`;
  return (
    <section
      className="flex flex-col min-h-0"
      style={{ background: "var(--panel)", border: "1px solid var(--border)", borderRadius: 8 }}
      aria-label="Ticket Sweeper"
    >
      <header className="px-4 py-2.5" style={{ borderBottom: "1px solid var(--border)" }}>
        <h2 className="text-xs font-semibold uppercase tracking-widest" style={{ color: "var(--text-muted)" }}>
          Ticket Sweeper
        </h2>
      </header>
      <div className="flex-1 overflow-auto p-4 flex flex-col gap-2 min-h-0 text-sm">
        <div className="flex items-center justify-between gap-3">
          <span style={{ color: "var(--text-muted)" }}>Last run</span>
          <span className="font-medium" style={{ color: counts ? "var(--text)" : "var(--text-dim)" }}>{status}</span>
        </div>
        {sweeper && counts && !sweeper.complete && (
          <p style={{ color: "var(--warning)" }}>
            Incomplete run — {sweeper.errors.length} error(s); counts below are partial.
          </p>
        )}
        {counts &&
          ROWS.map((r) => (
            <div key={r.key} className="flex items-center justify-between gap-3">
              <span style={{ color: "var(--text-muted)" }}>{r.label}</span>
              <span
                className="font-medium tabular-nums"
                style={{ color: counts[r.key] > 0 ? "var(--warning)" : "var(--text)" }}
              >
                {counts[r.key]}
              </span>
            </div>
          ))}
      </div>
    </section>
  );
}
