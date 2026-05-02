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

export async function GET(request: Request): Promise<Response> {
  const { searchParams } = new URL(request.url);
  const op = searchParams.get("op") ?? "status";
  if (op !== "status") {
    return Response.json({ error: `unsupported GET op: ${op}` }, { status: 400 });
  }

  const base = _baseUrl();
  if (!base) {
    return Response.json(
      { error: "PI_CEO_URL / RAILWAY_URL not configured" },
      { status: 503 },
    );
  }

  try {
    const upstream = await fetch(`${base}/api/swarm/status`, {
      headers: _authHeaders(),
      signal: AbortSignal.timeout(5_000),
      cache: "no-store",
    });
    const body = await upstream.json().catch(() => ({}));
    return Response.json(body, { status: upstream.status });
  } catch (exc) {
    return Response.json(
      { error: "upstream unreachable", detail: String(exc) },
      { status: 502 },
    );
  }
}

export async function POST(request: Request): Promise<Response> {
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
