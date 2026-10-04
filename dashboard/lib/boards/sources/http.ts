// RA-7898 — the one GET helper the direct (non-proxy) feeds share.
//
// Mirrors what each panel did before the move: `cache: "no-store"`, and a
// body that fails to parse is `null`, never an exception. A network error or
// abort comes back as `{ error }` so every reader can turn it into a state.

export interface HttpResult {
  /** Present when a response arrived. */
  status?: number;
  ok?: boolean;
  body?: unknown;
  /** Present when no response arrived (network error, abort): `String(exc)`. */
  error?: string;
  /** The exception's own message, for panels that showed `e.message`. */
  message?: string;
}

export async function getJson(url: string, signal: AbortSignal): Promise<HttpResult> {
  try {
    const res = await fetch(url, { cache: "no-store", signal });
    const body = await res.json().catch(() => null);
    return { status: typeof res.status === "number" ? res.status : undefined, ok: res.ok, body };
  } catch (exc) {
    return { error: String(exc), message: exc instanceof Error ? exc.message : String(exc) };
  }
}

export function record(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>) : null;
}

/**
 * A body's `error` as display text. Absent stays absent; anything that is not
 * a string becomes `fallback`, so a panel is never handed an object to render.
 */
export function errorText(value: unknown, fallback: string): string | undefined {
  if (value === undefined || value === null || value === "") return undefined;
  return typeof value === "string" ? value : fallback;
}

/** "not configured" in a quiet-failure `error` means configuration is absent, not a fault. */
export function isNotConfigured(error: unknown): boolean {
  return typeof error === "string" && /not configured/i.test(error);
}
