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
// Auth: enforced upstream by proxy.ts, whose matcher covers all non-static routes
// and returns 401 without a valid session. There is no getUser() equivalent here
// to call, and inventing one would be a fabricated identity rather than a port.

import { NextResponse } from "next/server";
import { createServerClient } from "@/lib/supabase/server";
import { buildWikiGraph, type WikiPageRow } from "@/lib/command-centre/wiki-graph";

export const dynamic = "force-dynamic";

// PostgREST's default row cap. Made explicit so truncation can be DETECTED and
// surfaced honestly, instead of silently rendering a partial graph as complete.
const WIKI_PAGES_LIMIT = 1000;

export async function GET(): Promise<Response> {
  try {
    const supabase = createServerClient();

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
    return NextResponse.json(
      { error: e instanceof Error ? e.message : "Failed to build wiki graph" },
      { status: 500 }
    );
  }
}
