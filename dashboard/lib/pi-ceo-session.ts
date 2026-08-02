/**
 * Authenticated access to the Pi CEO upstream — the ONLY correct credential path.
 *
 * WHY THIS EXISTS
 *
 * Four routes (kill-switch, zte, swarm-status, curator-proposals) sent
 * `Authorization: Bearer ${PI_CEO_PASSWORD}` — a raw password where upstream requires a
 * SIGNED SESSION TOKEN. `app/server/auth.py::require_auth` accepts a `tao_session` cookie or
 * `Bearer <session-token>`, and both branches run `verify_session_token`, which needs
 * `data.sig` HMAC'd over SESSION_SECRET plus an `exp` claim. A password fails the
 * `rsplit(".", 1)` length check on the first line, so it could never authenticate for any
 * value of the password.
 *
 * The upstream requirement predates the dashboard code by 25 days (2026-04-07 vs 2026-05-02),
 * so this never worked — there is no "when it broke". Observed 2026-08-02:
 * `GET /api/kill-switch?op=status` returned `X-Upstream-Status: 401` to production traffic,
 * and zte/swarm-status silently served fallback values. The kill switch has had no working
 * outbound leg for 92 days.
 *
 * The correct exchange already existed in this repo, in `pi-ceo/[...path]`: POST the password
 * to `/api/login`, keep the `tao_session` cookie, send it as `Cookie:`. This module is that
 * pattern, extracted — not invented.
 *
 * SURVIVOR REVIEW — READ BEFORE TRUSTING THIS FILE
 *
 * Consolidation does not average quality; it promotes the survivor's weaknesses to every
 * caller. This helper is now load-bearing for four routes including a SAFETY CONTROL, so it
 * is reviewed as new code rather than inherited as already-reviewed. Two properties the
 * single-route original did not need, and which consolidation creates:
 *
 *   1. SINGLE-FLIGHT LOGIN. The original served one route; a burst produced a few duplicate
 *      logins at worst. Four routes — three of them polled by dashboard panels — can now
 *      stampede. `/api/login` locks out an IP after 5 failures in 15 minutes, and Vercel
 *      egress IPs are SHARED, so a stampede of failing logins is capable of locking out the
 *      whole deployment. A concurrency bug here is not a performance problem, it is an
 *      availability attack on ourselves. Hence one in-flight login, shared by all waiters.
 *
 *   2. LOCKOUT AWARENESS. On 429 we stop and cool down rather than retry. Retrying into a
 *      lockout deepens it and converts an auth fault into an outage — which is exactly how
 *      this class of failure gets misdiagnosed as "the credential is wrong".
 *
 * Deliberately NOT handled: refreshing before expiry. A 401 triggers exactly one re-login,
 * which is the same contract the original had and is sufficient.
 */

const PI_CEO_URL = (process.env.RAILWAY_URL ?? process.env.PI_CEO_URL ?? "http://127.0.0.1:7777")
  .replace(/\/$/, "");

/** Module-level, so it is per-instance in serverless — not shared state across the fleet. */
let _cookie: string | null = null;
/** The single in-flight login. All concurrent callers await this one promise. */
let _loginInFlight: Promise<string | null> | null = null;
/** Epoch ms until which we refuse to attempt login, set when upstream reports lockout. */
let _cooldownUntil = 0;

function password(): string {
  // Trim: Vercel env pulls can carry a trailing newline, which would silently fail every login.
  return (process.env.PI_CEO_PASSWORD ?? "").trim();
}

async function login(): Promise<string | null> {
  if (Date.now() < _cooldownUntil) return null;

  const pw = password();
  if (!pw) return null;

  try {
    const res = await fetch(`${PI_CEO_URL}/api/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password: pw }),
      signal: AbortSignal.timeout(8_000),
    });

    if (res.status === 429) {
      // Upstream lockout (5 failures / 15 min per IP). Backing off is mandatory: retrying
      // extends the window, and on shared egress that denies the dashboard to everyone.
      _cooldownUntil = Date.now() + 15 * 60_000;
      console.warn("[pi-ceo-session] upstream login LOCKED OUT (429) — backing off 15m");
      return null;
    }
    if (!res.ok) {
      // 401 here means the password is wrong or upstream regenerated its own credential
      // (config.py invents one when TAO_PASSWORD is unset). Never log the value.
      console.warn(`[pi-ceo-session] login rejected: HTTP ${res.status}`);
      return null;
    }

    const setCookie = res.headers.get("set-cookie");
    if (!setCookie) return null;
    _cookie = setCookie.split(";")[0]; // "tao_session=<token>"
    return _cookie;
  } catch {
    return null;
  }
}

/** Cached cookie, or one shared login attempt for all concurrent callers. */
async function authCookie(): Promise<string | null> {
  if (_cookie) return _cookie;
  if (!_loginInFlight) {
    _loginInFlight = login().finally(() => { _loginInFlight = null; });
  }
  return _loginInFlight;
}

/**
 * Fetch an upstream path with a valid session. Returns null when the request could not be
 * made authenticated at all, so callers keep their existing quiet-fallback behaviour rather
 * than inventing a new error surface.
 */
export async function piCeoFetch(
  path: string,
  init: RequestInit = {},
  timeoutMs = 8_000,
): Promise<Response | null> {
  let cookie = await authCookie();
  if (!cookie) return null;

  const doFetch = (c: string) =>
    fetch(`${PI_CEO_URL}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init.headers ?? {}), Cookie: c },
      signal: AbortSignal.timeout(timeoutMs),
      cache: "no-store",
    });

  let res = await doFetch(cookie).catch(() => null);
  if (!res) return null;

  // Expired session — drop it and re-login exactly once.
  if (res.status === 401) {
    _cookie = null;
    cookie = await authCookie();
    if (!cookie) return res;
    res = (await doFetch(cookie).catch(() => null)) ?? res;
  }
  return res;
}

/** True when upstream is currently refusing logins for lockout. Lets callers report an
 *  availability fault instead of misreporting it as a credential fault. */
export function isLockedOut(): boolean {
  return Date.now() < _cooldownUntil;
}
