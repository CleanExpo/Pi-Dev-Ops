// app/api/auth/login/route.ts
// Browser-facing login: accepts password, calls FastAPI, forwards session cookie.

const PI_CEO_URL = (process.env.PI_CEO_URL ?? "http://127.0.0.1:7777").replace(/\/$/, "");

export async function POST(request: Request): Promise<Response> {
  let password: string;
  try {
    const body = await request.json();
    password = body.password ?? "";
  } catch {
    return Response.json({ error: "Invalid request body" }, { status: 400 });
  }

  let upstream: Response;
  try {
    upstream = await fetch(`${PI_CEO_URL}/api/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password }),
      signal: AbortSignal.timeout(5_000),
    });
  } catch {
    return Response.json({ error: "Pi CEO server unreachable" }, { status: 502 });
  }

  if (!upstream.ok) {
    return Response.json({ error: "Invalid password" }, { status: 401 });
  }

  // Forward the tao_session cookie from FastAPI to the browser
  const setCookie = upstream.headers.get("set-cookie");
  const res = Response.json({ ok: true }, { status: 200 });
  if (setCookie) {
    res.headers.set("set-cookie", setCookie);
  }
  return res;
}
