/** Public build identity only; never infer deployed code from a local checkout. */
export const dynamic = "force-dynamic";

export function GET() {
  const candidate = process.env.VERCEL_GIT_COMMIT_SHA || process.env.BUILD_REVISION || "";
  const revision = /^[0-9a-f]{40}$/i.test(candidate) ? candidate.toLowerCase() : null;
  return Response.json({ revision }, { headers: { "Cache-Control": "no-store" } });
}
