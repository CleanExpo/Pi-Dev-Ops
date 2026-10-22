// lib/api-auth-policy.ts — which /api routes may be reached WITHOUT a pi_session.
//
// proxy.ts is deny-by-default for /api: every API request needs a valid session unless its
// exact path is listed here. This replaces the old allow-by-default PROTECTED_API_PREFIXES
// list, where a route was public unless someone remembered to add it — and /api/attachments,
// /api/flow-board and /api/margot/bubble each reached main unprotected that way.
//
// Rules for adding an entry:
//   - exact paths only, never a prefix (a new /api/webhook/x must not inherit an exemption);
//   - a reason, saying what authenticates the caller instead of the session;
//   - if that is a secret or signature, the handler must REFUSE when the secret is unset.
// __tests__/api-deny-default.test.ts probes every route.ts on disk against this list.

export const PUBLIC_API_ROUTES: Readonly<Record<string, string>> = {
  "/api/auth/login":
    "The login form itself: a caller has no session until this route issues one. Wrong password returns {ok:false} and sets no cookie.",
  "/api/revision":
    "Read-only deploy identity for smoke checks. Returns only a validated commit SHA or null; no credentials, no actions.",
  "/api/telegram":
    "Telegram webhook (Telegram cannot hold a session). Handler requires TELEGRAM_WEBHOOK_SECRET, constant-time; 403 when unset or absent.",
  "/api/webhook/github":
    "GitHub webhook. Handler verifies HMAC-SHA256 of the raw body; 401 when the webhook secret is unset.",
  "/api/webhook/intake":
    "Intake webhook. Handler requires X-Intake-Secret matching INTAKE_WEBHOOK_SECRET; 401 when unset or absent.",
  "/api/webhook/morning-intel":
    "Railway morning-intel webhook. Handler requires X-Pi-CEO-Secret matching WEBHOOK_SECRET; 503 when unset, 401 when wrong.",
  "/api/cron/analyze":
    "Vercel cron (vercel.json) carries no session. Handler requires Authorization: Bearer CRON_SECRET; 401 when unset or wrong.",
  "/api/kill-switch":
    "Scripted/remote callers use X-Kill-Switch-Secret instead of a session. Handler accepts a verified pi_session or that secret; 401 otherwise, fail-closed.",
};

function safeDecode(pathname: string): string {
  try {
    return decodeURIComponent(pathname);
  } catch {
    return pathname;
  }
}

/** True for anything that could route to app/api — compared decoded and case-folded, so it fails closed. */
export function isApiPath(pathname: string): boolean {
  const p = safeDecode(pathname).toLowerCase();
  return p === "/api" || p.startsWith("/api/");
}

/** True only for an exact public path (one trailing slash tolerated), compared as raw text. */
export function isPublicApiPath(pathname: string): boolean {
  const p = pathname.length > 1 && pathname.endsWith("/") ? pathname.slice(0, -1) : pathname;
  return Object.prototype.hasOwnProperty.call(PUBLIC_API_ROUTES, p);
}
