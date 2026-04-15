// components/CeoHealthPanel.tsx — live system health for sidebar
"use client";

import { useEffect, useState } from "react";

interface HealthData {
  status: string;
  uptime_s: number;
  sessions: { active: number; total: number; max: number };
  claude_cli: boolean;
  anthropic_key: boolean;
  linear_key: boolean;
  autonomy: {
    enabled: boolean;
    armed: boolean;
    poll_count: number;
    seconds_since_last_poll: number | null;
  };
  disk_free_gb: number | null;
  swarm_enabled?: boolean;
  swarm_shadow?: boolean;
}

function formatUptime(s: number): string {
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`;
  return `${Math.floor(s / 86400)}d ${Math.floor((s % 86400) / 3600)}h`;
}

function formatPollAge(s: number | null): string {
  if (s === null) return "never";
  if (s < 60) return `${s}s ago`;
  return `${Math.floor(s / 60)}m ago`;
}

interface StatRowProps {
  label: string;
  value: string;
  dot?: "green" | "amber" | "red" | "dim";
}

function StatRow({ label, value, dot }: StatRowProps) {
  const dotColor =
    dot === "green" ? "var(--success)" :
    dot === "amber" ? "var(--warning)" :
    dot === "red"   ? "var(--error)"   : "var(--text-dim)";

  return (
    <div className="flex items-center justify-between gap-2 py-0.5">
      <span className="text-[10px] leading-none" style={{ color: "var(--text-dim)" }}>
        {label}
      </span>
      <div className="flex items-center gap-1.5 shrink-0">
        {dot && (
          <span
            className="w-1.5 h-1.5 rounded-full shrink-0"
            style={{ background: dotColor }}
          />
        )}
        <span
          className="text-[10px] font-mono leading-none"
          style={{ color: "var(--text-muted)" }}
        >
          {value}
        </span>
      </div>
    </div>
  );
}

export default function CeoHealthPanel() {
  const [health, setHealth] = useState<HealthData | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    async function fetchHealth() {
      try {
        const res = await fetch("/api/pi-ceo/health");
        if (res.ok) {
          setHealth(await res.json() as HealthData);
          setError(false);
        } else {
          setError(true);
        }
      } catch {
        setError(true);
      }
    }

    void fetchHealth();
    const t = setInterval(() => { void fetchHealth(); }, 30_000);
    return () => clearInterval(t);
  }, []);

  // ── Error / loading states ────────────────────────────────────────────────
  if (error) {
    return (
      <div className="flex items-center gap-2 px-4 py-3" style={{ borderTop: "1px solid var(--border)" }}>
        <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ background: "var(--error)" }} />
        <span className="text-[10px]" style={{ color: "var(--text-muted)" }}>Backend unreachable</span>
      </div>
    );
  }

  if (!health) {
    return (
      <div className="flex items-center gap-2 px-4 py-3" style={{ borderTop: "1px solid var(--border)" }}>
        <span className="w-1.5 h-1.5 rounded-full shrink-0 animate-pulse" style={{ background: "var(--text-dim)" }} />
        <span className="text-[10px]" style={{ color: "var(--text-dim)" }}>Connecting…</span>
      </div>
    );
  }

  // ── Derived values ────────────────────────────────────────────────────────
  const ok = health.status === "ok";
  const swarmOn = health.swarm_enabled !== false;
  const swarmShadow = health.swarm_shadow === true;
  const autonomyArmed = health.autonomy.armed;

  const swarmLabel = !swarmOn ? "Off" : swarmShadow ? "Shadow" : "Active";
  const swarmDot: "green" | "amber" | "red" =
    !swarmOn ? "red" : swarmShadow ? "amber" : "green";

  return (
    <div
      className="px-4 pt-2.5 pb-3 shrink-0 flex flex-col gap-0.5"
      style={{ borderTop: "1px solid var(--border)" }}
    >
      {/* Header row */}
      <div className="flex items-center justify-between mb-1">
        <span className="text-[10px] font-semibold uppercase tracking-wider" style={{ color: "var(--text-dim)" }}>
          System
        </span>
        <span
          className="text-[9px] font-mono px-1.5 py-0.5 rounded"
          style={{
            background: ok ? "rgba(34,197,94,0.12)" : "rgba(239,68,68,0.12)",
            color: ok ? "var(--success)" : "var(--error)",
          }}
        >
          {ok ? "OK" : "DEGRADED"}
        </span>
      </div>

      <StatRow label="Uptime" value={formatUptime(health.uptime_s)} dot={ok ? "green" : "red"} />
      <StatRow
        label="Builds"
        value={`${health.sessions.active} active / ${health.sessions.max} max`}
        dot={health.sessions.active > 0 ? "green" : "dim"}
      />
      <StatRow
        label="Swarm"
        value={swarmLabel}
        dot={swarmDot}
      />
      <StatRow
        label="Autonomy"
        value={autonomyArmed ? "Armed" : "Disarmed"}
        dot={autonomyArmed ? "green" : "amber"}
      />
      <StatRow
        label="Last poll"
        value={formatPollAge(health.autonomy.seconds_since_last_poll)}
      />
      {health.disk_free_gb !== null && (
        <StatRow
          label="Disk free"
          value={`${health.disk_free_gb} GB`}
          dot={health.disk_free_gb < 10 ? "amber" : "dim"}
        />
      )}
    </div>
  );
}
