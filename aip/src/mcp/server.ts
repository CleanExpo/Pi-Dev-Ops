// AIP read-only MCP server.
// Spec: ~/2nd Brain/2nd Brain/Wiki/aip-first-slice-schema.md § 6 — `src/mcp/aip-server.ts`.
// Day 4 of the AIP build plan, pulled forward per Path D Hybrid (writes will land via
// Palantir Foundry's Logic-functions API; this server is read-only by design).
//
// Tools exposed:
//   - aip_get_entity      — fetch one entity by aip:// URI
//   - aip_list_entities   — list entities (optional kind filter, paginated)
//   - aip_traverse        — walk relationships outward from an entity, up to depth 3
//   - aip_query_view      — query a per-kind Postgres view with simple equality filters
//   - aip_log_tail        — tail rows from aip_action_log
//
// Connection:
//   - Supabase URL: SUPABASE_PICEO_URL or SUPABASE_URL (defaults to the Pi-CEO project)
//   - Service key:  SUPABASE_PICEO_SERVICE_KEY or SUPABASE_SERVICE_ROLE_KEY
//                   (sourced from 1Password Unite-Group-Infrastructure vault outside
//                   the process — see README. Never logged.)

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { createClient, type SupabaseClient } from "@supabase/supabase-js";
import { z } from "zod";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const SERVER_NAME = "aip-readonly";
const SERVER_VERSION = "0.1.0";
const DEFAULT_SUPABASE_URL = "https://zbryrmxmgfmslqzizsto.supabase.co";

const URI_PREFIX = "aip://unite-group/";
const URI_REGEX = /^aip:\/\/unite-group\/[A-Za-z][A-Za-z0-9]*\/[^/\s]+$/;

const KNOWN_VIEWS = [
  "v_google_identity",
  "v_gcp_project",
  "v_vercel_project",
  "v_oauth_client",
  "v_portfolio_service",
] as const;
type KnownView = (typeof KNOWN_VIEWS)[number];

// ---------------------------------------------------------------------------
// Supabase client (lazy — never log the key)
// ---------------------------------------------------------------------------

function readSupabaseConfig(): { url: string; key: string } {
  const url =
    process.env.SUPABASE_PICEO_URL ??
    process.env.SUPABASE_URL ??
    DEFAULT_SUPABASE_URL;
  const key =
    process.env.SUPABASE_PICEO_SERVICE_KEY ??
    process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!key) {
    throw new Error(
      "Supabase service key missing. Set SUPABASE_PICEO_SERVICE_KEY or " +
        "SUPABASE_SERVICE_ROLE_KEY (see aip/src/mcp/README.md for 1Password lookup).",
    );
  }
  return { url, key };
}

let _client: SupabaseClient | null = null;
function db(): SupabaseClient {
  if (_client) return _client;
  const { url, key } = readSupabaseConfig();
  _client = createClient(url, key, {
    auth: { persistSession: false, autoRefreshToken: false },
  });
  return _client;
}

// ---------------------------------------------------------------------------
// Shared types — mirror the live aip_entities / aip_relationships shapes
// ---------------------------------------------------------------------------

interface EntityRow {
  uri: string;
  kind: string;
  id: string;
  properties: Record<string, unknown>;
  source: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

interface RelationshipRow {
  uri: string;
  kind: string;
  from_uri: string;
  to_uri: string;
  cardinality: "1:1" | "N:1" | "1:N" | "N:N";
  properties: Record<string, unknown>;
  created_at: string;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function assertAipUri(uri: string): void {
  if (!URI_REGEX.test(uri)) {
    throw new Error(
      `Invalid AIP URI '${uri}'. Expected '${URI_PREFIX}{kind}/{id}'.`,
    );
  }
}

/** MCP tool callbacks must return CallToolResult shape. */
function ok(payload: unknown): {
  content: Array<{ type: "text"; text: string }>;
} {
  return {
    content: [{ type: "text" as const, text: JSON.stringify(payload, null, 2) }],
  };
}

function err(message: string): {
  isError: true;
  content: Array<{ type: "text"; text: string }>;
} {
  return {
    isError: true as const,
    content: [{ type: "text" as const, text: message }],
  };
}

// ---------------------------------------------------------------------------
// Tool implementations
// ---------------------------------------------------------------------------

async function getEntity(uri: string): Promise<EntityRow | null> {
  assertAipUri(uri);
  const { data, error } = await db()
    .from("aip_entities")
    .select("uri,kind,id,properties,source,created_at,updated_at")
    .eq("uri", uri)
    .maybeSingle();
  if (error) throw new Error(error.message);
  return (data as EntityRow | null) ?? null;
}

async function listEntities(
  kind: string | undefined,
  limit: number,
): Promise<EntityRow[]> {
  let q = db()
    .from("aip_entities")
    .select("uri,kind,id,properties,source,created_at,updated_at")
    .order("kind", { ascending: true })
    .order("id", { ascending: true })
    .limit(limit);
  if (kind) q = q.eq("kind", kind);
  const { data, error } = await q;
  if (error) throw new Error(error.message);
  return (data as EntityRow[] | null) ?? [];
}

interface TraverseResult {
  root: EntityRow;
  edges: RelationshipRow[];
  entities: EntityRow[];
  depth: number;
}

async function traverse(
  fromUri: string,
  relationshipKind: string | undefined,
  depth: number,
): Promise<TraverseResult> {
  assertAipUri(fromUri);

  const root = await getEntity(fromUri);
  if (!root) {
    throw new Error(`Entity not found: ${fromUri}`);
  }

  const visitedEntities = new Map<string, EntityRow>([[root.uri, root]]);
  const visitedEdges = new Map<string, RelationshipRow>();
  let frontier: string[] = [root.uri];

  for (let level = 0; level < depth; level += 1) {
    if (frontier.length === 0) break;
    let q = db()
      .from("aip_relationships")
      .select("uri,kind,from_uri,to_uri,cardinality,properties,created_at")
      .in("from_uri", frontier);
    if (relationshipKind) q = q.eq("kind", relationshipKind);
    const { data, error } = await q;
    if (error) throw new Error(error.message);
    const edges = (data as RelationshipRow[] | null) ?? [];

    const nextFrontier = new Set<string>();
    for (const edge of edges) {
      if (visitedEdges.has(edge.uri)) continue;
      visitedEdges.set(edge.uri, edge);
      if (!visitedEntities.has(edge.to_uri)) nextFrontier.add(edge.to_uri);
    }

    if (nextFrontier.size > 0) {
      const { data: ents, error: eErr } = await db()
        .from("aip_entities")
        .select("uri,kind,id,properties,source,created_at,updated_at")
        .in("uri", Array.from(nextFrontier));
      if (eErr) throw new Error(eErr.message);
      for (const e of (ents as EntityRow[] | null) ?? []) {
        visitedEntities.set(e.uri, e);
      }
    }
    frontier = Array.from(nextFrontier);
  }

  return {
    root,
    edges: Array.from(visitedEdges.values()),
    entities: Array.from(visitedEntities.values()).filter(
      (e) => e.uri !== root.uri,
    ),
    depth,
  };
}

async function queryView(
  viewName: KnownView,
  filters: Record<string, string | number | boolean> | undefined,
  limit: number,
): Promise<Record<string, unknown>[]> {
  let q = db().from(viewName).select("*").limit(limit);
  if (filters) {
    for (const [k, v] of Object.entries(filters)) q = q.eq(k, v);
  }
  const { data, error } = await q;
  if (error) throw new Error(error.message);
  return (data as Record<string, unknown>[] | null) ?? [];
}

interface ActionLogRow {
  id: number;
  action: string;
  actor: string;
  params: Record<string, unknown>;
  permission: string;
  affected: string[];
  before_hash: string | null;
  after_hash: string | null;
  result: Record<string, unknown> | null;
  error: string | null;
  started_at: string;
  ended_at: string | null;
}

async function logTail(
  actor: string | undefined,
  limit: number,
): Promise<ActionLogRow[]> {
  let q = db()
    .from("aip_action_log")
    .select(
      "id,action,actor,params,permission,affected,before_hash,after_hash,result,error,started_at,ended_at",
    )
    .order("started_at", { ascending: false })
    .limit(limit);
  if (actor) q = q.eq("actor", actor);
  const { data, error } = await q;
  if (error) throw new Error(error.message);
  return (data as ActionLogRow[] | null) ?? [];
}

// ---------------------------------------------------------------------------
// Server registration
// ---------------------------------------------------------------------------

export function buildServer(): McpServer {
  const server = new McpServer({
    name: SERVER_NAME,
    version: SERVER_VERSION,
  });

  server.registerTool(
    "aip_get_entity",
    {
      title: "Get AIP entity",
      description:
        "Fetch a single AIP entity by its aip://unite-group/{kind}/{id} URI. Returns null if not found.",
      inputSchema: {
        uri: z
          .string()
          .regex(URI_REGEX, "must match aip://unite-group/{kind}/{id}"),
      },
    },
    async (args) => {
      try {
        const row = await getEntity(args.uri);
        return ok({ entity: row });
      } catch (e) {
        return err((e as Error).message);
      }
    },
  );

  server.registerTool(
    "aip_list_entities",
    {
      title: "List AIP entities",
      description:
        "List entities, optionally filtered by kind. Default limit 50, max 500.",
      inputSchema: {
        kind: z.string().min(1).optional(),
        limit: z.number().int().min(1).max(500).optional(),
      },
    },
    async (args) => {
      try {
        const limit = args.limit ?? 50;
        const rows = await listEntities(args.kind, limit);
        return ok({ count: rows.length, entities: rows });
      } catch (e) {
        return err((e as Error).message);
      }
    },
  );

  server.registerTool(
    "aip_traverse",
    {
      title: "Traverse AIP relationships",
      description:
        "Walk outbound relationships from an entity. Optional kind filter and depth (1-3, default 1). Returns root, edges, related entities.",
      inputSchema: {
        from_uri: z
          .string()
          .regex(URI_REGEX, "must match aip://unite-group/{kind}/{id}"),
        relationship_kind: z.string().min(1).optional(),
        depth: z.number().int().min(1).max(3).optional(),
      },
    },
    async (args) => {
      try {
        const depth = args.depth ?? 1;
        const result = await traverse(
          args.from_uri,
          args.relationship_kind,
          depth,
        );
        return ok(result);
      } catch (e) {
        return err((e as Error).message);
      }
    },
  );

  server.registerTool(
    "aip_query_view",
    {
      title: "Query AIP per-kind view",
      description:
        "Query one of the 5 per-kind views with simple equality filters. Default limit 50, max 500.",
      inputSchema: {
        view_name: z.enum(KNOWN_VIEWS),
        filters: z
          .record(z.string(), z.union([z.string(), z.number(), z.boolean()]))
          .optional(),
        limit: z.number().int().min(1).max(500).optional(),
      },
    },
    async (args) => {
      try {
        const limit = args.limit ?? 50;
        const rows = await queryView(args.view_name, args.filters, limit);
        return ok({ view: args.view_name, count: rows.length, rows });
      } catch (e) {
        return err((e as Error).message);
      }
    },
  );

  server.registerTool(
    "aip_log_tail",
    {
      title: "Tail AIP action log",
      description:
        "Return recent rows from aip_action_log, newest first. Optional actor filter. Default limit 20, max 500. Empty until Foundry-driven Actions land (Path D).",
      inputSchema: {
        actor: z.string().min(1).optional(),
        limit: z.number().int().min(1).max(500).optional(),
      },
    },
    async (args) => {
      try {
        const limit = args.limit ?? 20;
        const rows = await logTail(args.actor, limit);
        return ok({ count: rows.length, rows });
      } catch (e) {
        return err((e as Error).message);
      }
    },
  );

  return server;
}

// ---------------------------------------------------------------------------
// Entrypoint
// ---------------------------------------------------------------------------

async function main(): Promise<void> {
  // Validate config eagerly so a missing key surfaces on startup, not on first call.
  readSupabaseConfig();
  const server = buildServer();
  const transport = new StdioServerTransport();
  await server.connect(transport);
  // stderr is safe — stdout is the MCP transport.
  process.stderr.write(
    `[${SERVER_NAME} v${SERVER_VERSION}] read-only MCP server ready (stdio)\n`,
  );
}

const isDirectInvocation =
  import.meta.url === `file://${process.argv[1] ?? ""}` ||
  import.meta.url.endsWith(process.argv[1] ?? "_never_");

if (isDirectInvocation) {
  main().catch((e: unknown) => {
    const msg = e instanceof Error ? e.message : String(e);
    process.stderr.write(`[${SERVER_NAME}] fatal: ${msg}\n`);
    process.exit(1);
  });
}
