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
  /^\/api\/autonomy\/status$/,
  /^\/api\/integrations\/health$/,
  /^\/api\/nexus\/health$/,
  /^\/api\/nexus\/ingest\/health$/,
  /^\/api\/telegram\/intake\/status$/,
  /^\/webhook\/telegram$/,
];

export function allowed(pathStr: string): boolean {
  const bare = pathStr.split("?")[0];
  return ALLOWED_UPSTREAM.some((re) => re.test(bare));
}
