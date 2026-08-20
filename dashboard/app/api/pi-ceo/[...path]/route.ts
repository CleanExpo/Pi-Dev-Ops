// app/api/pi-ceo/[...path]/route.ts
// Proxy route: forwards requests to the Pi CEO FastAPI server.
// Handles auth transparently — clients never see Pi CEO credentials.
// SSE paths (/api/sessions/*/logs and /api/sessions/*/stream) are streamed without timeout.

const PI_CEO_URL = (process.env.PI_CEO_URL ?? "http://127.0.0.1:7777").replace(/\/$/, "");
const PI_CEO_PASSWORD = process.env.PI_CEO_PASSWORD ?? "";

const SSE_PATH_RE = /^\/api\/sessions\/[^/]+\/(?:logs(?:\/stream)?|stream)(?:\?|$)/;

// Module-level cookie cache — login once, reuse until 401
let _cookie: string | null = null;

function quietFallback(path: string, error: string, upstreamStatus = 502): Response {
  const now = new Date().toISOString();
  const headers = {
    "Content-Type": "application/json",
    "X-Upstream-Status": String(upstreamStatus),
  };

  if (path === "/health" || path === "/api/health") {
    return Response.json(
      { status: "unreachable", error, swarm_enabled: false, swarm_shadow: false },
      { status: 200, headers },
    );
  }

  if (path === "/api/sessions") {
    return Response.json([], { status: 200, headers });
  }

  if (path === "/api/projects/health") {
    return Response.json([], { status: 200, headers });
  }

  if (path === "/api/mission-control/live") {
    return Response.json(
      {
        ts: now,
        throughput: { hourly_24h: Array.from({ length: 24 }, () => 0) },
        active_sessions: [],
        recent_completions: [],
        queue: {
          urgent: 0,
          high: 0,
          next_issue_id: null,
          next_issue_title: error,
        },
        pulse: {
          last_at: null,
          comments_today: 0,
          pulse_issue_id: null,
        },
        observability: {
          source: "proxy_fallback",
          ok: false,
          fully_observed: false,
          red_components: ["pi_ceo_backend"],
          degraded_components: [],
          actions: [
            {
              component: "pi_ceo_backend",
              status: "red",
              ok: false,
              observed: false,
              owner: "Senior PM",
              severity: "high",
              next_action: "Restore Pi-CEO backend reachability before trusting Mission Control telemetry.",
              evidence_required: ["proxy route returns backend mission-control payload"],
              detail: error,
            },
          ],
        },
        error,
      },
      { status: 200, headers },
    );
  }

  if (path.startsWith("/api/routines")) {
    return Response.json({ runs: [], total: 0, error }, { status: 200, headers });
  }

  return Response.json({ error }, { status: 200, headers });
}

async function getAuthCookie(): Promise<string | null> {
  if (_cookie) return _cookie;
  try {
    const res = await fetch(`${PI_CEO_URL}/api/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password: PI_CEO_PASSWORD }),
    });
    if (!res.ok) return null;
    const setCookie = res.headers.get("set-cookie");
    if (!setCookie) return null;
    _cookie = setCookie.split(";")[0]; // "tao_session=<token>"
    return _cookie;
  } catch {
    return null;
  }
}

async function proxyRequest(method: string, path: string, body?: string): Promise<Response> {
  let cookie = await getAuthCookie();
  if (!cookie) {
    if (method === "GET") {
      return quietFallback(path, "Pi CEO server unreachable or wrong password");
    }
    return Response.json({ error: "Pi CEO server unreachable or wrong password" }, { status: 502 });
  }

  const headers: Record<string, string> = {
    Cookie: cookie,
    "Content-Type": "application/json",
  };

  const upstream = `${PI_CEO_URL}${path}`;

  // 10 s was too short for Railway cold-start — RA-1699 smoke test
  // (`GET /api/pi-ceo/api/routines?limit=1`) returned 502 because the
  // upstream container hadn't booted by the time AbortSignal fired.
  // Bumped to 25 s, which sits inside Vercel's default 30 s function
  // limit while giving Railway enough headroom for a cold boot.
  const doFetch = () =>
    fetch(upstream, { method, headers, body, signal: AbortSignal.timeout(25_000) });

  let res = await doFetch().catch(() => null);
  if (!res) {
    if (method === "GET") {
      return quietFallback(path, "Pi CEO server unreachable");
    }
    return Response.json({ error: "Pi CEO server unreachable" }, { status: 502 });
  }

  // On 401 — session cookie expired, re-login once
  if (res.status === 401) {
    _cookie = null;
    cookie = await getAuthCookie();
    if (!cookie) {
      if (method === "GET") {
        return quietFallback(path, "Pi CEO re-auth failed");
      }
      return Response.json({ error: "Pi CEO re-auth failed" }, { status: 502 });
    }
    headers.Cookie = cookie;
    res = (await doFetch().catch(() => null)) ?? res;
  }

  const data = await res.text();
  if (method === "GET" && res.status >= 400) {
    const fallback = quietFallback(path, data || `HTTP ${res.status}`, res.status);
    fallback.headers.set("X-Upstream-Status", String(res.status));
    return fallback;
  }

  return new Response(data, {
    status: res.status,
    headers: { "Content-Type": "application/json" },
  });
}

async function proxySse(path: string, clientSignal: AbortSignal): Promise<Response> {
  const cookie = await getAuthCookie();
  if (!cookie) {
    return Response.json({ error: "Pi CEO server unreachable or wrong password" }, { status: 502 });
  }

  const upstream = `${PI_CEO_URL}${path}`;
  const res = await fetch(upstream, {
    headers: { Cookie: cookie },
    signal: clientSignal,
  }).catch(() => null);

  if (!res || !res.body) {
    return Response.json({ error: "Pi CEO server unreachable" }, { status: 502 });
  }

  // Pass the upstream ReadableStream directly to the client
  return new Response(res.body, {
    status: res.status,
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      "X-Accel-Buffering": "no",
    },
  });
}

/**
 * Upstream path allowlist.
 *
 * This was a catch-all: any path under /api/pi-ceo/* was forwarded verbatim to
 * PI_CEO_URL, including /api/login. In a single shared-password system anything
 * holding that password — including the estate's own automation — could reach any
 * upstream route, and the fence intercepts tool calls rather than HTTP, so nothing
 * gated it.
 *
 * Derived from the paths the dashboard actually calls (19 distinct, enumerated from
 * source). Anything not listed is refused here rather than forwarded. Adding a route
 * upstream now requires adding it here too — deliberately, so the surface cannot grow
 * silently.
 *
 * RA-fix-allowed-upstream-gap: the original enumeration missed routes that pre-date
 * it and are still asserted by the E2E smoke suite's `auth: true` (post-login)
 * probes — those reach this gate directly (the `auth: false` probes never get past
 * proxy.ts's session check, so they never exercised this allowlist at all). Added
 * back: autonomy/integrations/nexus/health-endpoint reads, the Telegram webhook
 * intake path (called externally, so it was never in "what the dashboard calls"),
 * spec-pipeline/run, and the sessions logs/stream SSE alias + kill action.
 */
const ALLOWED_UPSTREAM: RegExp[] = [
  /^\/health$/,
  /^\/api\/health$/,
  /^\/api\/health\/obsidian$/,
  /^\/api\/health\/full$/,
  /^\/api\/sessions$/,
  /^\/api\/sessions\/[^/]+\/(logs(?:\/stream)?|stream|resume|kill)$/,
  /^\/api\/terminal\/(sessions|tail)$/,
  /^\/api\/projects\/health$/,
  /^\/api\/projects\/[^/]+\/findings$/,
  /^\/api\/routines$/,
  /^\/api\/mission-control\/live$/,
  /^\/api\/margot\/assets$/,
  /^\/api\/spec-pipeline$/,
  /^\/api\/spec-pipeline\/run$/,
  /^\/api\/scan$/,
  /^\/api\/build$/,
  /^\/api\/goal-ticket$/,
  /^\/api\/goal-ticket\/analyze$/,
  /^\/api\/autonomy\/status$/,
  /^\/api\/integrations\/health$/,
  /^\/api\/nexus\/health$/,
  /^\/api\/nexus\/ingest\/health$/,
  /^\/api\/telegram\/intake\/status$/,
  /^\/webhook\/telegram$/,
];

export function allowed(pathStr: string): boolean {
  // Compare the path only. A query string must never widen what is reachable.
  const bare = pathStr.split("?")[0];
  return ALLOWED_UPSTREAM.some((re) => re.test(bare));
}

function refuse(pathStr: string): Response {
  return new Response(
    JSON.stringify({
      error: "Upstream path not allowed",
      path: pathStr.split("?")[0],
      hint: "This proxy forwards an explicit allowlist. Add the route to ALLOWED_UPSTREAM if it is legitimate.",
    }),
    { status: 403, headers: { "content-type": "application/json" } }
  );
}

export async function GET(request: Request, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params;
  const url = new URL(request.url);
  const pathStr = "/" + path.join("/") + url.search;

  if (!allowed(pathStr)) return refuse(pathStr);

  if (SSE_PATH_RE.test(pathStr)) {
    return proxySse(pathStr, request.signal);
  }
  return proxyRequest("GET", pathStr);
}

export async function POST(request: Request, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params;
  const url = new URL(request.url);
  const pathStr = "/" + path.join("/") + url.search;

  if (!allowed(pathStr)) return refuse(pathStr);

  const body = await request.text();
  return proxyRequest("POST", pathStr, body);
}
