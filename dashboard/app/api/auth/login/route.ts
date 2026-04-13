// app/api/auth/login/route.ts
// Vercel-native auth — no Railway dependency.
// Password is checked against DASHBOARD_PASSWORD env var directly.
// Session token = HMAC-SHA256(key=DASHBOARD_PASSWORD, data=issuedAt) stored as
// an httpOnly Secure cookie. Rotating the password instantly invalidates all sessions.

// DASHBOARD_PASSWORD = human-facing login (what you type on the landing page).
// PI_CEO_PASSWORD    = machine-to-machine secret (Vercel proxy → Railway backend).
// These must be SEPARATE: PI_CEO_PASSWORD is a random 30-char secret that no human
// should be expected to type. Set DASHBOARD_PASSWORD in Vercel env to whatever
// password you want to use on the login screen.
const DASHBOARD_PASSWORD =
  process.env.DASHBOARD_PASSWORD ||
  process.env.PI_CEO_PASSWORD ||
  "";
const SESSION_TTL_SECONDS = 86_400; // 24 hours
const COOKIE_NAME = "pi_session";

async function hmac(key: string, data: string): Promise<string> {
  const enc = new TextEncoder();
  const cryptoKey = await crypto.subtle.importKey(
    "raw",
    enc.encode(key),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const sig = await crypto.subtle.sign("HMAC", cryptoKey, enc.encode(data));
  return Array.from(new Uint8Array(sig))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

export async function POST(request: Request): Promise<Response> {
  if (!DASHBOARD_PASSWORD) {
    return Response.json(
      { error: "DASHBOARD_PASSWORD env var not set on Vercel" },
      { status: 503 },
    );
  }

  let password: string;
  try {
    const body = await request.json();
    password = body.password ?? "";
  } catch {
    return Response.json({ error: "Invalid request body" }, { status: 400 });
  }

  // Constant-time comparison via HMAC to prevent timing attacks
  const expectedHmac = await hmac(DASHBOARD_PASSWORD, "auth-check");
  const submittedHmac = await hmac(password, "auth-check");
  if (expectedHmac !== submittedHmac) {
    return Response.json({ error: "Invalid password" }, { status: 401 });
  }

  // Issue session token: "issuedAt.hmac(issuedAt)"
  const issuedAt = Math.floor(Date.now() / 1000).toString();
  const sig = await hmac(DASHBOARD_PASSWORD, issuedAt);
  const token = `${issuedAt}.${sig}`;

  const isSecure = request.url.startsWith("https://");
  const cookieHeader = [
    `${COOKIE_NAME}=${token}`,
    `Path=/`,
    `HttpOnly`,
    isSecure ? "Secure" : "",
    `SameSite=Strict`,
    `Max-Age=${SESSION_TTL_SECONDS}`,
  ]
    .filter(Boolean)
    .join("; ");

  return new Response(JSON.stringify({ ok: true }), {
    status: 200,
    headers: {
      "Content-Type": "application/json",
      "Set-Cookie": cookieHeader,
    },
  });
}
