// app/api/command-centre/wiki-graph/route.ts
//
// GET /api/command-centre/wiki-graph — the wiki knowledge base as an interactive
// graph. Reads wiki_pages, parses [[wikilink]] references server-side via the
// ported pure builder, and returns the resolved node/edge graph. Unresolved links
// are dropped, never fabricated; orphan pages are included as isolated nodes.
//
// READ-ONLY. Nothing executes. No write path exists in this file.
//
// REBUILT, NOT PORTED — deliberately. The source route imports `getUser` and
// `createClient` from its own `@/lib/supabase/server`, which is an anon-key,
// RLS-enforced, cookie-scoped client with per-user identity. The same specifier
// in this app resolves to a service-role client that bypasses RLS, and this app
// has no per-user identity at all — it is single-operator behind one shared
// password. Porting the source verbatim would have typechecked cleanly while
// silently swapping an RLS-enforced read for an RLS-bypassing one.
//
// Auth: enforced upstream by proxy.ts, which returns 401 for this path without a
// valid session. There is no getUser() equivalent here to call, and inventing one
// would be a fabricated identity rather than a port.
//
// That sentence was WRONG when first written — it said the proxy's matcher "covers
// all non-static routes", which is true and irrelevant: proxy() only checks a
// session for paths listed in its PROTECTED_* prefixes, and /api/command-centre was
// in neither. This route served anonymous requests while reading through a
// service-role client that bypasses RLS. Proven and closed in
// __tests__/command-centre-auth-coverage.test.ts — which now fails if the prefix is
// ever removed, so this comment cannot rot back into a false claim silently.
//
// WRONG SUPABASE PROJECT, separately from the above. wiki_pages lives in the
// Unite-Group production project (lksfwktwtmyznckodsau — see
// scripts/sync_wiki_to_supabase.py, the writer), not in Pi CEO's own project
// (zbryrmxmgfmslqzizsto), which is what lib/supabase/server.ts's createServerClient()
// reaches. This route used that client anyway, so every request hit the wrong
// project's PostgREST endpoint for a table it doesn't have, got a 404 back, and
// surfaced it to callers as a bare 500 with nothing pointing at the real cause.
// Fixed by giving this route its own client scoped to the Unite-Group project —
// lib/supabase/unite-group-server.ts.

import { NextResponse } from "next/server";
import {
  createUniteGroupServerClient,
  missingUniteGroupEnv,
} from "@/lib/supabase/unite-group-server";
import { buildWikiGraph, type WikiPageRow } from "@/lib/command-centre/wiki-graph";

export const dynamic = "force-dynamic";

// PostgREST's default row cap. Made explicit so truncation can be DETECTED and
// surfaced honestly, instead of silently rendering a partial graph as complete.
const WIKI_PAGES_LIMIT = 1000;

export async function GET(): Promise<Response> {
  // Checked BEFORE the try, so an unconfigured deployment is reported as itself
  // rather than being flattened into the catch-all below.
  //
  // That catch-all is deliberately message-free (see its own comment) because a
  // driver error can carry a connection string. The cost was that the ONE failure
  // an operator can act on — "these two env vars were never set on this
  // deployment" — arrived as the same blank 500 as every failure they cannot.
  //
  // 503, not 500: nothing here is broken. The feature is unconfigured, which is a
  // different thing to tell an operator, and it is temporary in exactly the way
  // 503 means. Only variable NAMES cross the boundary; missingUniteGroupEnv()
  // never reads a value.
  //
  // This does NOT make the cc-wiki-graph smoke probe pass — that probe expects 200
  // with a pageCount, and there is no pageCount to return without the credentials.
  // It makes the failure legible, nothing more.
  const missingEnv = missingUniteGroupEnv();
  if (missingEnv.length > 0) {
    return NextResponse.json(
      {
        error: "Wiki graph is not configured on this deployment",
        missing: missingEnv,
        detail:
          "wiki_pages lives in the Unite-Group Supabase project, which needs its " +
          "own credentials. Set the variables named above on the dashboard " +
          "deployment — see docs/runbooks/fleet-operations.md.",
      },
      { status: 503 }
    );
  }

  try {
    const supabase = createUniteGroupServerClient();

    const { data, error } = await supabase
      .from("wiki_pages")
      .select("id,title,tags,content,updated_at")
      .limit(WIKI_PAGES_LIMIT);

    if (error) {
      // Message only — never the full error object, which can carry connection
      // details and query text.
      return NextResponse.json(
        { error: "Failed to read wiki pages", detail: error.message },
        { status: 500 }
      );
    }

    const pages = (data ?? []) as WikiPageRow[];
    const graph = buildWikiGraph(pages);

    // If we hit the cap, the graph is a partial view. Say so rather than letting
    // a truncated graph read as the whole knowledge base.
    const truncated = pages.length >= WIKI_PAGES_LIMIT;

    return NextResponse.json({
      ...graph,
      pageCount: pages.length,
      truncated,
      ...(truncated
        ? {
            warning:
              `Only the first ${WIKI_PAGES_LIMIT} pages were read, so this graph is ` +
              `incomplete. Nodes and edges beyond the cap are missing, not absent.`,
          }
        : {}),
    });
  } catch (e) {
    // Do NOT pass e.message through. The adjacent handler above is deliberately
    // message-only for a *known* PostgREST error shape; this catch-all sees
    // anything at all — client construction, env resolution, a thrown driver
    // error — and those messages carry connection strings and query text. Log
    // server-side, return a fixed string.
    console.error("[wiki-graph] unhandled failure building graph:", e);
    return NextResponse.json({ error: "Failed to build wiki graph" }, { status: 500 });
  }
}
