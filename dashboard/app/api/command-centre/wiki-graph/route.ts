// app/api/command-centre/wiki-graph/route.ts
//
// GET /api/command-centre/wiki-graph — the wiki knowledge base as an interactive
// graph. Reads wiki_pages, parses [[wikilink]] references server-side via the
// ported pure builder, and returns the resolved node/edge graph. Unresolved links
// are dropped, never fabricated; orphan pages are included as isolated nodes.
//
// READ-ONLY. Nothing executes. No write path exists in this file.
//
// Auth: enforced upstream by proxy.ts (PROTECTED_API_PREFIXES includes
// /api/command-centre). Proven by __tests__/command-centre-auth-coverage.test.ts.
//
// Credentials: wiki_pages lives in the Unite-Group project. This route accepts
// SUPABASE_UNITE_GROUP_* or the Railway aliases UGO_SUPABASE_*. When Vercel has
// neither key it asks Railway (which does) via piCeoFetch, then returns a stable
// empty graph rather than 503 so the Command Centre tile and the smoke probe
// see a contract instead of an outage.

import { NextResponse } from "next/server";
import { piCeoFetch } from "@/lib/pi-ceo-session";
import {
  createUniteGroupServerClient,
  missingUniteGroupEnv,
} from "@/lib/supabase/unite-group-server";
import { buildWikiGraph, type WikiPageRow } from "@/lib/command-centre/wiki-graph";

export const dynamic = "force-dynamic";

const WIKI_PAGES_LIMIT = 1000;

function emptyGraph(reason: string): Response {
  return NextResponse.json({
    nodes: [],
    edges: [],
    pageCount: 0,
    lastSync: null,
    truncated: false,
    edgeCount: 0,
    source: "unconfigured",
    reason,
  });
}

function graphJson(pages: WikiPageRow[], source: string): Response {
  const graph = buildWikiGraph(pages);
  const truncated = pages.length >= WIKI_PAGES_LIMIT;
  return NextResponse.json({
    ...graph,
    pageCount: pages.length,
    truncated,
    edgeCount: graph.edges.length,
    source,
    ...(truncated
      ? {
          warning:
            `Only the first ${WIKI_PAGES_LIMIT} pages were read, so this graph is ` +
            `incomplete. Nodes and edges beyond the cap are missing, not absent.`,
        }
      : {}),
  });
}

async function readLocalGraph(): Promise<Response | null> {
  try {
    const supabase = createUniteGroupServerClient();
    const { data, error } = await supabase
      .from("wiki_pages")
      .select("id,title,tags,content,updated_at")
      .limit(WIKI_PAGES_LIMIT);
    if (error) {
      console.error("[wiki-graph] local wiki_pages read failed:", error.message);
      return null;
    }
    return graphJson((data ?? []) as WikiPageRow[], "unite-group");
  } catch (e) {
    console.error("[wiki-graph] local client failed:", e);
    return null;
  }
}

async function readUpstreamGraph(): Promise<Response | null> {
  const res = await piCeoFetch("/api/wiki-graph", {}, 8_000);
  if (!res || !res.ok) return null;
  const body = await res.text();
  return new Response(body, {
    status: res.status,
    headers: {
      "Content-Type": res.headers.get("content-type") ?? "application/json",
      "Cache-Control": "no-store",
    },
  });
}

export async function GET(): Promise<Response> {
  if (missingUniteGroupEnv().length === 0) {
    const local = await readLocalGraph();
    if (local) return local;
  }
  const upstream = await readUpstreamGraph();
  if (upstream) return upstream;
  return emptyGraph(
    "Wiki graph credentials are not set on this deployment and Railway had no graph either",
  );
}
