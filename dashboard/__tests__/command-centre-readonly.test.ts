/**
 * command-centre-readonly.test.ts — diff-relative conformance for ported capabilities.
 *
 * THE CLAIM THIS TEST CHECKS, and the one it deliberately does NOT:
 *
 *   CHECKS:      "this port introduces no network/DB/execution construct that the
 *                 named source baseline did not already contain."
 *   DOES NOT:    "this page makes no network call."
 *
 * The second is an unbounded negative. Three bounded attempts at capability 1 were
 * all correctly failed by cross-vendor review because the spec asked for it: there
 * is always another path (dynamic import, require, WebSocket, sendBeacon, server
 * action, transitive side effect). The code was fine every time; the spec was the
 * defect. Founder ruling 2026-08-01: take the diff-relative framing.
 *
 * A diff-relative claim is decidable — compare against a baseline, answer yes or no.
 * It is also only as strong as that baseline, which is why capabilities whose safety
 * properties are load-bearing (operator-gateway) require a hand-established baseline
 * recorded in the provenance file before they may be ported.
 */
import { describe, expect, it } from "vitest";
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join, resolve } from "node:path";

const ROOT = resolve(__dirname, "..");
const PROV = JSON.parse(
  readFileSync(join(__dirname, "command-centre-provenance.json"), "utf8")
) as {
  _baseline_root: string;
  files: Record<string, string>;
};
const BASELINE = PROV._baseline_root;
const baselineAvailable = existsSync(BASELINE);

/** Constructs whose COUNT must not increase relative to the baseline. */
const TRACKED: Array<{ re: RegExp; rule: string }> = [
  { re: /\bfetch\s*\(/g, rule: "network: fetch" },
  { re: /\b(axios|got|node-fetch|undici)\b/g, rule: "network: http client" },
  { re: /\b(WebSocket|EventSource|XMLHttpRequest|sendBeacon)\b/g, rule: "network: streaming/beacon" },
  { re: /\bimport\s*\(/g, rule: "dynamic import" },
  { re: /\brequire\s*\(/g, rule: "require()" },
  { re: /https?:\/\//g, rule: "remote host literal" },
  { re: /\.(insert|update|upsert|delete)\s*\(/g, rule: "database write" },
  { re: /createServerClient|createClient\s*\(/g, rule: "database client" },
  { re: /\bMcpClient\b|modelcontextprotocol/g, rule: "MCP client" },
  { re: /"use server"|'use server'/g, rule: "server action" },
  { re: /ANTHROPIC_API_KEY|OPENAI_API_KEY|STRIPE_SECRET/g, rule: "paid API key" },
];

const strip = (s: string) =>
  s.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");

const count = (src: string, re: RegExp) => (strip(src).match(new RegExp(re.source, "g")) || []).length;

function resolveSpec(spec: string, from: string): string | null {
  let base: string;
  if (spec.startsWith("@/")) base = join(ROOT, spec.slice(2));
  else if (spec.startsWith(".")) base = resolve(dirname(from), spec);
  else return null;
  for (const c of [`${base}.ts`, `${base}.tsx`, join(base, "index.ts"), join(base, "index.tsx"), base]) {
    if (existsSync(c) && statSync(c).isFile()) return c;
  }
  return null;
}

/** Everything reachable from the capability entry pages, following imports. */
function importGraph(): string[] {
  const entries: string[] = [];
  (function walk(d: string) {
    if (!existsSync(d)) return;
    for (const e of readdirSync(d)) {
      const p = join(d, e);
      if (statSync(p).isDirectory()) walk(p);
      else if (e === "page.tsx") entries.push(p);
    }
  })(join(ROOT, "app/(main)/command-centre"));

  const seen = new Set<string>();
  const queue = [...entries];
  while (queue.length) {
    const f = queue.pop()!;
    if (seen.has(f) || !existsSync(f)) continue;
    seen.add(f);
    // Both `import x from 'y'` and the side-effect form `import 'y'`. Matching only
    // `from '...'` let a side-effect import enter the surface unprovenanced.
    for (const m of readFileSync(f, "utf8").matchAll(/(?:from|import)\s+['"]([^'"]+)['"]/g)) {
      const r = resolveSpec(m[1], f);
      if (r && !seen.has(r)) queue.push(r);
    }
  }
  return [...seen];
}

const rel = (f: string) => f.slice(ROOT.length + 1).replace(/\\/g, "/");

describe("command-centre: no new surface vs source baseline", () => {
  const files = importGraph().map(rel);

  it("the import graph reaches beyond the capability directory (positive control)", () => {
    expect(files.length).toBeGreaterThan(1);
    expect(files.some((f) => f.startsWith("components/command-centre"))).toBe(true);
  });

  it("every file in the capability surface has a declared origin", () => {
    // A file with no provenance has no baseline, so "no new surface" is unprovable
    // for it. Unlisted means fail, not skip.
    const undeclared = files.filter((f) => !(f in PROV.files));
    expect(undeclared, `no provenance entry for:\n${undeclared.join("\n")}`).toEqual([]);
  });

  it("the baseline is reachable, or the run is explicitly acknowledged as unverified", () => {
    // A skipped comparison is not a passing one. Previously this only warned while
    // the suite still went green — so an environment without the baseline reported
    // success having checked nothing. It now FAILS closed. Setting
    // CC_ALLOW_NO_BASELINE=1 is the only way past, and it makes the gap a recorded
    // choice rather than a silent one.
    const acknowledged = process.env.CC_ALLOW_NO_BASELINE === "1";
    expect(
      baselineAvailable || acknowledged,
      `[BASELINE UNAVAILABLE] ${BASELINE} not present, so the diff-relative claim ` +
        `was NOT verified. This suite refuses to report success without checking. ` +
        `Provide the baseline checkout, or set CC_ALLOW_NO_BASELINE=1 to record ` +
        `deliberately that this run proves nothing about R2/R6.`
    ).toBe(true);
  });

  it("detects an increase when one exists (positive control)", () => {
    const before = count("const a = 1", /\bfetch\s*\(/);
    const after = count("const a = fetch('x')", /\bfetch\s*\(/);
    expect(after).toBeGreaterThan(before);
  });

  for (const t of TRACKED) {
    it.skipIf(!baselineAvailable)(`introduces no new — ${t.rule}`, () => {
      const grew: string[] = [];
      const unresolved: string[] = [];
      for (const [ported, source] of Object.entries(PROV.files)) {
        const pPath = join(ROOT, ported);
        const sPath = join(BASELINE, source);
        // A pair that cannot be resolved must NOT be skipped. Skipping it left the
        // file uncompared while the suite still went green — a mistyped baseline
        // path would read as "verified clean" having checked nothing.
        if (!existsSync(pPath)) { unresolved.push(`ported missing: ${ported}`); continue; }
        if (!existsSync(sPath)) { unresolved.push(`baseline missing: ${source} (for ${ported})`); continue; }
        const p = count(readFileSync(pPath, "utf8"), t.re);
        const s = count(readFileSync(sPath, "utf8"), t.re);
        if (p > s) grew.push(`${ported}: ${s} -> ${p}`);
      }
      expect(
        unresolved,
        `provenance pairs could not be resolved, so these files were NOT compared:\n${unresolved.join("\n")}`
      ).toEqual([]);
      expect(grew, `${t.rule} increased vs baseline:\n${grew.join("\n")}`).toEqual([]);
    });
  }
});
