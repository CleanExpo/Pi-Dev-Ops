// lib/auth-secret.ts — single source of truth for the dashboard auth secret.
//
// Both app/api/auth/login/route.ts (which signs cookies) and proxy.ts (which
// validates them) MUST resolve the secret the same way, otherwise login
// succeeds but every protected page redirects back to login. Before this
// module the two callers had subtly different logic — login fell back to
// "dev" in non-production while proxy returned an empty string, causing a
// redirect loop in any local-dev session without a .env.local.
//
// This module is the only place that decision lives. Edit here, both
// callers stay in sync.

interface ResolvedSecret {
  /** The secret used to sign + verify session HMACs. */
  value: string;
  /** True when running with the "dev" fallback. */
  dev: boolean;
  /** Reason the real env var was unusable (logged once at startup). */
  reason: "ok" | "unset" | "unresolved-1password";
}

/**
 * Resolve the dashboard auth secret.
 *
 * Priority:
 *   1. DASHBOARD_PASSWORD (preferred — human-facing login secret)
 *   2. PI_CEO_PASSWORD (fallback — same secret reused for backend auth)
 *   3. Dev fallback "dev" — ONLY in non-production builds
 *
 * Vercel-specific quirks handled:
 *   - .trim() to drop trailing newlines that the Vercel CLI sometimes adds
 *   - "op://..." prefix detection — unresolved 1Password CLI references
 *     that the Vercel CLI creates by default when you `vercel env pull`.
 *     These are TREATED AS IF UNSET and trigger the dev fallback.
 */
export function resolvePassword(): ResolvedSecret {
  const raw = (process.env.DASHBOARD_PASSWORD || process.env.PI_CEO_PASSWORD || "").trim();

  if (raw && !raw.startsWith("op://")) {
    return { value: raw, dev: false, reason: "ok" };
  }

  const reason: ResolvedSecret["reason"] = raw.startsWith("op://")
    ? "unresolved-1password"
    : "unset";

  if (process.env.NODE_ENV !== "production") {
    return { value: "dev", dev: true, reason };
  }

  // Production with no usable secret — return empty so callers can refuse
  // to authenticate and surface the misconfiguration instead of silently
  // accepting the dev fallback.
  return { value: "", dev: false, reason };
}

/** Bare value, for callers that just need the HMAC key. */
export function authSecret(): string {
  return resolvePassword().value;
}

/**
 * Verify a `pi_session` token: `<issuedAtSeconds>.<hexHmacSha256(issuedAt)>`.
 *
 * This lives here, next to `resolvePassword`, for the reason this module exists at all:
 * two callers once resolved the secret differently and login succeeded while every
 * protected page bounced. Verification is now about to have two callers too — `proxy.ts`
 * and `/api/kill-switch` — so it is defined once rather than copied and left to drift.
 *
 * Returns false for anything malformed, expired, or signed with a different secret. It
 * never throws, so a caller cannot accidentally treat a thrown error as "authenticated".
 */
export async function verifySessionToken(
  token: string,
  ttlSeconds = 86_400,
): Promise<boolean> {
  const secret = resolvePassword().value;
  if (!secret || !token) return false;

  const dot = token.indexOf(".");
  if (dot === -1) return false;

  const issuedAtStr = token.slice(0, dot);
  const sig = token.slice(dot + 1);
  const issuedAt = parseInt(issuedAtStr, 10);
  if (Number.isNaN(issuedAt)) return false;

  const age = Math.floor(Date.now() / 1000) - issuedAt;
  if (age < 0 || age > ttlSeconds) return false;

  try {
    const enc = new TextEncoder();
    const key = await crypto.subtle.importKey(
      "raw",
      enc.encode(secret),
      { name: "HMAC", hash: "SHA-256" },
      false,
      ["sign"],
    );
    const expected = await crypto.subtle.sign("HMAC", key, enc.encode(issuedAtStr));
    const expectedHex = Array.from(new Uint8Array(expected))
      .map((b) => b.toString(16).padStart(2, "0"))
      .join("");
    return expectedHex === sig;
  } catch {
    return false;
  }
}
