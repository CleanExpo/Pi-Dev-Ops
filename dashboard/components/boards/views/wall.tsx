"use client";
// RA-7898 — the wall's three pieces as board views. FleetTiles, StationAccordion
// and WallBanner are unchanged; these wrappers hand them the same props Wall.tsx
// computes, from the shared `wall` source instead of Wall's own poll.

import { useState } from "react";

import { FleetTiles } from "@/components/wall/FleetTiles";
import { StationAccordion } from "@/components/wall/StationAccordion";
import { WallBanner } from "@/components/wall/WallBanner";
import { useSource } from "@/lib/boards/sources";
import type { ViewProps } from "@/lib/boards/registry/types";
import { useNow } from "@/lib/boards/use-now";
import { displayedCounts, isSnapshotStale, resolveKioskMachine, snapshotAgeSeconds } from "@/lib/wall/client";
import type { WallSnapshot } from "@/lib/wall/snapshot";

function useWall(): { snap: WallSnapshot | null; stale: boolean; age: number | null } {
  const source = useSource<WallSnapshot | null>("wall");
  const now = useNow(1_000);
  const snap = source.value ?? source.lastGood;
  if (!snap) return { snap: null, stale: true, age: null };
  return { snap, stale: isSnapshotStale(snap.generated_at, now), age: snapshotAgeSeconds(snap.generated_at, now) };
}

export function WallFleetView({ kioskHost }: ViewProps) {
  const { snap, stale } = useWall();
  if (!snap) return null;
  const kiosk = resolveKioskMachine(kioskHost ?? null, snap.fleet.machines.map((m) => m.host));
  return <FleetTiles fleet={snap.fleet} stale={stale} kioskHost={kiosk.host} />;
}

export function WallStationsView() {
  const { snap, stale } = useWall();
  const [open, setOpen] = useState<string | null>(null);
  if (!snap) return null;
  return <StationAccordion stations={snap.stations} open={open} stale={stale} onPick={(id) => setOpen(open === id ? null : id)} />;
}

export function WallBannerView({ kioskHost }: ViewProps) {
  const { snap, stale, age } = useWall();
  if (!snap) return <WallBanner red={0} grey={0} staleAge="missing" />;
  const kiosk = resolveKioskMachine(kioskHost ?? null, snap.fleet.machines.map((m) => m.host));
  return <WallBanner {...displayedCounts(snap, stale, kiosk.unknown)} staleAge={stale ? (age ?? "missing") : null} />;
}
