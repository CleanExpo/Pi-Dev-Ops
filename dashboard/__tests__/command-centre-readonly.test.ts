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
  // OG2 had zero coverage until this line. External execution was tracked by nothing.
  { re: /\b(child_process|execSync|spawnSync|\bexec\s*\(|\bspawn\s*\(|\bfork\s*\()/g,
    rule: "external execution" },
];

/**
 * Guards whose count must NOT DECREASE. The tracked list above is one-directional —
 * it fails on an increase — so a port that DELETES a safety check passes every one of
 * them. Cross-vendor audit named this as the single most valuable missing check:
 * "a port that does not add new scary constructs, but removes the exact guards that
 * made the scary surface inert."
 */
const GUARDS: Array<{ re: RegExp; rule: string }> = [
  { re: /\b(dryRun|dry_run|DRY_RUN|isDryRun)\b/g, rule: "dry-run predicate" },
  { re: /\bdisabled\b/g, rule: "disabled control" },
  { re: /\b(readOnly|read_only|READONLY)\b/g, rule: "read-only flag" },
  { re: /\b(requireAuth|isAuthed|getUser|getSession|redirect\s*\(\s*['"]\/auth)/g, rule: "auth gate" },
  { re: /\b(sandbox|SANDBOX|isSandbox)\b/g, rule: "sandbox boundary" },
  { re: /\bconfirm\s*\(|\bconfirmed\b/g, rule: "confirmation gate" },
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

  // ---- G1: every internal link/fetch must resolve to a route that EXISTS here ----
  // Construct counts are identical when a ported fetch points at an API route that was
  // never ported, so the surface passes while the control 404s. Found in capability 2
  // by the reviewer, not by the harness.
  it("every internal href/fetch resolves to a route in the target app", () => {
    const APP = join(ROOT, "app");
    const routeExists = (p: string): boolean => {
      const clean = p.split("?")[0].split("#")[0].replace(/\/$/, "");
      if (!clean || clean === "/") return true;
      const segs = clean.split("/").filter(Boolean);
      // Next.js route groups "(main)" are transparent in the URL, so try every
      // group-prefixed location as well as the bare one.
      const groups = existsSync(APP)
        ? readdirSync(APP).filter((d) => d.startsWith("(") && statSync(join(APP, d)).isDirectory())
        : [];
      const bases = [APP, ...groups.map((g) => join(APP, g))];
      return bases.some((b) => {
        const dir = join(b, ...segs);
        return existsSync(join(dir, "page.tsx")) || existsSync(join(dir, "route.ts"));
      });
    };

    const broken: string[] = [];
    for (const f of files) {
      const src = strip(readFileSync(join(ROOT, f), "utf8"));
      const paths = [
        ...[...src.matchAll(/href=["'`](\/[^"'`]*)["'`]/g)].map((m) => m[1]),
        ...[...src.matchAll(/fetch\(\s*["'`](\/[^"'`]*)["'`]/g)].map((m) => m[1]),
      ];
      for (const p of new Set(paths)) {
        if (!routeExists(p)) broken.push(`${f} -> ${p}`);
      }
    }
    expect(
      broken,
      `internal paths with no matching route in the target app (these would 404):\n${broken.join("\n")}`
    ).toEqual([]);
  });

  // ---- G10 / Q3: a port may not DELETE a guard ----
  // fail-open-ok: same reasoning as the tracked-construct tests — the separate
  // "baseline is reachable" test FAILS when the baseline is absent, so the suite
  // cannot go green unverified. This skip avoids a second misleading failure; it
  // does not hide the first.
  it.skipIf(!baselineAvailable)("no safety guard was removed relative to the baseline", () => {
    const lost: string[] = [];
    for (const g of GUARDS) {
      for (const [ported, source] of Object.entries(PROV.files)) {
        const pPath = join(ROOT, ported);
        const sPath = join(BASELINE, source);
        if (!existsSync(pPath) || !existsSync(sPath)) continue; // covered by the unresolved check
        const p = count(readFileSync(pPath, "utf8"), g.re);
        const s = count(readFileSync(sPath, "utf8"), g.re);
        if (p < s) lost.push(`${g.rule} in ${ported}: ${s} -> ${p}`);
      }
    }
    expect(lost, `safety guards removed vs baseline:\n${lost.join("\n")}`).toEqual([]);
  });

  for (const t of TRACKED) {
    // fail-open-ok: skipping here is safe because the separate "baseline is
    // reachable" test FAILS when the baseline is absent, so the suite cannot go
    // green unverified. The skip avoids a misleading second failure, it does not
    // hide the first.
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

/**
 * Import-level provenance. File provenance proves a file has a declared origin; it
 * does NOT prove that what its imports RESOLVE TO behaves the same in both apps.
 * `@/lib/supabase/server` resolves in the source to an anon-key RLS-enforced client
 * and in the target to a service-role client that bypasses RLS — same specifier,
 * compatible shapes, clean typecheck, silent privilege change.
 */
describe("command-centre: every import has a declared judgment", () => {
  const IMPORTS = (PROV as unknown as {
    imports?: Record<string, { specifier: string; judgment: string; note: string }>;
  }).imports ?? {};

  it("the import map is populated (positive control)", () => {
    // An empty map would make every assertion below vacuously true.
    expect(Object.keys(IMPORTS).length).toBeGreaterThan(0);
  });

  it("no import is UNDECLARED", () => {
    const undeclared = Object.entries(IMPORTS)
      .filter(([, v]) => v.judgment === "UNDECLARED")
      .map(([k, v]) => `${k}\n      ${v.note}`);
    expect(
      undeclared,
      `imports with no declared judgment (same | different-but-checked | must-change):\n${undeclared.join("\n")}`
    ).toEqual([]);
  });

  it("every judgment is one of the three permitted values", () => {
    const ok = new Set(["same", "different-but-checked", "must-change"]);
    const bad = Object.entries(IMPORTS)
      .filter(([, v]) => !ok.has(v.judgment))
      .map(([k, v]) => `${k}: '${v.judgment}'`);
    expect(bad, `invalid judgment values:\n${bad.join("\n")}`).toEqual([]);
  });

  it("a 'different-but-checked' judgment carries a stated reason", () => {
    const unexplained = Object.entries(IMPORTS)
      .filter(([, v]) => v.judgment !== "same" && !v.note.trim())
      .map(([k]) => k);
    expect(unexplained, `divergent imports with no note:\n${unexplained.join("\n")}`).toEqual([]);
  });
});
