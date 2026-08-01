/**
 * command-centre-readonly.test.ts — enforces R1/R2/R6 for ported capabilities.
 *
 * WHY THIS EXISTS: `npm run build` passes *alongside* a fetch, a DB write, or a
 * paid API call — it does not prove a page is read-only. Cross-vendor review of
 * capability 1 flagged exactly that: build evidence is not spec evidence. This
 * test is the missing evidence. It fails on the constructs the contract forbids,
 * rather than hoping the compiler notices.
 *
 * Scope: every file under app/(main)/command-centre/ and lib/command-centre/.
 * Capabilities that legitimately need a data source (wiki-graph reads wiki_pages)
 * must be added to ALLOWED_DATA_READERS with a justification, so the exemption is
 * a visible decision rather than a silent hole.
 */
import { describe, expect, it } from "vitest";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";

const ROOTS = ["app/(main)/command-centre", "lib/command-centre"];

/** Capabilities permitted a server-side read, with the reason. Read-only still. */
const ALLOWED_DATA_READERS: Record<string, string> = {
  // "app/(main)/command-centre/wiki-graph": "reads wiki_pages server-side (capability 3)",
};

/** Constructs that would break the read-only contract. */
const FORBIDDEN: Array<{ re: RegExp; rule: string }> = [
  { re: /\bfetch\s*\(/, rule: "R2 no external connections" },
  { re: /\baxios\b/, rule: "R2 no external connections" },
  { re: /https?:\/\/(?!.*(?:schema|w3\.org|localhost))/, rule: "R2/R6 no remote host" },
  { re: /\.(insert|update|upsert|delete)\s*\(/, rule: "R6 no database writes" },
  { re: /createServerClient|createClient\s*\(/, rule: "R6 no database client" },
  { re: /\bMcpClient\b|modelcontextprotocol/, rule: "R2 no MCP client" },
  { re: /ANTHROPIC_API_KEY|OPENAI_API_KEY|STRIPE_SECRET/, rule: "R6 no paid API keys" },
];

function walk(dir: string): string[] {
  let out: string[] = [];
  let entries: string[];
  try {
    entries = readdirSync(dir);
  } catch {
    return out;
  }
  for (const e of entries) {
    const p = join(dir, e);
    if (statSync(p).isDirectory()) out = out.concat(walk(p));
    else if (/\.(ts|tsx)$/.test(e)) out.push(p);
  }
  return out;
}

/** Strip comments so a comment mentioning "fetch" is not a violation. */
function code(src: string): string {
  return src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
}

describe("command-centre capabilities are read-only", () => {
  const files = ROOTS.flatMap((r) => walk(r));

  it("finds the ported capability files (positive control)", () => {
    // A passing suite that scanned zero files would be indistinguishable from a
    // clean one. Fail loudly if the scan target vanished.
    expect(files.length).toBeGreaterThan(0);
  });

  it("detects a violation when one exists (positive control)", () => {
    const planted = code("const x = fetch('https://example.com')");
    expect(FORBIDDEN.some((f) => f.re.test(planted))).toBe(true);
  });

  for (const rule of FORBIDDEN) {
    it(`has no violation of: ${rule.rule}`, () => {
      const hits = files.filter((f) => {
        const exempt = Object.keys(ALLOWED_DATA_READERS).some((a) =>
          f.replace(/\\/g, "/").includes(a)
        );
        if (exempt) return false;
        return rule.re.test(code(readFileSync(f, "utf8")));
      });
      expect(hits, `${rule.rule} violated in:\n${hits.join("\n")}`).toEqual([]);
    });
  }
});
