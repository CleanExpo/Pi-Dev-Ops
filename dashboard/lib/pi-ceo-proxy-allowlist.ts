/**
 * Upstream path allowlist for /api/pi-ceo/*.
 * Lives outside the route module — Next.js 16 rejects extra exports from route.ts.
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
  /^\/api\/goal-projects$/,
  /^\/api\/autonomy\/status$/,
  /^\/api\/integrations\/health$/,
  /^\/api\/nexus\/health$/,
  /^\/api\/nexus\/ingest\/health$/,
  // YouTube connector. PR #650 declared these four in .github/smoke-surfaces.json
  // as "surfaced through dashboard proxy" and expecting 200/422 — but never added
  // them here, so every call 403'd on `refuse()` instead. The e2e suite has been
  // red on main on exactly these four ever since. Anchored one path each, no
  // wildcard: the rest of the youtube-intent router (catalog, synthesize,
  // pull-live, oauth/callback) is deliberately NOT proxied.
  /^\/api\/nexus\/youtube-intent\/policy$/,
  /^\/api\/nexus\/youtube-intent\/oauth\/start$/,
  /^\/api\/nexus\/youtube-intent\/oauth\/state$/,
  /^\/api\/nexus\/youtube-intent\/import-takeout$/,
  /^\/api\/telegram\/intake\/status$/,
  /^\/webhook\/telegram$/,
  // Slack Events ingress (PR #673), the sibling of /webhook/telegram above. Its
  // smoke probe expects the BACKEND's 401 "Invalid Slack signature" — proof that
  // signature validation runs. Unlisted, the proxy 403'd it first, so the probe
  // never reached the check it exists to verify. Forwarding is safe precisely
  // because slack_bridge.py rejects an unsigned body before doing any work.
  /^\/webhooks\/slack\/events$/,
  // The dispatch webhook, same posture as the two above. Its smoke probe is
  // auth:true and expects the BACKEND's 400 "Missing webhook signature header"
  // (app/server/routes/webhooks.py:297) — the assertion that the signature gate
  // runs. Forwarding is safe for the same reason: the backend refuses an
  // unsigned body before doing any work, so admitting the path here grants no
  // capability the signature check does not already govern.
  //
  // This entry is REQUIRED by the auth:true flag on that probe, not incidental:
  // __tests__/pi-ceo-proxy-allowlist.test.ts derives its expected set from
  // smoke-surfaces.json with `.filter((s) => s.auth === true)`, so the two must
  // move together.
  /^\/api\/webhook$/,
];

export function allowed(pathStr: string): boolean {
  const bare = pathStr.split("?")[0];
  return ALLOWED_UPSTREAM.some((re) => re.test(bare));
}
