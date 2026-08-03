// app/api/kill-switch/route.ts — RA-1839: proxy /api/swarm/{status,kill,resume}
//
// Three operations on one route, switched by `?op=` query param:
//   GET  ?op=status            → forwards to GET  /api/swarm/status
//   POST ?op=kill              → forwards to POST /api/swarm/kill
//   POST ?op=resume            → forwards to POST /api/swarm/resume
//
// Why one route handler: the three Railway endpoints share auth + rate-limit
// shape; a single proxy keeps the dashboard surface tight. The frontend
// component decides which op to call based on user action.

import { createHash, timingSafeEqual } from "crypto";
import { verifySessionToken } from "@/lib/auth-secret";
import { piCeoFetch, isLockedOut } from "@/lib/pi-ceo-session";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

interface KillSwitchStatus {
  swarm_enabled_env: boolean;
  kill_switch_active: boolean;
  escalation_lock_active: boolean;
  panic_count_last_hour: number;
  approver_allowlist: string[];
  approver_totp_configured: string[];
}

function _baseUrl(): string | null {
  const raw = process.env.RAILWAY_URL ?? process.env.PI_CEO_URL;
  return raw ? raw.replace(/\/$/, "") : null;
}

// _authHeaders() was here until 2026-08-02. It attached `Authorization: Bearer
// ${PI_CEO_PASSWORD}` — a raw password where upstream requires a signed session token, so it
// authenticated nothing for 92 days while this route reported HTTP 200. Replaced by
// piCeoFetch(), which performs the login exchange upstream actually implements. See
// lib/pi-ceo-session.ts for why that helper is single-flight and lockout-aware.

function _quietStatus(error: string, detail?: string): Response {
  return Response.json(
    {
      error,
      detail,
      swarm_enabled_env: false,
      kill_switch_active: false,
      escalation_lock_active: false,
      panic_count_last_hour: 0,
      approver_allowlist: [],
      approver_totp_configured: [],
    },
    { status: 200 },
  );
}

export async function GET(request: Request): Promise<Response> {
  // 2026-08-02: this was unauthenticated. /api/kill-switch is in neither proxy prefix list, so
  // proxy() never looks at it, and the hotfix that closed POST left GET exactly as it found it.
  // Observed live returning HTTP 200 to an anonymous caller with a body proving it had reached
  // upstream — it only looked harmless because upstream happened to reject the credentials
  // this route attaches on the caller's behalf. Correct that misconfiguration and the same
  // anonymous GET begins returning internal swarm state.
  //
  // The previous justification was that "a CI smoke surface calls it unauthenticated by
  // design" — the smoke test's observed behaviour cited as the requirement. The question is
  // whether an anonymous caller SHOULD read swarm state through a credential it does not
  // hold. It should not, so the smoke surface was changed to assert 401, not this handler.
  if (!(await isAuthorised(request))) {
    return Response.json({ error: "Unauthorised" }, { status: 401 });
  }

  const { searchParams } = new URL(request.url);
  const op = searchParams.get("op") ?? "status";
  if (op !== "status") {
    return Response.json({ error: `unsupported GET op: ${op}` }, { status: 400 });
  }

  const base = _baseUrl();
  if (!base) {
    return _quietStatus("PI_CEO_URL / RAILWAY_URL not configured");
  }

  try {
    const upstream = await piCeoFetch("/api/swarm/status", {}, 5_000);
    if (!upstream) {
      // Could not obtain a session at all. Distinguish lockout from a bad credential — they
      // are different faults and were conflated for 92 days. A 429 lockout on shared Vercel
      // egress reads as an outage; reporting it as "wrong password" sends the next person
      // to rotate a credential that was never the problem.
      return _quietStatus(
        isLockedOut() ? "upstream login locked out (429)" : "could not authenticate upstream",
      );
    }
    const body = await upstream.json().catch(() => ({}));
    return Response.json(
      upstream.ok ? body : { error: `HTTP ${upstream.status}`, ...body },
      { status: 200, headers: { "X-Upstream-Status": String(upstream.status) } },
    );
  } catch (exc) {
    return _quietStatus("upstream unreachable", String(exc));
  }
}

/**
 * Authenticate ANY kill-switch call — read or mutate.
 *
 * /api/kill-switch is in NEITHER PROTECTED_API_PREFIXES nor PUBLIC_API_PREFIXES in proxy.ts,
 * so proxy() never examined it — and this route attaches Authorization: Bearer
 * PI_CEO_PASSWORD to its own upstream call. An anonymous POST could therefore kill the swarm,
 * or RESUME automation deliberately stopped, with no credential of any kind.
 *
 * Accepts a pi_session cookie (dashboard UI) or X-Kill-Switch-Secret matching
 * KILL_SWITCH_SECRET (scripted/remote), compared in constant time over digests.
 * FAIL-CLOSED: no session and no configured secret is 401.
 *
 * Named ...Mutation until 2026-08-02, which encoded the assumption that reads needed no
 * credential. Both methods reach upstream with the same borrowed credential, so both are
 * gated and the name no longer draws a distinction the route does not make.
 */
async function isAuthorised(request: Request): Promise<boolean> {
  const cookie = request.headers.get("cookie") ?? "";
  const m = /(?:^|;\s*)pi_session=([^;]+)/.exec(cookie);
  if (m) {
    // decodeURIComponent throws on malformed percent-encoding; a bad cookie must yield a
    // clean 401, not a handler error.
    let token = m[1];
    try { token = decodeURIComponent(token); } catch { /* raw value will simply not verify */ }
    if (await verifySessionToken(token)) return true;
  }

  const configured = (process.env.KILL_SWITCH_SECRET ?? "").trim();
  const presented = (request.headers.get("x-kill-switch-secret") ?? "").trim();
  if (!configured || !presented) return false;
  return timingSafeEqual(
    createHash("sha256").update(configured).digest(),
    createHash("sha256").update(presented).digest(),
  );
}

export async function POST(request: Request): Promise<Response> {
  if (!(await isAuthorised(request))) {
    // No detail about which credential was missing or wrong — that is a probing oracle.
    return Response.json({ error: "Unauthorised" }, { status: 401 });
  }
  const { searchParams } = new URL(request.url);
  const op = searchParams.get("op") ?? "";
  if (op !== "kill" && op !== "resume") {
    return Response.json(
      { error: `unsupported POST op: ${op} (use 'kill' or 'resume')` },
      { status: 400 },
    );
  }

  const base = _baseUrl();
  if (!base) {
    return Response.json(
      { error: "PI_CEO_URL / RAILWAY_URL not configured" },
      { status: 503 },
    );
  }

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return Response.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  try {
    const upstream = await piCeoFetch(
      `/api/swarm/${op}`,
      { method: "POST", body: JSON.stringify(body) },
      10_000,
    );
    if (!upstream) {
      // Mutations must NOT be quiet. A kill or resume that could not authenticate has to
      // surface loudly — the whole failure being fixed here is a safety control that
      // reported success-shaped output while doing nothing.
      return Response.json(
        {
          error: isLockedOut()
            ? "upstream login locked out (429) — this is an availability fault, not a bad credential"
            : "could not authenticate upstream — kill/resume did NOT take effect",
        },
        { status: 502 },
      );
    }
    const data = await upstream.json().catch(() => ({}));
    return Response.json(data, { status: upstream.status });
  } catch (exc) {
    return Response.json(
      { error: "upstream unreachable", detail: String(exc) },
      { status: 502 },
    );
  }
}
