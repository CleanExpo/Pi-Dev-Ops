// Fleet view — one tile per declared machine. Every value here is self-reported.
import { displayChip } from "@/lib/wall/client";
import type { FleetPanel, MachineTile } from "@/lib/wall/snapshot";
import { ChipBadge, fmtAge } from "./chips";

function Tile({ m, stale, mine }: { m: MachineTile; stale: boolean; mine: boolean }) {
  const chip = displayChip(m.chip, stale);
  return (
    <div
      data-testid={`machine-${m.host}`}
      className="flex flex-col gap-2 rounded-lg p-5"
      style={{ background: "#111827", border: mine ? "3px solid #93c5fd" : "1px solid #374151" }}
    >
      <div className="flex items-center justify-between gap-3">
        <span className="text-2xl font-semibold" style={{ color: "#f9fafb" }}>{m.host}</span>
        <ChipBadge chip={chip} />
      </div>
      <span className="text-lg" style={{ color: "#d1d5db" }}>
        {m.reason} · {fmtAge(m.ageSeconds)}
        {m.load1 !== null && ` · load ${m.load1.toFixed(1)}`}
      </span>
      {m.agents.map((a) => (
        <span key={a.runtime} className="text-base" style={{ color: "#9ca3af" }}>
          <ChipBadge chip={displayChip(a.chip, stale)} label={a.runtime} /> {a.state} · {fmtAge(a.ageSeconds)}
        </span>
      ))}
      <span className="text-xs uppercase tracking-widest" style={{ color: "#6b7280" }}>self-reported</span>
    </div>
  );
}

export function FleetTiles({ fleet, stale, kioskHost }: { fleet: FleetPanel; stale: boolean; kioskHost: string | null }) {
  return (
    <section className="flex flex-col gap-3">
      <h2 className="text-2xl font-semibold" style={{ color: "#e5e7eb" }}>Fleet</h2>
      {fleet.status !== "ok" && (
        <div data-testid="fleet-source" className="rounded-md px-4 py-3 text-xl" style={{ background: "#374151", color: "#f3f4f6" }}>
          {fleet.reason}
        </div>
      )}
      <div className="grid gap-4" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))" }}>
        {fleet.machines.map((m) => <Tile key={m.host} m={m} stale={stale} mine={m.host === kioskHost} />)}
      </div>
      {fleet.others.length > 0 && (
        <p className="text-sm" style={{ color: "#6b7280" }}>Also reporting, not in the fleet: {fleet.others.join(", ")}</p>
      )}
    </section>
  );
}
