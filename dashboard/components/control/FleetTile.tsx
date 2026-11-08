// Fleet tile — UNI-2649. Reads the session-gated BFF, never /api/mesh/fleet.
"use client";

import type { FleetMachine, FleetView, RunnerView } from "@/lib/control/mesh-fleet";
import { displayState } from "@/lib/control/mesh-fleet";
import { brisbaneDateTime } from "@/lib/brisbane-time";
import { useSource } from "@/lib/boards/sources";

function fmtStamp(value: string | null | undefined): string {
  if (!value) return "never";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : brisbaneDateTime(date);
}

const UNKNOWN = "unknown";

/** Seconds as an age. The only value on this tile computed from elapsed time. */
function fmtAge(seconds: number | null): string {
  if (seconds === null || seconds < 0) return UNKNOWN;
  if (seconds < 120) return `${Math.round(seconds)}s ago`;
  if (seconds < 7200) return `${Math.round(seconds / 60)}m ago`;
  if (seconds < 172800) return `${Math.round(seconds / 3600)}h ago`;
  return `${Math.round(seconds / 86400)}d ago`;
}

function heartbeatAge(lastHeartbeat: string | null, checkedAt: string): string {
  const seen = lastHeartbeat ? Date.parse(lastHeartbeat) : Number.NaN;
  const now = Date.parse(checkedAt);
  return Number.isNaN(seen) || Number.isNaN(now) ? UNKNOWN : fmtAge((now - seen) / 1000);
}

function fmtUnix(ts: number | null): string {
  return ts === null ? UNKNOWN : fmtStamp(new Date(ts * 1000).toISOString());
}

function words(...parts: (string | null)[]): string {
  return parts.map((part) => part ?? UNKNOWN).join(" ");
}

/** "<blocker>; <next action>" as the runner wrote it (mesh/version_gate.py). Split, never reworded. */
function splitHold(reason: string | null): [string | null, string | null] {
  if (!reason) return [null, null];
  const cut = reason.indexOf("; ");
  return cut < 0 ? [reason, null] : [reason.slice(0, cut), reason.slice(cut + 2)];
}

function RunnerFacts({ runner }: { runner: RunnerView | null }) {
  const [blocker, next] = splitHold(runner?.holdReason ?? null);
  const update = runner?.lastUpdate;
  const job = runner?.lastJob;
  return (
    <>
      <span>running {runner?.version?.slice(0, 12) ?? UNKNOWN}</span>
      <span>approved {runner?.approvedVersion?.slice(0, 12) ?? UNKNOWN}</span>
      <span>match {runner?.versionStatus ?? UNKNOWN}</span>
      <span>task {runner?.currentTask ?? UNKNOWN}</span>
      <span>last update {update ? words(update.outcome, fmtUnix(update.ts)) : UNKNOWN}</span>
      <span>last job {job ? words(job.linearId, job.state, fmtUnix(job.ts)) : UNKNOWN}</span>
      <span>local edits {runner?.localEdits ?? UNKNOWN}</span>
      <span>blocker {blocker ?? UNKNOWN}</span>
      <span>next {next ?? UNKNOWN}</span>
    </>
  );
}

function MachineRow({ machine, claimsAvailable, checkedAt }: {
  machine: FleetMachine; claimsAvailable: boolean; checkedAt: string;
}) {
  const color = machine.stale ? "var(--warning)" : "var(--text)";
  return (
    <article className="flex flex-col gap-1 text-sm" style={{ color }} aria-label={machine.host}>
      <div className="flex items-center justify-between gap-2">
        <span className="font-medium truncate">{machine.host}</span>
        <span className="text-[10px] uppercase tracking-widest" style={{ color: "var(--text-dim)" }}>
          {machine.placeholder ? "cloud claim" : machine.stale ? "stale" : "fresh"}
        </span>
      </div>
      <div className="grid grid-cols-1 gap-0.5 text-xs" style={{ color: "var(--text-muted)" }}>
        <span>revision {machine.revision ?? "—"}</span>
        <span>heartbeat {machine.placeholder ? "none (cloud claim)" : heartbeatAge(machine.lastHeartbeat, checkedAt)}</span>
        <span>claim {machine.currentClaim ?? (claimsAvailable ? "none" : "unavailable")}</span>
        {!machine.placeholder && <span>state {displayState(machine)}</span>}
        {!machine.placeholder && <RunnerFacts runner={machine.runner} />}
      </div>
    </article>
  );
}

export default function FleetTile() {
  // RA-7898: one shared /api/mesh-fleet poller (20 s) for every Fleet on screen.
  const fleet = useSource<FleetView>("mesh-fleet");
  const view = fleet.seq > 0 ? fleet.value : null;

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
            <MachineRow
              key={machine.host}
              machine={machine}
              claimsAvailable={view.claimsAvailable === true}
              checkedAt={view.checkedAt}
            />
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
