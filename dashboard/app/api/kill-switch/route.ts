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

function _authHeaders(): Record<string, string> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (process.env.PI_CEO_PASSWORD) {
    headers.Authorization = `Bearer ${process.env.PI_CEO_PASSWORD}`;
  }
  return headers;
}

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
    const upstream = await fetch(`${base}/api/swarm/status`, {
      headers: _authHeaders(),
      signal: AbortSignal.timeout(5_000),
      cache: "no-store",
    });
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
 * Authenticate a MUTATING kill-switch call.
 *
 * Until 2026-08-02 POST had NO inbound check at all. `/api/kill-switch` is in neither
 * PROTECTED_API_PREFIXES nor PUBLIC_API_PREFIXES in proxy.ts, so it fell straight through the
 * proxy's auth block. That made an anonymous POST able to kill OR RESUME the swarm — and the
 * route supplies `Authorization: Bearer PI_CEO_PASSWORD` on the upstream call itself, so the
 * caller needed no credential of any kind. A confused deputy on a safety control.
 *
 * `resume` is the sharper end: it can restart automation the founder deliberately stopped.
 *
 * Two accepted credentials, because this control has two legitimate callers:
 *   · a `pi_session` cookie — the founder using the dashboard UI
 *   · `X-Kill-Switch-Secret` matching KILL_SWITCH_SECRET — scripted or remote use, where
 *     there is no browser session to carry. Compared with timingSafeEqual over digests, the
 *     same shape /api/webhook/github and /api/webhook/intake already use.
 *
 * FAIL-CLOSED. No session and no configured secret means 401, not "allow". That does cost an
 * abort axis while KILL_SWITCH_SECRET is unset — deliberately: an unauthenticated `resume` is
 * strictly worse than an HTTP kill path that is temporarily unavailable, and it is not the
 * only abort axis (RA-1966 wires a cost ceiling, a hard-stop file and an iteration cap).
 *
 * GET ?op=status is deliberately NOT gated: it is read-only, rejects any other op with 400,
 * and the CI smoke surface calls it unauthenticated by design.
 */
async function isAuthorisedMutation(request: Request): Promise<boolean> {
  const cookie = request.headers.get("cookie") ?? "";
  const m = /(?:^|;\s*)pi_session=([^;]+)/.exec(cookie);
  if (m && (await verifySessionToken(decodeURIComponent(m[1])))) return true;

  const configured = (process.env.KILL_SWITCH_SECRET ?? "").trim();
  const presented = (request.headers.get("x-kill-switch-secret") ?? "").trim();
  if (!configured || !presented) return false;
  // Hash both sides first so timingSafeEqual never throws on a length mismatch.
  return timingSafeEqual(
    createHash("sha256").update(configured).digest(),
    createHash("sha256").update(presented).digest(),
  );
}

export async function POST(request: Request): Promise<Response> {
  if (!(await isAuthorisedMutation(request))) {
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
    const upstream = await fetch(`${base}/api/swarm/${op}`, {
      method: "POST",
      headers: _authHeaders(),
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(10_000),
    });
    const data = await upstream.json().catch(() => ({}));
    return Response.json(data, { status: upstream.status });
  } catch (exc) {
    return Response.json(
      { error: "upstream unreachable", detail: String(exc) },
      { status: 502 },
    );
  }
}
