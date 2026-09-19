/**
 * Server-side source for the Live Wall snapshot, with a short cache.
 *
 * A cached payload keeps the `generated_at` it was built with, so the browser's
 * freshness check still sees its true age.
 */
import { ceoBase, meshSecret, readMeshFleet } from "@/lib/control/mesh-upstream";
import { buildSnapshot, DEFAULT_FLEET_HOSTS, fleetPanel, type WallSnapshot } from "./snapshot";

const CACHE_MS = 4_000;
let cached: { at: number; body: WallSnapshot } | null = null;

function fleetHosts(): string[] {
  const raw = (process.env.WALL_FLEET_HOSTS ?? "").split(",").map((h) => h.trim()).filter(Boolean);
  return raw.length ? raw : DEFAULT_FLEET_HOSTS;
}

async function build(now: number): Promise<WallSnapshot> {
  const hosts = fleetHosts();
  const secret = meshSecret();
  const base = ceoBase();
  if (!secret) return buildSnapshot(fleetPanel(null, hosts, now, { kind: "no_source", reason: "NO LIVE SOURCE YET — mesh secret not configured on the dashboard" }), now);
  if (!base) return buildSnapshot(fleetPanel(null, hosts, now, { kind: "no_source", reason: "NO LIVE SOURCE YET — Pi-CEO URL not configured" }), now);
  const raw = await readMeshFleet(base, secret);
  if (raw === null) return buildSnapshot(fleetPanel(null, hosts, now, { kind: "broken", reason: "SOURCE BROKEN — upstream unreachable" }), now);
  return buildSnapshot(fleetPanel(raw, hosts, now), now);
}

/** Test hook: drop the module cache so each case builds fresh. */
export function _resetWallCache(): void {
  cached = null;
}

export async function getWallSnapshot(now: number = Date.now()): Promise<WallSnapshot> {
  if (!cached || now - cached.at > CACHE_MS) cached = { at: now, body: await build(now) };
  return cached.body;
}
