// app/api/pi-ceo/[...path]/route.ts
// Proxy route: forwards requests to the Pi CEO FastAPI server.
// Handles auth transparently — clients never see Pi CEO credentials.

const PI_CEO_URL = (process.env.PI_CEO_URL ?? "http://127.0.0.1:7777").replace(/\/$/, "");
const PI_CEO_PASSWORD = process.env.PI_CEO_PASSWORD ?? "";

// Module-level cookie cache — login once, reuse until 401
let _cookie: string | null = null;

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
    return Response.json({ error: "Pi CEO server unreachable or wrong password" }, { status: 502 });
  }

  const headers: Record<string, string> = {
    Cookie: cookie,
    "Content-Type": "application/json",
  };

  const upstream = `${PI_CEO_URL}${path}`;

  const doFetch = () =>
    fetch(upstream, { method, headers, body, signal: AbortSignal.timeout(10_000) });

  let res = await doFetch().catch(() => null);
  if (!res) {
    return Response.json({ error: "Pi CEO server unreachable" }, { status: 502 });
  }

  // On 401 — session cookie expired, re-login once
  if (res.status === 401) {
    _cookie = null;
    cookie = await getAuthCookie();
    if (!cookie) {
      return Response.json({ error: "Pi CEO re-auth failed" }, { status: 502 });
    }
    headers.Cookie = cookie;
    res = (await doFetch().catch(() => null)) ?? res;
  }

  const data = await res.text();
  return new Response(data, {
    status: res.status,
    headers: { "Content-Type": "application/json" },
  });
}

export async function GET(request: Request, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params;
  const url = new URL(request.url);
  const pathStr = "/" + path.join("/") + url.search;
  return proxyRequest("GET", pathStr);
}

export async function POST(request: Request, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params;
  const url = new URL(request.url);
  const pathStr = "/" + path.join("/") + url.search;
  const body = await request.text();
  return proxyRequest("POST", pathStr, body);
}
