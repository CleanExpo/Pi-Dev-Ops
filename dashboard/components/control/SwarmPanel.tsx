// components/control/SwarmPanel.tsx — Panel 1: swarm state + autonomous PR progress (RA-1092)
"use client";

import { useEffect, useState } from "react";

interface SwarmStatus {
  state: "SHADOW" | "ACTIVE" | "RATE_LIMITED" | "OFF";
  autonomous_prs_today: number;
  autonomous_prs_limit: number;
  green_merges: number;
  green_merges_target: number;
  last_pr_ts: string | null;
  last_pr_url: string | null;
}

const STATE_COLOUR: Record<SwarmStatus["state"], string> = {
  ACTIVE: "var(--success)",
  SHADOW: "var(--warning)",
  RATE_LIMITED: "var(--error)",
  OFF: "var(--text-dim)",
};

function fmtTs(ts: string | null): string {
  if (!ts) return "never";
  try {
    const d = new Date(ts);
    return d.toLocaleString(undefined, {
      month: "short",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return ts;
  }
}

export default function SwarmPanel() {
  const [data, setData] = useState<SwarmStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const res = await fetch("/api/swarm-status");
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const json = (await res.json()) as SwarmStatus;
        if (!cancelled) {
          setData(json);
          setError(null);
        }
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "Failed to load swarm status");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void load();
    const t = setInterval(() => void load(), 30_000);
    return () => {
      cancelled = true;
      clearInterval(t);
    };
  }, []);

  const prPct = data
    ? Math.min(100, Math.round((data.autonomous_prs_today / Math.max(1, data.autonomous_prs_limit)) * 100))
    : 0;
  const mergePct = data
    ? Math.min(100, Math.round((data.green_merges / Math.max(1, data.green_merges_target)) * 100))
    : 0;

  return (
    <section
      className="flex flex-col h-full"
      style={{ background: "var(--panel)", border: "1px solid var(--border)", borderRadius: 8 }}
      aria-label="Swarm status"
    >
      <header
        className="flex items-center justify-between px-4 py-2.5"
        style={{ borderBottom: "1px solid var(--border)" }}
      >
        <h2 className="text-xs font-semibold uppercase tracking-widest" style={{ color: "var(--text-muted)" }}>
          Swarm Status
        </h2>
        {data && (
          <span
            className="text-[10px] font-mono uppercase px-2 py-0.5 rounded"
            style={{
              color: STATE_COLOUR[data.state],
              background: "var(--panel-hover)",
              border: `1px solid ${STATE_COLOUR[data.state]}33`,
            }}
          >
            {data.state}
          </span>
        )}
      </header>

      <div className="flex-1 overflow-auto p-4 space-y-4">
        {loading && (
          <p className="text-xs" style={{ color: "var(--text-dim)" }}>
            Loading…
          </p>
        )}

        {error && !loading && (
          <p className="text-xs" style={{ color: "var(--error)" }}>
            {error}
          </p>
        )}

        {data && !loading && (
          <>
            {/* Autonomous PRs today */}
            <div>
              <div className="flex items-center justify-between mb-1">
                <span className="text-[11px]" style={{ color: "var(--text-dim)" }}>
                  Autonomous PRs today
                </span>
                <span className="text-xs font-mono" style={{ color: "var(--text)" }}>
                  {data.autonomous_prs_today} / {data.autonomous_prs_limit}
                </span>
              </div>
              <div
                className="w-full h-1.5 rounded-full overflow-hidden"
                style={{ background: "var(--border)" }}
                role="progressbar"
                aria-valuenow={prPct}
                aria-valuemin={0}
                aria-valuemax={100}
              >
                <div
                  className="h-full transition-all"
                  style={{ width: `${prPct}%`, background: "var(--accent)" }}
                />
              </div>
            </div>

            {/* Green merge progress */}
            <div>
              <div className="flex items-center justify-between mb-1">
                <span className="text-[11px]" style={{ color: "var(--text-dim)" }}>
                  Green merges
                </span>
                <span className="text-xs font-mono" style={{ color: "var(--text)" }}>
                  {data.green_merges} / {data.green_merges_target}
                </span>
              </div>
              <div
                className="w-full h-1.5 rounded-full overflow-hidden"
                style={{ background: "var(--border)" }}
                role="progressbar"
                aria-valuenow={mergePct}
                aria-valuemin={0}
                aria-valuemax={100}
              >
                <div
                  className="h-full transition-all"
                  style={{ width: `${mergePct}%`, background: "var(--success)" }}
                />
              </div>
            </div>

            {/* Last autonomous PR */}
            <div className="pt-2" style={{ borderTop: "1px solid var(--border)" }}>
              <div className="text-[11px] mb-1" style={{ color: "var(--text-dim)" }}>
                Last autonomous PR
              </div>
              {data.last_pr_url ? (
                <a
                  href={data.last_pr_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs font-mono inline-flex items-center gap-1 hover:underline"
                  style={{ color: "var(--accent)" }}
                >
                  <span>{fmtTs(data.last_pr_ts)}</span>
                  <span aria-hidden="true">↗</span>
                </a>
              ) : (
                <span className="text-xs font-mono" style={{ color: "var(--text-muted)" }}>
                  {fmtTs(data.last_pr_ts)}
                </span>
              )}
            </div>
          </>
        )}
      </div>
    </section>
  );
}
