// app/api/attachments/upload/route.ts — RA-7487 fail-closed upload gate.
//
// Auth is checked before the body is read. This handler does not mint Drive
// credentials and does not accept caller bytes. The drive/attachments feature
// is out of scope; the hole was an unauthenticated path that looked successful.

import { verifySessionToken } from "@/lib/auth-secret";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const SESSION_TTL_SECONDS = 86_400;

function sessionTokenFrom(request: Request): string {
  const cookie = request.headers.get("cookie") ?? "";
  const match = /(?:^|;\s*)pi_session=([^;]+)/.exec(cookie);
  if (!match) return "";
  try {
    return decodeURIComponent(match[1]);
  } catch {
    return match[1];
  }
}

async function isAuthorised(request: Request): Promise<boolean> {
  return verifySessionToken(sessionTokenFrom(request), SESSION_TTL_SECONDS);
}

export async function POST(request: Request): Promise<Response> {
  if (!(await isAuthorised(request))) {
    return Response.json({ error: "Unauthorised" }, { status: 401 });
  }
  // Past auth. No Drive mint, no body parse — that work is the attachments
  // feature, not this gate. 503 is the kill-switch "configured-but-unwired"
  // signal so a valid session is distinguishable from a 401.
  return Response.json({ error: "Upload not configured" }, { status: 503 });
}
