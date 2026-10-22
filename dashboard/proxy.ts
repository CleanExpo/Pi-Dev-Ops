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

// Secret resolution lives in lib/auth-secret.ts so this verifier and the
// cookie signer (app/api/auth/login/route.ts) stay in sync. Edit there to
// change behaviour.
import { verifySessionToken } from "./lib/auth-secret";
import { isApiPath, isPublicApiPath } from "./lib/api-auth-policy";

export const config = {
  matcher: [
    // Every /api path, whatever it ends in. The static-asset exclusion below must never reach
    // /api: "/api/pi-ceo/api/build%3F.png" skipped proxy() entirely and reached a handler
    // with no session.
    "/api/:path*",
    // All other routes except static assets and Next.js internals
    "/((?!api/|_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)",
  ],
};

const SESSION_TTL_SECONDS = 86_400; // 24h — must match login/route.ts
const COOKIE_NAME = "pi_session";
const LOGIN_PATH = "/";

const PROTECTED_PAGE_PREFIXES = [
  "/control",
  // RA-6862: /loop (Loop Cockpit) is data-only — every panel reads /api/pi-ceo/*,
  // which 401s without a session, so an unauthenticated visit is a bare shell.
  // Protect it so unauthenticated users are redirected to login instead.
  // (/overview and /brain are intentionally public shells — see the brain-page
  // smoke surface entry — so they are deliberately NOT protected here.)
  "/loop",
  "/dashboard",
  "/health",
  "/builds",
  "/chat",
  "/settings",
  "/history",
  "/projects",
  // The command-centre pages read wiki_pages through a SERVICE-ROLE client that
  // bypasses RLS, and the ported wiki-graph page declares a delta against the
  // `auth gate` rule on the grounds that "auth is enforced upstream by proxy.ts".
  // That was true of the matcher and false of the enforcement: the matcher covers
  // every non-static route, but proxy() only checks a session for a path listed
  // here. Until this line existed, the whole knowledge base was readable without
  // one. See __tests__/command-centre-auth-coverage.test.ts.
  "/command-centre",
  // UNI-2666: Placecards prototype is Mission Control, not a public demo.
  // The .html alias also matches this prefix.
  "/placecards-prototype",
];

// API auth is DENY-BY-DEFAULT: every /api request needs a valid session unless its exact
// path is on PUBLIC_API_ROUTES in lib/api-auth-policy.ts, each with a written reason.
// Until this inversion the proxy was allow-by-default (PROTECTED_API_PREFIXES): a route was
// public unless someone remembered to list it, and /api/attachments, /api/flow-board and
// /api/margot/bubble each reached main unprotected that way. A new route is now protected
// the moment it exists. See __tests__/api-deny-default.test.ts.

// Verification lives in lib/auth-secret.ts and is imported, NOT reimplemented here.
//
// Round-1 review caught this: the brief claimed the verifier was "shared with proxy.ts" while
// proxy kept its own local copy — two implementations of the check that decides whether a
// request is authenticated, in the one module written because two callers once diverged on
// exactly this. The local copy also lacked the shared function's try/catch, so a crypto
// failure threw instead of returning false.

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
  const isProtectedApi = isApiPath(pathname) && !isPublicApiPath(pathname);

  if (isProtectedPage || isProtectedApi) {
    const token = req.cookies.get(COOKIE_NAME)?.value ?? "";
    const valid = await verifySessionToken(token, SESSION_TTL_SECONDS);

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
  const nonce = btoa(crypto.randomUUID()); // btoa works in Edge runtime; Buffer does not
  const csp = buildCsp(nonce);

  const requestHeaders = new Headers(req.headers);
  requestHeaders.set("x-nonce", nonce);

  const response = NextResponse.next({ request: { headers: requestHeaders } });
  response.headers.set("Content-Security-Policy", csp);

  return response;
}