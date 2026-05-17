// Smoke driver for the AIP MCP server.
// Spawns the server over stdio with the official MCP client and runs the three
// calls listed in the Day-4 task brief. Prints PASS/FAIL per call + a final
// summary; exits non-zero if any check fails.
//
// Usage: npx tsx src/mcp/_smoke.ts
//
// Requires SUPABASE_PICEO_SERVICE_KEY (or SUPABASE_SERVICE_ROLE_KEY) in env so
// the spawned server can read from the live Pi-CEO Supabase project.

import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

interface ToolTextResult {
  content?: Array<{ type: string; text?: string }>;
  isError?: boolean;
}

interface Check {
  name: string;
  pass: boolean;
  detail: string;
}

function extractJson(result: ToolTextResult): unknown {
  const block = result.content?.find((c) => c.type === "text");
  if (!block?.text) throw new Error("no text content");
  return JSON.parse(block.text);
}

async function main(): Promise<void> {
  const here = dirname(fileURLToPath(import.meta.url));
  const serverPath = resolve(here, "server.ts");
  const transport = new StdioClientTransport({
    command: "npx",
    args: ["tsx", serverPath],
    env: {
      ...(process.env as Record<string, string>),
      // ensure both names are forwarded if either is set
    },
  });

  const client = new Client({ name: "aip-smoke", version: "0.0.1" });
  await client.connect(transport);

  const checks: Check[] = [];

  // 1. list PortfolioService → expect at least the RestoreAssist row.
  try {
    const res = (await client.callTool({
      name: "aip_list_entities",
      arguments: { kind: "PortfolioService" },
    })) as ToolTextResult;
    if (res.isError) throw new Error("tool returned error");
    const payload = extractJson(res) as {
      count: number;
      entities: Array<{ uri: string; id: string }>;
    };
    const got = payload.entities.map((e) => e.uri);
    const pass =
      payload.count >= 1 &&
      got.includes("aip://unite-group/PortfolioService/ra");
    checks.push({
      name: "aip_list_entities { kind: 'PortfolioService' }",
      pass,
      detail: `count=${payload.count} uris=${JSON.stringify(got)}`,
    });
  } catch (e) {
    checks.push({
      name: "aip_list_entities { kind: 'PortfolioService' }",
      pass: false,
      detail: (e as Error).message,
    });
  }

  // 2. get RestoreAssist PortfolioService entity
  try {
    const res = (await client.callTool({
      name: "aip_get_entity",
      arguments: { uri: "aip://unite-group/PortfolioService/ra" },
    })) as ToolTextResult;
    if (res.isError) throw new Error("tool returned error");
    const payload = extractJson(res) as {
      entity: { uri: string; kind: string; properties: { slug?: string } } | null;
    };
    const ent = payload.entity;
    const pass =
      ent !== null &&
      ent.uri === "aip://unite-group/PortfolioService/ra" &&
      ent.kind === "PortfolioService" &&
      ent.properties.slug === "ra";
    checks.push({
      name: "aip_get_entity { uri: ra }",
      pass,
      detail: ent ? `kind=${ent.kind} slug=${ent.properties.slug}` : "null",
    });
  } catch (e) {
    checks.push({
      name: "aip_get_entity { uri: ra }",
      pass: false,
      detail: (e as Error).message,
    });
  }

  // 3. traverse from PortfolioService/ra at depth 1 → expect 3 outbound edges
  try {
    const res = (await client.callTool({
      name: "aip_traverse",
      arguments: {
        from_uri: "aip://unite-group/PortfolioService/ra",
        depth: 1,
      },
    })) as ToolTextResult;
    if (res.isError) throw new Error("tool returned error");
    const payload = extractJson(res) as {
      edges: Array<{ kind: string; to_uri: string }>;
    };
    const expectedKinds = new Set([
      "PortfolioService.deploysTo.VercelProject",
      "PortfolioService.authsVia.OAuthClient",
      "PortfolioService.usesGcp.GcpProject",
    ]);
    const got = new Set(payload.edges.map((e) => e.kind));
    const pass =
      payload.edges.length === 3 &&
      [...expectedKinds].every((k) => got.has(k));
    checks.push({
      name: "aip_traverse { from_uri: ra, depth: 1 }",
      pass,
      detail: `edges=${payload.edges.length} kinds=${JSON.stringify([...got])}`,
    });
  } catch (e) {
    checks.push({
      name: "aip_traverse { from_uri: ra, depth: 1 }",
      pass: false,
      detail: (e as Error).message,
    });
  }

  await client.close();

  let allPass = true;
  for (const c of checks) {
    const tag = c.pass ? "PASS" : "FAIL";
    if (!c.pass) allPass = false;
    process.stdout.write(`[${tag}] ${c.name} — ${c.detail}\n`);
  }
  process.stdout.write(
    `\nSummary: ${checks.filter((c) => c.pass).length}/${checks.length} passed\n`,
  );
  if (!allPass) process.exit(1);
}

main().catch((e: unknown) => {
  const msg = e instanceof Error ? e.message : String(e);
  process.stderr.write(`smoke fatal: ${msg}\n`);
  process.exit(1);
});
