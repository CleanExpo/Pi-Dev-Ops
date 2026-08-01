/**
 * command-centre-readonly.test.ts — enforces R1/R2/R6 for ported capabilities.
 *
 * ATTEMPT 3. Two prior approaches were rejected by cross-vendor review:
 *   1. "the build passes"      -> a build passes *alongside* a fetch. Not evidence.
 *   2. directory-scan of two   -> the page imports from components/command-centre,
 *      fixed roots                outside the scanned roots. A violation could enter
 *                                 through an import and never be looked at.
 *
 * This attempt changes the KIND of evidence rather than widening the last one:
 * it walks the actual transitive import graph from each capability's entry page
 * and scans everything reachable. Adding a new import cannot escape the scan,
 * because the scan follows imports. A new directory does not need to be
 * remembered, which is what defeated attempt 2.
 */
import { describe, expect, it } from "vitest";
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join, resolve } from "node:path";

const ROOT = resolve(__dirname, "..");
const CAPABILITIES = "app/(main)/command-centre";

/** Reachable code permitted a server-side READ, with the reason. Still no writes. */
const ALLOWED_DATA_READERS: Record<string, string> = {
  // "lib/command-centre/wiki-graph": "reads wiki_pages server-side (capability 3)",
};

const FORBIDDEN: Array<{ re: RegExp; rule: string }> = [
  { re: /\bfetch\s*\(/, rule: "R2 no external connections" },
  { re: /\b(axios|got|node-fetch|undici)\b/, rule: "R2 no http client" },
  { re: /https?:\/\/(?!.*(?:schema|w3\.org|localhost|127\.0\.0\.1))/, rule: "R2/R6 no remote host" },
  { re: /\.(insert|update|upsert|delete)\s*\(/, rule: "R6 no database writes" },
  { re: /createServerClient|createClient\s*\(/, rule: "R6 no database client" },
  { re: /\bMcpClient\b|modelcontextprotocol/, rule: "R2 no MCP client" },
  { re: /ANTHROPIC_API_KEY|OPENAI_API_KEY|STRIPE_SECRET/, rule: "R6 no paid API keys" },
  { re: /next\/font\/google/, rule: "R2 no external font fetch — use next/font/local" },
];

function strip(src: string): string {
  return src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
}

function resolveSpec(spec: string, from: string): string | null {
  let base: string;
  if (spec.startsWith("@/")) base = join(ROOT, spec.slice(2));
  else if (spec.startsWith(".")) base = resolve(dirname(from), spec);
  else return null; // node_module — not our source
  for (const c of [`${base}.ts`, `${base}.tsx`, join(base, "index.ts"), join(base, "index.tsx"), base]) {
    if (existsSync(c) && statSync(c).isFile()) return c;
  }
  return null;
}

/** Everything reachable from the capability entry pages, following imports. */
function importGraph(): string[] {
  const entries: string[] = [];
  const walkDir = (d: string) => {
    if (!existsSync(d)) return;
    for (const e of readdirSync(d)) {
      const p = join(d, e);
      if (statSync(p).isDirectory()) walkDir(p);
      else if (/^page\.tsx$/.test(e)) entries.push(p);
    }
  };
  walkDir(join(ROOT, CAPABILITIES));

  const seen = new Set<string>();
  const queue = [...entries];
  while (queue.length) {
    const f = queue.pop()!;
    if (seen.has(f) || !existsSync(f)) continue;
    seen.add(f);
    const src = readFileSync(f, "utf8");
    for (const m of src.matchAll(/from\s+['"]([^'"]+)['"]/g)) {
      const r = resolveSpec(m[1], f);
      if (r && !seen.has(r)) queue.push(r);
    }
  }
  return [...seen];
}

describe("command-centre capabilities are read-only (import-graph scan)", () => {
  const files = importGraph();
  const rel = (f: string) => f.slice(ROOT.length + 1).replace(/\\/g, "/");

  it("positive control: the graph reaches beyond the capability directory", () => {
    // Attempt 2 failed precisely because its scan stopped at directory edges.
    // If this ever regresses to only capability-local files, the scan is blind again.
    expect(files.length).toBeGreaterThan(1);
    expect(files.some((f) => rel(f).startsWith("components/command-centre"))).toBe(true);
  });

  it("positive control: a planted violation is detected", () => {
    const planted = strip("const x = fetch('https://example.com')");
    expect(FORBIDDEN.some((r) => r.re.test(planted))).toBe(true);
  });

  for (const rule of FORBIDDEN) {
    it(`no violation of: ${rule.rule}`, () => {
      const hits = files
        .filter((f) => !Object.keys(ALLOWED_DATA_READERS).some((a) => rel(f).startsWith(a)))
        .filter((f) => rule.re.test(strip(readFileSync(f, "utf8"))))
        .map(rel);
      expect(hits, `${rule.rule} violated in:\n${hits.join("\n")}`).toEqual([]);
    });
  }
});
