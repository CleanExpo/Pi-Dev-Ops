/**
 * Server-only access to the Railway mesh snapshot (GET /api/mesh/fleet).
 *
 * The endpoint is secret-bearing (X-Pi-CEO-Secret), so only dashboard server routes
 * call this; the browser never holds the secret. A failed read returns null — callers
 * must render that as unavailable, never as an empty fleet.
 */

export function meshSecret(): string {
  return (process.env.TAO_INTERNAL_WEBHOOK_SECRET || process.env.TAO_WEBHOOK_SECRET || "").trim();
}

export function ceoBase(): string {
  return (process.env.RAILWAY_URL ?? process.env.PI_CEO_URL ?? "").replace(/\/$/, "").trim();
}

export async function readMeshFleet(base: string, secret: string): Promise<unknown | null> {
  const res = await fetch(`${base}/api/mesh/fleet`, {
    headers: { "X-Pi-CEO-Secret": secret },
    signal: AbortSignal.timeout(8_000),
    cache: "no-store",
  }).catch(() => null);
  if (!res || !res.ok) return null;
  return res.json().catch(() => null);
}
