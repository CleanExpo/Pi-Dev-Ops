// components/control/CuratorProposalsPanel.tsx — RA-1839
//
// Read-only panel listing pending Curator proposals (skill self-authoring).
// Polls /api/curator-proposals every 30 s. Renders 0-state cleanly when
// the curator hasn't proposed anything yet.

"use client";

import { useEffect, useState, useCallback } from "react";

interface ProposalRow {
  proposal_id?: string;
  ts: string;
  cluster_id?: string;
  trigger_source?: string;
  cluster_summary?: string;
  evidence_count?: number;
  proposed_skill_name?: string;
  status: string;
  draft_id?: string;
  reason?: string;
}

interface ProposalsResponse {
  total?: number;
  returned?: number;
  by_status?: Record<string, number>;
  proposals?: ProposalRow[];
  error?: string;
}

const POLL_MS = 30_000;
const FILTER_STATUS = "pending";

function fmtAge(ts: string): string {
  const ms = Date.now() - new Date(ts).getTime();
  if (Number.isNaN(ms)) return "?";
  if (ms < 60_000) return `${Math.floor(ms / 1_000)}s ago`;
  if (ms < 3_600_000) return `${Math.floor(ms / 60_000)}m ago`;
  if (ms < 86_400_000) return `${Math.floor(ms / 3_600_000)}h ago`;
  return `${Math.floor(ms / 86_400_000)}d ago`;
}

export default function CuratorProposalsPanel() {
  const [data, setData] = useState<ProposalsResponse | null>(null);

  const refresh = useCallback(async () => {
    try {
      const r = await fetch(
        `/api/curator-proposals?status=${FILTER_STATUS}&limit=10`,
        { cache: "no-store" },
      );
      const json = (await r.json().catch(() => ({}))) as ProposalsResponse;
      setData(json);
    } catch (exc) {
      setData({ error: String(exc) });
    }
  }, []);

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, POLL_MS);
    return () => clearInterval(t);
  }, [refresh]);

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
          Skill Curator
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

        {!data?.error && proposals.length === 0 && (
          <p className="text-xs" style={{ color: "var(--text-dim)" }}>
            No pending proposals. The curator runs weekly on lessons.jsonl
            and daily on merged-PR diffs (≥3 evidence rows per cluster).
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
