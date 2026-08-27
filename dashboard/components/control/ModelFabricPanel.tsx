"use client";

import { useEffect, useMemo, useState } from "react";
import ModelBadge from "./ModelBadge";

type Lane = { model: string; banned: boolean };
type LastCall = {
  ts: number;
  role: string;
  lane: string;
  requested_model: string;
  served_model: string;
  provider: string;
  latency_ms: number;
  ok: boolean;
  error?: string | null;
};
type FabricStatus = {
  enabled: boolean;
  healthy: boolean;
  base_url?: string;
  allowed_roles?: string[];
  lanes?: Record<string, Lane>;
  models_available?: number;
  last_call?: LastCall | null;
  totals?: { calls: number; failures: number };
  blocked?: string[];
  error?: string | null;
};

function dot(ok: boolean): string {
  return ok ? "●" : "○";
}

export default function ModelFabricPanel() {
  const [data, setData] = useState<FabricStatus | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const res = await fetch("/api/model-fabric", { cache: "no-store" });
        const body = (await res.json()) as FabricStatus;
        if (!cancelled) setData(body);
      } catch (error) {
        if (!cancelled) {
          setData({ enabled: false, healthy: false, error: error instanceof Error ? error.message : "Unavailable" });
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void load();
    const timer = setInterval(() => void load(), 15_000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, []);

  const failureRate = useMemo(() => {
    const calls = data?.totals?.calls ?? 0;
    const failures = data?.totals?.failures ?? 0;
    return calls ? Math.round((failures / calls) * 100) : 0;
  }, [data]);

  const lanes = Object.entries(data?.lanes ?? {});
  const last = data?.last_call;

  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1.7fr)_minmax(280px,0.8fr)]">
      <section
        className="min-w-0"
        style={{ background: "var(--panel)", border: "1px solid var(--border)", borderRadius: 8 }}
        aria-label="Mission Control Model Fabric"
      >
        <header className="flex items-center justify-between px-4 py-3" style={{ borderBottom: "1px solid var(--border)" }}>
          <div>
            <div className="text-[10px] font-semibold uppercase tracking-[0.18em]" style={{ color: "var(--text-dim)" }}>
              Mission Control · Model Fabric
            </div>
            <h2 className="text-base font-semibold" style={{ color: "var(--text)" }}>Governed routing</h2>
          </div>
          <div className="text-xs font-mono" style={{ color: data?.healthy ? "var(--success)" : "var(--error)" }}>
            {dot(Boolean(data?.healthy))} {data?.healthy ? "HEALTHY" : data?.enabled ? "DEGRADED" : "DISABLED"}
          </div>
        </header>

        <div className="p-4 flex flex-col gap-4">
          {loading && <p className="text-xs" style={{ color: "var(--text-dim)" }}>Loading model fabric…</p>}

          {!loading && data?.error && (
            <div className="rounded p-3 text-xs font-mono" style={{ color: "var(--error)", border: "1px solid var(--border)" }}>
              {data.error}
            </div>
          )}

          <div className="grid gap-3 sm:grid-cols-3">
            <Metric label="Models visible" value={String(data?.models_available ?? 0)} />
            <Metric label="Fabric calls" value={String(data?.totals?.calls ?? 0)} />
            <Metric label="Failure rate" value={`${failureRate}%`} />
          </div>

          <div>
            <div className="text-[10px] uppercase tracking-wider mb-2" style={{ color: "var(--text-dim)" }}>Routing lanes</div>
            <div className="grid gap-2 sm:grid-cols-2">
              {lanes.map(([name, lane]) => (
                <div key={name} className="rounded p-3" style={{ background: "var(--panel-hover)", border: "1px solid var(--border)" }}>
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-xs font-semibold" style={{ color: "var(--text)" }}>{name}</span>
                    <span className="text-[10px] font-mono" style={{ color: lane.banned ? "var(--error)" : "var(--success)" }}>
                      {lane.banned ? "BLOCKED" : "APPROVED"}
                    </span>
                  </div>
                  <div className="text-[10px] font-mono mt-1 break-all" style={{ color: "var(--text-muted)" }}>{lane.model}</div>
                </div>
              ))}
            </div>
          </div>

          <div>
            <div className="text-[10px] uppercase tracking-wider mb-2" style={{ color: "var(--text-dim)" }}>Latest route</div>
            <div className="rounded p-3" style={{ background: "var(--panel-hover)", border: "1px solid var(--border)" }}>
              {last ? (
                <div className="grid gap-1 text-xs font-mono" style={{ color: "var(--text-muted)" }}>
                  <div><strong style={{ color: "var(--text)" }}>{last.role}</strong> → {last.lane}</div>
                  <div>requested: {last.requested_model}</div>
                  <div>served: {last.served_model || "unknown"}</div>
                  <div>provider: {last.provider || "unknown"} · {last.latency_ms} ms</div>
                  <div style={{ color: last.ok ? "var(--success)" : "var(--error)" }}>{last.ok ? "PASS" : last.error ?? "FAILED"}</div>
                </div>
              ) : (
                <div className="text-xs" style={{ color: "var(--text-dim)" }}>No routed call recorded since this Pi-CEO process started.</div>
              )}
            </div>
          </div>

          <div className="flex flex-wrap gap-2">
            {(data?.blocked ?? []).map((name) => (
              <span key={name} className="px-2 py-1 rounded text-[10px] font-mono uppercase" style={{ color: "var(--error)", border: "1px solid var(--border)" }}>
                {name} blocked
              </span>
            ))}
          </div>
        </div>
      </section>

      <ModelBadge />
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded p-3" style={{ background: "var(--panel-hover)", border: "1px solid var(--border)" }}>
      <div className="text-[10px] uppercase tracking-wider" style={{ color: "var(--text-dim)" }}>{label}</div>
      <div className="text-xl font-semibold mt-1" style={{ color: "var(--text)" }}>{value}</div>
    </div>
  );
}
