// Live Wall kiosk — docs/briefs/live-wall-v1.md. Polls the session-gated snapshot;
// the page never reloads. Freshness is judged from the payload's own generated_at.
"use client";

import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";

import {
  isSnapshotStale, nextStation, POLL_MS, resolveKioskMachine, rotationOrder, snapshotAgeSeconds,
} from "@/lib/wall/client";
import type { WallSnapshot } from "@/lib/wall/snapshot";
import { FleetTiles } from "./FleetTiles";
import { StationAccordion } from "./StationAccordion";
import { WallBanner } from "./WallBanner";
import { ChipBadge } from "./chips";

const ADVANCE_MS = 8_000;
const IDLE_RESUME_MS = 30_000;

function useSnapshot(): { snap: WallSnapshot | null; now: number } {
  const [snap, setSnap] = useState<WallSnapshot | null>(null);
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    let live = true;
    const tick = async () => {
      try {
        const res = await fetch("/api/mesh-fleet/wall", { cache: "no-store" });
        const body = (await res.json()) as WallSnapshot;
        if (live && res.ok && body && Array.isArray(body.stations)) setSnap(body);
      } catch {
        // Keep the last snapshot; its generated_at ages and greys the wall.
      }
      if (live) setNow(Date.now());
    };
    void tick();
    const t = setInterval(() => void tick(), POLL_MS);
    return () => { live = false; clearInterval(t); };
  }, []);
  return { snap, now };
}

function useRotation(order: string[]): { open: string | null; pick: (id: string) => void } {
  const [open, setOpen] = useState<string | null>(null);
  const pausedUntil = useRef(0);
  const key = order.join(",");
  useEffect(() => {
    const t = setInterval(() => {
      if (Date.now() < pausedUntil.current) return;
      setOpen((cur) => nextStation(order, cur !== null && order.includes(cur) ? cur : null));
    }, ADVANCE_MS);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- order is keyed by its contents
  }, [key]);
  const pick = (id: string) => { pausedUntil.current = Date.now() + IDLE_RESUME_MS; setOpen(id); };
  return { open, pick };
}

export function Wall() {
  const params = useSearchParams();
  const { snap, now } = useSnapshot();
  const { open, pick } = useRotation(snap ? rotationOrder(snap.stations) : []);
  if (!snap) {
    return <WallShell><WallBanner red={0} grey={0} staleAge="missing" /></WallShell>;
  }
  const stale = isSnapshotStale(snap.generated_at, now);
  const age = snapshotAgeSeconds(snap.generated_at, now);
  const kiosk = resolveKioskMachine(params.get("machine"), snap.fleet.machines.map((m) => m.host));
  return (
    <WallShell>
      <WallBanner red={snap.banner.red} grey={snap.banner.grey} staleAge={stale ? (age ?? "missing") : null} />
      {kiosk.unknown && (
        <div data-testid="unknown-machine" className="rounded-md px-4 py-3 text-xl" style={{ background: "#374151", color: "#fff" }}>
          <ChipBadge chip="GREY" /> unknown machine: {params.get("machine")}
        </div>
      )}
      <FleetTiles fleet={snap.fleet} stale={stale} kioskHost={kiosk.host} />
      <StationAccordion stations={snap.stations} open={open} stale={stale} onPick={pick} />
    </WallShell>
  );
}

function WallShell({ children }: { children: React.ReactNode }) {
  return (
    // Above the app shell's z-50 overlays (the Margot bubble covered a chip on the kiosk).
    <div className="fixed inset-0 overflow-y-auto overflow-x-hidden" style={{ background: "#030712", zIndex: 1000 }}>
      <div className="mx-auto flex max-w-[1800px] flex-col gap-6 p-8">{children}</div>
    </div>
  );
}
