// components/control/CuratorProposalsPanel.tsx — RA-1839
//
// Read-only panel listing pending Curator proposals (skill self-authoring).
// Polls /api/curator-proposals every 30 s. Renders 0-state cleanly when
// the curator hasn't proposed anything yet.

"use client";

import { useSource, type CuratorValue } from "@/lib/boards/sources";

type ProposalsResponse = CuratorValue;


function fmtAge(ts: string): string {
  const ms = Date.now() - new Date(ts).getTime();
  if (Number.isNaN(ms)) return "?";
  if (ms < 60_000) return `${Math.floor(ms / 1_000)}s ago`;
  if (ms < 3_600_000) return `${Math.floor(ms / 60_000)}m ago`;
  if (ms < 86_400_000) return `${Math.floor(ms / 3_600_000)}h ago`;
  return `${Math.floor(ms / 86_400_000)}d ago`;
}

export default function CuratorProposalsPanel() {
  // RA-7898: one shared /api/curator-proposals poller (30 s) for every copy on screen.
  const source = useSource<ProposalsResponse>("curator");
  const data = source.seq > 0 ? source.value : null;

  const proposals = data?.proposals ?? [];
  const pendingCount = data?.by_status?.pending ?? 0;
  const acceptedCount = data?.by_status?.accepted ?? 0;
  const rejectedCount = Object.entries(data?.by_status ?? {})
    .filter(([k]) => k.startsWith("rejected"))
    .reduce((acc, [, v]) => acc + (v as number), 0);

  return (
    <section
      className="flex flex-col h-full min-h-0"
      style={{
        background: "var(--panel)",
        border: "1px solid var(--border)",
        borderRadius: 8,
      }}
      aria-label="Curator proposals"
    >
      <header
        className="flex items-center justify-between px-4 py-2.5"
        style={{ borderBottom: "1px solid var(--border)" }}
      >
        <h2 className="text-sm font-semibold tracking-tight">
          Skill Curator — specialist
        </h2>
        <span className="text-[11px]" style={{ color: "var(--text-dim)" }}>
          {pendingCount} pending · {acceptedCount} accepted · {rejectedCount} rejected
        </span>
      </header>

      <div className="flex-1 overflow-auto p-4">
        {data?.error && (
          <p className="text-xs font-mono" style={{ color: "var(--error)" }}>
            <span aria-hidden="true">⚠ </span>
            {data.error}
          </p>
        )}

        {data === null && (
          <p className="text-xs" style={{ color: "var(--text-dim)" }}>
            Loading…
          </p>
        )}

        {data !== null && !data.error && proposals.length === 0 && (
          <p className="text-xs" style={{ color: "var(--text-dim)" }} data-mc-empty="no curator proposals are pending review">
            No pending proposals. Not the Goal path. The curator still
            clusters lessons.jsonl; it does not file Linear tickets.
          </p>
        )}

        {proposals.length > 0 && (
          <ul className="flex flex-col gap-2">
            {proposals.map((p) => (
              <li
                key={p.proposal_id ?? `${p.ts}-${p.cluster_id}`}
                className="rounded border px-3 py-2 text-xs"
                style={{
                  background: "var(--surface)",
                  borderColor: "var(--border)",
                }}
              >
                <div className="flex items-center justify-between gap-2">
                  <span
                    className="font-mono"
                    style={{ color: "var(--accent)" }}
                    data-mc-data={p.proposed_skill_name && !data?.error ? "curator-proposal" : undefined}
                  >
                    {p.proposed_skill_name ?? "(unnamed)"}
                  </span>
                  <span
                    className="text-[10px]"
                    style={{ color: "var(--text-dim)" }}
                  >
                    {fmtAge(p.ts)}
                  </span>
                </div>
                <div
                  className="mt-1 text-[11px]"
                  style={{ color: "var(--text-dim)" }}
                >
                  {p.cluster_summary ?? "(no summary)"}
                </div>
                <div
                  className="mt-1 flex items-center gap-2 text-[10px]"
                  style={{ color: "var(--text-muted)" }}
                >
                  <span>source: {p.trigger_source ?? "?"}</span>
                  <span>·</span>
                  <span>evidence: {p.evidence_count ?? "?"}</span>
                  {p.draft_id && (
                    <>
                      <span>·</span>
                      <span>draft: {p.draft_id.slice(0, 8)}…</span>
                    </>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
