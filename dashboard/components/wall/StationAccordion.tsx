// Seven-station accordion. Colour survives collapse: a RED or GREY station shows its
// colour in the header even when closed. Only detail is hidden.
import { displayChip } from "@/lib/wall/client";
import type { Station } from "@/lib/wall/snapshot";
import { CHIP_BG, ChipBadge } from "./chips";

export function StationAccordion({
  stations, open, stale, onPick,
}: { stations: Station[]; open: string | null; stale: boolean; onPick: (id: string) => void }) {
  return (
    <section className="flex flex-col gap-2">
      <h2 className="text-2xl font-semibold" style={{ color: "#e5e7eb" }}>Stations</h2>
      {stations.map((s) => {
        const chip = displayChip(s.chip, stale);
        const expanded = s.id === open;
        return (
          <div key={s.id} data-testid={`station-${s.id}`} data-chip={chip} className="rounded-lg" style={{ border: `2px solid ${CHIP_BG[chip]}` }}>
            <button
              type="button"
              onClick={() => onPick(s.id)}
              aria-expanded={expanded}
              className="flex w-full items-center justify-between px-5 py-3 text-left text-2xl font-semibold"
              style={{ background: chip === "GREEN" ? "#0b1220" : CHIP_BG[chip], color: "#fff" }}
            >
              <span>{s.name}</span>
              <ChipBadge chip={chip} />
            </button>
            {expanded && (
              <p className="px-5 py-4 text-xl" style={{ color: "#e5e7eb", background: "#0b1220" }}>{s.reason}</p>
            )}
          </div>
        );
      })}
    </section>
  );
}
