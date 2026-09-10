// The one honest reader of the Pi-CEO proxy.
//
// The proxy never fails loudly on a GET. When the backend is unreachable,
// `quietFallback` (app/api/pi-ceo/[...path]/route.ts) returns **HTTP 200** with
// a placeholder body — empty arrays, zeroed counters, absent fields — and
// stamps the real upstream status on `X-Upstream-Status`. Its success path
// never sets that header.
//
// So `res.ok` is true when the backend is dead, and a client that checks only
// `res.ok` renders placeholders as measurements. That is not a hypothetical:
// the Loop Cockpit turned an absent `enabled` field into the on-screen claim
// "Autonomy poller is disabled (TAO_AUTONOMY_ENABLED=0)" — naming a specific
// env var as the cause of an outage nothing had observed.
//
// Rule this enforces: **a failed read is never returned as a successful read
// that found nothing.** `null` means "the backend did not answer". Callers
// must render that as unknown, never as zero, empty, healthy or disabled.

export type ProxyResult<T> =
  | { ok: true; data: T }
  | { ok: false; reason: "unreachable" | "http" | "network"; upstreamStatus: number | null };

/** True when this response is a synthesised placeholder, not backend data. */
export function isProxyFallback(res: Response): boolean {
  return res.headers.get("X-Upstream-Status") !== null;
}

/**
 * Fetch a Pi-CEO endpoint through the proxy.
 *
 * Returns `null` when the backend did not answer — including the case where
 * the proxy answered 200 on its behalf. Use when the caller only needs
 * "data or nothing".
 */
export async function fetchProxyJSON<T>(path: string): Promise<T | null> {
  const r = await fetchProxy<T>(path);
  return r.ok ? r.data : null;
}

/**
 * As above, but says WHY there is no data, so a panel can distinguish
 * "backend down" from "you are logged out" when it wants to.
 */
export async function fetchProxy<T>(path: string): Promise<ProxyResult<T>> {
  try {
    const res = await fetch(`/api/pi-ceo${path}`);
    if (isProxyFallback(res)) {
      const raw = res.headers.get("X-Upstream-Status");
      const parsed = raw === null ? null : Number.parseInt(raw, 10);
      return {
        ok: false,
        reason: "unreachable",
        upstreamStatus: Number.isNaN(parsed as number) ? null : parsed,
      };
    }
    if (!res.ok) return { ok: false, reason: "http", upstreamStatus: res.status };
    return { ok: true, data: (await res.json()) as T };
  } catch {
    return { ok: false, reason: "network", upstreamStatus: null };
  }
}
