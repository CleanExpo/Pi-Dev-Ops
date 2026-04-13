/**
 * proxy.ts — Next.js 16 network-boundary proxy.
 * Node.js runtime required (crypto.subtle, Buffer).
 *
 * 1. Auth: verifies pi_session HMAC cookie — no Railway dependency.
 *    Unauthenticated page requests redirect to login.
 *    Unauthenticated API requests return 401.
 *
 * 2. CSP nonce: generates a per-request nonce, injects it into
 *    Content-Security-Policy and forwards it via x-nonce header.
 *
 * style-src retains 'unsafe-inline' — xterm.js injects CSS at runtime.
 */
import { NextRequest, NextResponse } from "next/server";

export const config = {
  matcher: [
    // All routes except static assets and Next.js internals
    "/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)",
  ],
};

const DASHBOARD_PASSWORD = process.env.PI_CEO_PASSWORD ?? "";
const SESSION_TTL_SECONDS = 86_400; // 24h — must match login/route.ts
const COOKIE_NAME = "pi_session";
const LOGIN_PATH = "/";

const PROTECTED_PAGE_PREFIXES = [
  "/dashboard",
  "/builds",
  "/chat",
  "/settings",
  "/history",
  "/projects",
];

const PROTECTED_API_PREFIXES = [
  "/api/pi-ceo",
  "/api/sessions",
  "/api/analyze",
  "/api/actions",
  "/api/capabilities",
  "/api/chat",
  "/api/settings",
];

// Public API routes — never require session
const PUBLIC_API_PREFIXES = [
  "/api/auth/",
  "/api/telegram",
  "/api/webhook/",
];

async function verifySession(token: string): Promise<boolean> {
  if (!DASHBOARD_PASSWORD || !token) return false;
  const dot = token.indexOf(".");
  if (dot === -1) return false;

  const issuedAtStr = token.slice(0, dot);
  const sig = token.slice(dot + 1);
  const issuedAt = parseInt(issuedAtStr, 10);
  if (isNaN(issuedAt)) return false;

  const age = Math.floor(Date.now() / 1000) - issuedAt;
  if (age < 0 || age > SESSION_TTL_SECONDS) return false;

  const enc = new TextEncoder();
  const cryptoKey = await crypto.subtle.importKey(
    "raw",
    enc.encode(DASHBOARD_PASSWORD),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const expected = await crypto.subtle.sign("HMAC", cryptoKey, enc.encode(issuedAtStr));
  const expectedHex = Array.from(new Uint8Array(expected))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");

  return expectedHex === sig;
}

function buildCsp(nonce: string): string {
  const isDev = process.env.NODE_ENV === "development";
  return [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}' 'wasm-unsafe-eval'${isDev ? " 'unsafe-eval'" : ""}`,
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
    "font-src 'self' https://fonts.gstatic.com",
    "connect-src 'self' https://api.github.com https://api.anthropic.com https://api.linear.app https://*.vercel.app https://*.supabase.co wss://*.supabase.co",
    "worker-src blob:",
    "img-src 'self' data: blob:",
    "frame-ancestors 'none'",
  ].join("; ");
}

export async function proxy(req: NextRequest): Promise<NextResponse | Response> {
  const { pathname } = req.nextUrl;

  // ── Auth ───────────────────────────────────────────────────────────────────
  const isProtectedPage = PROTECTED_PAGE_PREFIXES.some((p) => pathname.startsWith(p));
  const isPublicApi = PUBLIC_API_PREFIXES.some((p) => pathname.startsWith(p));
  const isProtectedApi = !isPublicApi && PROTECTED_API_PREFIXES.some((p) => pathname.startsWith(p));

  if (isProtectedPage || isProtectedApi) {
    const token = req.cookies.get(COOKIE_NAME)?.value ?? "";
    const valid = await verifySession(token);

    if (!valid) {
      if (isProtectedApi) {
        return Response.json({ error: "Unauthorised" }, { status: 401 });
      }
      const loginUrl = new URL(LOGIN_PATH, req.url);
      loginUrl.searchParams.set("redirect", pathname);
      return NextResponse.redirect(loginUrl);
    }
  }

  // ── CSP nonce ──────────────────────────────────────────────────────────────
  const nonce = Buffer.from(crypto.randomUUID()).toString("base64");
  const csp = buildCsp(nonce);

  const requestHeaders = new Headers(req.headers);
  requestHeaders.set("x-nonce", nonce);

  const response = NextResponse.next({ request: { headers: requestHeaders } });
  response.headers.set("Content-Security-Policy", csp);

  return response;
}
