// Fleet tile — UNI-2649. Reads the session-gated BFF, never /api/mesh/fleet.
"use client";

import { useEffect, useState } from "react";

import type { FleetMachine, FleetView } from "@/lib/control/mesh-fleet";

const POLL_MS = 20_000;

function fmtStamp(value: string | null | undefined): string {
  if (!value) return "never";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

async function loadFleet(): Promise<FleetView> {
  try {
    const res = await fetch("/api/mesh-fleet", { cache: "no-store" });
    const body = (await res.json().catch(() => null)) as FleetView | null;
    if (body && body.status === "ok") return body;
    if (body && body.status === "unavailable") return body;
  } catch {
    /* fall through */
  }
  return {
    status: "unavailable",
    checkedAt: new Date().toISOString(),
    reason: "fleet read failed",
  };
}

function MachineRow({ machine }: { machine: FleetMachine }) {
  const color = machine.stale ? "var(--warning)" : "var(--text)";
  return (
    <article className="flex flex-col gap-1 text-sm" style={{ color }}>
      <div className="flex items-center justify-between gap-2">
        <span className="font-medium truncate">{machine.host}</span>
        <span className="text-[10px] uppercase tracking-widest" style={{ color: "var(--text-dim)" }}>
          {machine.stale ? "stale" : "fresh"}
        </span>
      </div>
      <div className="grid grid-cols-1 gap-0.5 text-xs" style={{ color: "var(--text-muted)" }}>
        <span>revision {machine.revision ?? "—"}</span>
        <span>heartbeat {fmtStamp(machine.lastHeartbeat)}</span>
        <span>claim {machine.currentClaim ?? "none"}</span>
      </div>
    </article>
  );
}

export default function FleetTile() {
  const [view, setView] = useState<FleetView | null>(null);

  useEffect(() => {
    let cancelled = false;
    const refresh = async () => {
      const next = await loadFleet();
      if (!cancelled) setView(next);
    };
    void refresh();
    const timer = setInterval(() => { void refresh(); }, POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, []);

  return (
    <section
      className="flex flex-col min-h-0"
      style={{ background: "var(--panel)", border: "1px solid var(--border)", borderRadius: 8 }}
      aria-label="Fleet"
    >
      <header className="px-4 py-2.5" style={{ borderBottom: "1px solid var(--border)" }}>
        <h2 className="text-xs font-semibold uppercase tracking-widest" style={{ color: "var(--text-muted)" }}>
          Fleet
        </h2>
      </header>
      <div className="flex-1 overflow-auto p-4 flex flex-col gap-3 min-h-0">
        {!view ? (
          <p className="text-sm" style={{ color: "var(--text-dim)" }}>Loading…</p>
        ) : view.status === "unavailable" ? (
          <p className="text-sm" style={{ color: "var(--error)" }}>
            unavailable — {view.reason}
          </p>
        ) : view.machines.length === 0 ? (
          <p className="text-sm" style={{ color: "var(--text-dim)" }}>No machines enrolled.</p>
        ) : (
          view.machines.map((machine) => (
            <MachineRow key={machine.host} machine={machine} />
          ))
        )}
        {view && (
          <p className="text-[11px] tabular-nums" style={{ color: "var(--text-dim)" }}>
            checked {fmtStamp(view.checkedAt)}
          </p>
        )}
      </div>
    </section>
  );
}
