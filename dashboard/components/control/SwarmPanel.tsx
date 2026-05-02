// components/control/SwarmPanel.tsx — Panel 1: swarm state + autonomous PR progress (RA-1092)
// RA-1839 — Kill-switch panel embedded after the PR progress block.
"use client";

import { useEffect, useState } from "react";
import ProgressRing from "./ProgressRing";
import KillSwitchPanel from "./KillSwitchPanel";

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
    return new Date(ts).toLocaleString(undefined, {
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
      {/* Amber pulse keyframe — injected once */}
      <style>{`
        @keyframes pi-swarm-pulse {
          0%, 100% { box-shadow: 0 0 0 0 rgba(249,115,22,0.55); }
          60%       { box-shadow: 0 0 0 7px rgba(249,115,22,0); }
        }
        @keyframes pi-dot-pulse {
          0%, 100% { opacity: 1; }
          50%       { opacity: 0.35; }
        }
      `}</style>

      <header
        className="flex items-center justify-between px-4 py-2.5"
        style={{ borderBottom: "1px solid var(--border)" }}
      >
        <h2 className="text-xs font-semibold uppercase tracking-widest" style={{ color: "var(--text-muted)" }}>
          Swarm
        </h2>
        {data && (
          <span
            className="text-[10px] font-mono uppercase px-2 py-0.5 rounded"
            style={{
              color: STATE_COLOUR[data.state],
              background: "var(--panel-hover)",
              border: `1px solid ${STATE_COLOUR[data.state]}33`,
              animation: data.state === "ACTIVE" ? "pi-swarm-pulse 2.2s ease-in-out infinite" : undefined,
            }}
          >
            {/* Pulsing dot only for ACTIVE */}
            {data.state === "ACTIVE" && (
              <span
                aria-hidden="true"
                style={{
                  display: "inline-block",
                  width: 6,
                  height: 6,
                  borderRadius: "50%",
                  background: STATE_COLOUR[data.state],
                  marginRight: 5,
                  verticalAlign: "middle",
                  animation: "pi-dot-pulse 1.4s ease-in-out infinite",
                }}
              />
            )}
            {data.state}
          </span>
        )}
      </header>

      <div className="flex-1 overflow-auto p-4 flex flex-col gap-4">
        {loading && (
          <p className="text-xs" style={{ color: "var(--text-dim)" }}>
            Loading…
          </p>
        )}

        {error && !loading && (
          <p className="text-xs font-mono" style={{ color: "var(--error)" }}>
            <span aria-hidden="true">⚠ </span>{error}
          </p>
        )}

        {/* RA-1839 — Kill-switch must mount independently of swarm-status fetch
            so the operator can halt even when /api/autonomy/status is down. */}
        {!loading && (error || !data) && <KillSwitchPanel />}

        {data && !loading && (
          <>
            {/* Progress rings row */}
            <div className="flex items-center justify-around pt-1">
              <div className="flex flex-col items-center gap-1.5">
                <ProgressRing
                  value={prPct}
                  size={80}
                  colour="var(--accent)"
                  label={`${data.autonomous_prs_today}/${data.autonomous_prs_limit}`}
                  sublabel="PRs today"
                />
                <span className="text-[10px]" style={{ color: "var(--text-dim)" }}>
                  Autonomous PRs
                </span>
              </div>

              <div className="w-px self-stretch" style={{ background: "var(--border)" }} aria-hidden="true" />

              <div className="flex flex-col items-center gap-1.5">
                <ProgressRing
                  value={mergePct}
                  size={80}
                  colour="var(--success)"
                  label={`${data.green_merges}/${data.green_merges_target}`}
                  sublabel="merges"
                />
                <span className="text-[10px]" style={{ color: "var(--text-dim)" }}>
                  Green merges
                </span>
              </div>
            </div>

            {/* Last autonomous PR */}
            <div className="pt-3" style={{ borderTop: "1px solid var(--border)" }}>
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

            {/* RA-1839 — Kill-switch status + Halt/Resume controls */}
            <KillSwitchPanel />
          </>
        )}
      </div>
    </section>
  );
}
