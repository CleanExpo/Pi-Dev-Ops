/**
 * proxy.ts — Next.js auth + CSP nonce proxy (RA-519, RA-518)
 *
 * 1. Auth: redirects unauthenticated requests for protected routes to login.
 *    Cookie presence check only — HMAC verification is enforced server-side.
 *
 * 2. CSP nonce: generates a per-request nonce, injects it into the
 *    Content-Security-Policy header (removing 'unsafe-inline' from script-src),
 *    and forwards it to the app via x-nonce request header so layout.tsx can
 *    apply it to any inline scripts Next.js needs for hydration.
 *
 * style-src retains 'unsafe-inline' — xterm.js injects CSS at runtime and
 * cannot be nonce'd without patching the library.
 */
import { NextRequest, NextResponse } from "next/server";

const LOGIN_PATH = "/";

const PROTECTED_PREFIXES = [
  "/dashboard",
  "/builds",
  "/chat",
  "/settings",
  "/history",
  "/projects",
];

function buildCsp(nonce: string): string {
  const isDev = process.env.NODE_ENV === "development";
  return [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}' 'wasm-unsafe-eval'${isDev ? " 'unsafe-eval'" : ""}`,
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
    "font-src 'self' https://fonts.gstatic.com",
    "connect-src 'self' https://api.github.com https://api.anthropic.com https://*.vercel.app https://*.supabase.co wss://*.supabase.co",
    "worker-src blob:",
    "img-src 'self' data: blob:",
    "frame-ancestors 'none'",
  ].join("; ");
}

export function proxy(req: NextRequest): NextResponse {
  const { pathname } = req.nextUrl;

  // ── Auth redirect ──────────────────────────────────────────────────────────
  const isProtected = PROTECTED_PREFIXES.some((p) => pathname.startsWith(p));
  if (isProtected) {
    const session = req.cookies.get("tao_session");
    if (!session?.value) {
      const loginUrl = new URL(LOGIN_PATH, req.url);
      loginUrl.searchParams.set("redirect", pathname);
      return NextResponse.redirect(loginUrl);
    }
  }

  // ── CSP nonce ──────────────────────────────────────────────────────────────
  const nonce = Buffer.from(crypto.randomUUID()).toString("base64");
  const csp = buildCsp(nonce);

  // Forward nonce to server components via request header
  const requestHeaders = new Headers(req.headers);
  requestHeaders.set("x-nonce", nonce);

  const response = NextResponse.next({ request: { headers: requestHeaders } });
  response.headers.set("Content-Security-Policy", csp);

  return response;
}

export const config = {
  matcher: [
    // Run on all pages except static assets and Next.js internals
    "/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)",
  ],
};
