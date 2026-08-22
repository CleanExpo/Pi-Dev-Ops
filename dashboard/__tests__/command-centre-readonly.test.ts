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
const PROV_RAW = JSON.parse(
  readFileSync(join(__dirname, "command-centre-provenance.json"), "utf8")
) as Record<string, unknown>;
const PROV = PROV_RAW as unknown as {
  _baseline_root: string;
  _baseline_snapshot: string;
  files: Record<string, string>;
  /** Written fresh for this app. No source baseline exists, so diff-relative
   *  comparison is meaningless for these — they are declared, not compared. */
  _rebuilt_not_ported?: Record<string, string>;
  /** Pre-existing files of THIS app, pulled into the graph by an import. */
  _target_native?: Record<string, string>;
  /** file -> rule -> the ONE expected count change, with its reason. */
  _declared_deltas?: Record<string, Record<string, DeclaredDelta>>;
};

/** An exemption names the exact magnitude it excuses, not just the direction. */
interface DeclaredDelta {
  /** Count in the baseline. */
  from: number;
  /** Count the port is allowed to have — this value and no other. */
  to: number;
  reason: string;
}

/**
 * True only for the EXACT declared count change.
 *
 * This used to key on file+rule alone, which made it a blanket exclusion wearing
 * a narrower label: declaring "auth gate 3 -> 0" also excused 3 -> 1, 3 -> 2, and
 * every future auth-gate loss in that file. Cross-vendor review caught it —
 * "exempts any auth gate decrease in wiki-graph/page.tsx, not just the expected
 * removal". The mechanism existed to avoid a blanket exclusion and was blanket one
 * level down. An exemption now excuses one measured transition; anything else in
 * the same file, same rule, still fails.
 */
const deltaDeclared = (file: string, rule: string, from: number, to: number): boolean => {
  const d = (PROV_RAW as {
    _declared_deltas?: Record<string, Record<string, DeclaredDelta>>;
  })._declared_deltas?.[file]?.[rule];
  if (!d) return false;
  return d.from === from && d.to === to && Boolean(d.reason);
};

/** Files with a declared origin OR a declared reason for having none. */
const DECLARED = new Set<string>([
  ...Object.keys((PROV_RAW as { files: Record<string, string> }).files),
  ...Object.keys((PROV_RAW as { _rebuilt_not_ported?: Record<string, string> })._rebuilt_not_ported ?? {}),
  ...Object.keys((PROV_RAW as { _target_native?: Record<string, string> })._target_native ?? {}),
]);
// The recorded path is the source machine's checkout. CI and independent reviewers may
// provide the same source tree at a different absolute path without rewriting provenance.
const BASELINE = process.env.CC_BASELINE_ROOT;
const SNAPSHOT_PATH = join(__dirname, PROV._baseline_snapshot);
const baselineAvailable = Boolean(BASELINE ? existsSync(BASELINE) : existsSync(SNAPSHOT_PATH));
const SNAPSHOT = existsSync(SNAPSHOT_PATH)
  ? JSON.parse(readFileSync(SNAPSHOT_PATH, "utf8")) as {
      files: Record<string, { sha256: string; counts: Record<string, number> }>;
    }
  : null;

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

/** Prefer a supplied source checkout; otherwise use the immutable, hash-anchored count snapshot. */
const baselineCount = (source: string, rule: string, re: RegExp): number | null => {
  if (BASELINE) {
    const sourcePath = join(BASELINE, source);
    return existsSync(sourcePath) ? count(readFileSync(sourcePath, "utf8"), re) : null;
  }
  const entry = SNAPSHOT?.files[source];
  return entry?.sha256 ? (entry.counts[rule] ?? 0) : null;
};

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

/**
 * Everything reachable from the capability entry pages, following imports.
 *
 * SCOPE vs .gitignore — recorded because every git-grounded check in this repo had to be
 * audited for it (see ".gitignore is a silent scope reducer" in .harness/lesson-patterns.md).
 *
 * This walk is FILESYSTEM-grounded, not git-grounded, so .gitignore cannot silently shrink
 * it — an ignored file in the import graph is still walked and still needs provenance.
 *
 * The exposure here is the INVERSE: a capability file that is gitignored would satisfy
 * provenance while never entering the repo. It would run on this machine and exist nowhere
 * else. Same family as "wired is not synced". Nothing in this suite would catch that; the
 * check that would is fail_open_check.py Class B, which asks git whether declared evidence
 * is actually tracked.
 */
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

  // The API routes are capability surface too, and seeding only from page.tsx left
  // them out of the graph entirely. Cross-vendor review named the exact consequence:
  // the route's own imports — including `@/lib/supabase/server`, the service-role
  // client — could change with no provenance entry, while "no real import without an
  // entry" still passed. The route was checked for EXISTENCE and never for what it
  // pulls in. A reachability check that starts from the wrong roots is not narrower,
  // it is blind in a specific direction.
  (function walk(d: string) {
    if (!existsSync(d)) return;
    for (const e of readdirSync(d)) {
      const p = join(d, e);
      if (statSync(p).isDirectory()) walk(p);
      else if (e === "route.ts" || e === "route.tsx") entries.push(p);
    }
  })(join(ROOT, "app/api/command-centre"));

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

/**
 * ---- Shared predicates ----
 *
 * The checks below are pure functions of (map, observed surface) so the mutation
 * controls at the end of this file can run THE REAL LOGIC over a deliberately broken
 * map. A control that re-implements the check it is meant to falsify proves only that
 * the copy works; these call the same function the passing test calls.
 */
const undeclaredFiles = (declared: Set<string>, graphFiles: string[]): string[] =>
  graphFiles.filter((f) => !declared.has(f));

const unmappedImports = (map: Record<string, unknown>, actual: Set<string>): string[] =>
  [...actual].filter((k) => !(k in map));

interface ImportEntry {
  specifier: string;
  judgment: string;
  note: string;
  resolves_in_target?: string;
  /** Required exactly when this import resolves to a module that builds a
   *  service-role database client. See _privilege_note in the provenance file. */
  privilege?: string;
}

const IMPORT_MAP: Record<string, ImportEntry> =
  (PROV as unknown as { imports?: Record<string, ImportEntry> }).imports ?? {};

const ACTUAL_IMPORTS = new Set<string>(
  importGraph().flatMap((f) =>
    [...readFileSync(f, "utf8").matchAll(/(?:from|import)\s+['"]([^'"]+)['"]/g)]
      .map((m) => `${rel(f)} :: ${m[1]}`)
  )
);

/**
 * ---- Privilege boundary ----
 *
 * A module is PRIVILEGED when its own source builds a database client from a
 * service-role credential — the credential that bypasses Row Level Security.
 * `dashboard/lib/supabase/server.ts` says so in its own words ("Bypasses Row Level
 * Security — never expose to browser"), and `lib/supabase/unite-group-server.ts`
 * repeats it for the Unite-Group project.
 *
 * The set is DERIVED by reading the resolved modules, never maintained by hand. That
 * is the whole point: every other check in this file compares the map against the set
 * of import SPECIFIERS, so all of them pass unchanged when a module that is already
 * mapped quietly starts constructing a service-role client. No specifier moved, no
 * file entered the graph, and the privilege boundary shifted anyway. That is the
 * "same specifier, compatible shapes, clean typecheck, silent privilege change" case
 * this suite's own docstring names, and until now nothing here could see it.
 */
const SERVICE_ROLE_CREDENTIAL = /SERVICE_ROLE[A-Z_]*|SERVICE_KEY/;

const privilegedModules = (graphFiles: string[]): Set<string> =>
  new Set(
    graphFiles.filter((f) =>
      SERVICE_ROLE_CREDENTIAL.test(strip(readFileSync(join(ROOT, f), "utf8")))
    )
  );

/** Resolve `"<file> :: <specifier>"` to a repo-relative target file, or null. */
const resolveEntryTarget = (key: string): string | null => {
  const [from, spec] = key.split(" :: ");
  if (!from || !spec) return null;
  const r = resolveSpec(spec, join(ROOT, from));
  return r ? rel(r) : null;
};

/** Imports that reach a privileged module without saying so. */
const undeclaredPrivilegedImports = (
  map: Record<string, ImportEntry>,
  actual: Set<string>,
  privileged: Set<string>
): string[] =>
  [...actual]
    .filter((k) => {
      const target = resolveEntryTarget(k);
      if (!target || !privileged.has(target)) return false;
      const e = map[k];
      return !e || e.privilege !== "service-role" || !String(e.note ?? "").trim();
    })
    .sort();

/** Entries claiming service-role over something that is not one. A stale claim
 *  inflates the map exactly the way a phantom entry does. */
const phantomPrivilegeClaims = (
  map: Record<string, ImportEntry>,
  privileged: Set<string>
): string[] =>
  Object.keys(map)
    .filter((k) => {
      if (map[k]?.privilege !== "service-role") return false;
      const target = resolveEntryTarget(k);
      return !target || !privileged.has(target);
    })
    .sort();

describe("command-centre: no new surface vs source baseline", () => {
  const files = importGraph().map(rel);

  it("the import graph reaches beyond the capability directory (positive control)", () => {
    expect(files.length).toBeGreaterThan(1);
    expect(files.some((f) => f.startsWith("components/command-centre"))).toBe(true);
  });

  it("every file in the capability surface has a declared origin", () => {
    // A file with no provenance has no baseline, so "no new surface" is unprovable
    // for it. Unlisted means fail, not skip.
    const undeclared = undeclaredFiles(DECLARED, files);
    expect(undeclared, `no provenance entry for:\n${undeclared.join("\n")}`).toEqual([]);
  });

  it("pinned baseline evidence is available, or the run is explicitly acknowledged as unverified", () => {
    // A skipped comparison is not a passing one. Previously this only warned while
    // the suite still went green — so an environment without the baseline reported
    // success having checked nothing. It now FAILS closed. Setting
    // CC_ALLOW_NO_BASELINE=1 is the only way past, and it makes the gap a recorded
    // choice rather than a silent one.
    const acknowledged = process.env.CC_ALLOW_NO_BASELINE === "1";
    expect(
      baselineAvailable || acknowledged,
      `[BASELINE UNAVAILABLE] neither CC_BASELINE_ROOT nor ${SNAPSHOT_PATH} is usable, so the diff-relative claim ` +
        `was NOT verified. This suite refuses to report success without checking. ` +
        `Provide the baseline checkout or pinned snapshot, or set CC_ALLOW_NO_BASELINE=1 to record ` +
        `deliberately that this run proves nothing about R2/R6.`
    ).toBe(true);
  });

  it("detects an increase when one exists (positive control)", () => {
    const before = count("const a = 1", /\bfetch\s*\(/);
    const after = count("const a = fetch('x')", /\bfetch\s*\(/);
    expect(after).toBeGreaterThan(before);
  });

  // ---- G1 (PARTIAL): literal internal navigation must resolve to a route here ----
  // Construct counts are identical when a ported fetch points at an API route that was
  // never ported, so the surface passes while the control 404s. Found in capability 2
  // by the reviewer, not by the harness.
  //
  // THIS IS A TRIPWIRE, NOT A PROOF, AND THE NAME NOW SAYS SO.
  //
  // It scans three literal forms: href="/x", fetch("/x"), and router.push/replace("/x…").
  // It cannot see navigation through an expression — `<Link href={d.href}>` over a local
  // array is in this very capability and invisible to it. Nor object hrefs, wrapper
  // components, window.location, callbacks passed as props, server redirects, or form
  // actions.
  //
  // It was previously called "every internal href/fetch resolves to a route in the
  // target app". That name claimed the general property while checking three syntactic
  // forms, and a reviewer found the gap for the fourth round running — the same class
  // every round found: coverage reading wider than it is. Founder ruled 2026-08-01:
  // rename to what it verifies, keep the gap OPEN on the coverage map (G1 stays open,
  // partially mitigated), and replace the detector with runtime route exercising rather
  // than extending the pattern list. Enumerating navigation forms is not a design that
  // can be completed; AST extraction was considered and rejected as the same
  // uncompletable enumeration in better clothes.
  //
  // Do NOT close this by adding another regex. That is the patch the ruling forbids.
  it("literal href/fetch/router paths resolve to a route in the target app (tripwire — does not cover computed navigation, see G1)", () => {
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
        // Programmatic navigation, and the TEMPLATE-LITERAL form especially. This check
        // was written to catch a ported control pointing at an unported route, and it
        // missed exactly that: WikiGraphCanvas does
        // `router.push(`/founder/wiki/${slug}`)`, which is not an href= and not a
        // string literal, so every node click 404'd while this test passed. Truncate at
        // the first `${` and check the static prefix — a prefix that does not exist
        // cannot be rescued by whatever the interpolation produces.
        ...[...src.matchAll(/router\.(?:push|replace)\(\s*["'`](\/[^"'`]*)["'`]/g)]
          .map((m) => m[1].split("${")[0]),
      ];
      for (const p of new Set(paths)) {
        if (!routeExists(p)) broken.push(`${f} -> ${p}`);
      }
    }
    expect(
      broken,
      `literal internal paths with no matching route in the target app (these would 404):\n` +
        `${broken.join("\n")}\n\n` +
        `NOTE: an empty result here does NOT mean every internal navigation resolves. This ` +
        `check sees three literal forms only. Computed navigation — <Link href={expr}>, ` +
        `object hrefs, wrapper components, window.location, server redirects — is not ` +
        `covered. G1 is OPEN on the coverage map.`
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
        if (!existsSync(pPath)) continue; // covered by the unresolved check
        const p = count(readFileSync(pPath, "utf8"), g.re);
        const s = baselineCount(source, g.rule, g.re);
        if (s === null) continue; // covered by the unresolved check
        if (p < s && !deltaDeclared(ported, g.rule, s, p)) lost.push(`${g.rule} in ${ported}: ${s} -> ${p}`);
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
        // A pair that cannot be resolved must NOT be skipped. Skipping it left the
        // file uncompared while the suite still went green — a mistyped baseline
        // path would read as "verified clean" having checked nothing.
        if (!existsSync(pPath)) { unresolved.push(`ported missing: ${ported}`); continue; }
        const s = baselineCount(source, t.rule, t.re);
        if (s === null) { unresolved.push(`baseline missing: ${source} (for ${ported})`); continue; }
        const p = count(readFileSync(pPath, "utf8"), t.re);
        if (p > s && !deltaDeclared(ported, t.rule, s, p)) grew.push(`${ported}: ${s} -> ${p}`);
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
  const IMPORTS = IMPORT_MAP;

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

  it("every judgment is one of the permitted values", () => {
    const ok = new Set(["same", "different-but-checked", "must-change", "no-source-baseline"]);
    const bad = Object.entries(IMPORTS)
      .filter(([, v]) => !ok.has(v.judgment))
      .map(([k, v]) => `${k}: '${v.judgment}'`);
    expect(bad, `invalid judgment values:\n${bad.join("\n")}`).toEqual([]);
  });

  /**
   * `no-source-baseline` is the honest judgment for an import in a file that has no
   * source counterpart — a rebuilt or target-native file. Comparing its imports across
   * apps is not a check that can be run, and labelling it `must-change` would assert a
   * comparison that never happened.
   *
   * It is also, obviously, an escape hatch: any import could be waved through by
   * claiming its file has no baseline. So it is CONSTRAINED to files actually declared
   * as baseline-free. This is the third time on this capability that a mechanism built
   * to narrow an exclusion had to be narrowed itself — the pattern is that an exemption
   * is only as tight as the thing that decides who may claim it.
   */
  it("'no-source-baseline' is only claimable by a file declared as having none", () => {
    const baselineFree = new Set([
      ...Object.keys((PROV_RAW as { _rebuilt_not_ported?: Record<string, string> })._rebuilt_not_ported ?? {}),
      ...Object.keys((PROV_RAW as { _target_native?: Record<string, string> })._target_native ?? {}),
    ]);
    const bad = Object.entries(IMPORTS)
      .filter(([, v]) => v.judgment === "no-source-baseline")
      .map(([k]) => k)
      .filter((k) => !baselineFree.has(k.split(" :: ")[0]));
    expect(
      bad,
      "these claim 'no-source-baseline' but their file IS declared with a source baseline,\n" +
        "so a real import comparison was owed and skipped:\n" + bad.join("\n")
    ).toEqual([]);
  });

  it("a 'different-but-checked' judgment carries a stated reason", () => {
    const unexplained = Object.entries(IMPORTS)
      .filter(([, v]) => v.judgment !== "same" && !v.note.trim())
      .map(([k]) => k);
    expect(unexplained, `divergent imports with no note:\n${unexplained.join("\n")}`).toEqual([]);
  });

  /**
   * ---- The map must match reality, in BOTH directions ----
   *
   * Everything above validates the map against itself. Cross-vendor review found what
   * that permits: an entry for `knowledge/page.tsx :: @/components/command-centre/
   * WikiEnhanceControl`, judged `must-change`, resolving to a target file that does
   * not exist — for a component KI-002 deliberately omitted and the page never
   * imports. Four assertions passed over it. A phantom entry does not merely sit
   * there being wrong; it INFLATES the map, and the map is the thing we point at to
   * say the import surface was reviewed. It reads as coverage.
   *
   * Deleting that one entry fixes one entry. These two tests fix the class: the map
   * cannot claim an import that no file makes, and no file can make an import the map
   * does not claim. Either direction failing is a real finding — the first means the
   * map overstates what was checked, the second means something entered the surface
   * unreviewed.
   */
  const ACTUAL = ACTUAL_IMPORTS;

  it("the actual-import set is populated (positive control)", () => {
    // Both directional tests below compare against ACTUAL. If the graph walk or the
    // specifier regex breaks, ACTUAL empties, and "no phantom entries" would still
    // pass while checking nothing. This is the check that stops that being silent.
    expect(ACTUAL.size).toBeGreaterThan(0);
  });

  it("no map entry describes an import that is not actually made", () => {
    const phantom = Object.keys(IMPORTS).filter((k) => !ACTUAL.has(k));
    expect(
      phantom,
      "provenance map entries with no corresponding import in the file named by the key.\n" +
        "The map overstates what was reviewed — these were 'checked' and do not exist:\n" +
        phantom.join("\n")
    ).toEqual([]);
  });

  it("every actual import in the capability graph has a map entry", () => {
    const unmapped = unmappedImports(IMPORTS, ACTUAL);
    expect(
      unmapped,
      "imports present in the capability graph with no provenance entry — these entered\n" +
        "the surface without a declared judgment:\n" + unmapped.join("\n")
    ).toEqual([]);
  });

  it("a map entry resolving to a target file names a file that exists", () => {
    const missing = Object.entries(IMPORTS)
      .map(([k, v]) => [k, /^file:\s*(.+)$/.exec(
        (v as unknown as { resolves_in_target?: string }).resolves_in_target ?? ""
      )] as const)
      .filter(([, m]) => m && !existsSync(join(ROOT, m[1].trim())))
      .map(([k, m]) => `${k} -> ${m![1].trim()}`);
    expect(
      missing,
      `map entries resolving to a target file that is absent from disk:\n${missing.join("\n")}`
    ).toEqual([]);
  });
});

describe("command-centre: no silent privilege change", () => {
  const PRIVILEGED = privilegedModules(importGraph().map(rel));

  it("at least one privileged module is in the graph (positive control)", () => {
    // Without this, a graph that reached no service-role client at all would make
    // every assertion below vacuously true and read as coverage.
    expect(
      [...PRIVILEGED],
      "no module in the capability graph builds a service-role client, so the privilege " +
        "checks below verified nothing. If that is genuinely true now, this control must " +
        "be revisited deliberately rather than deleted."
    ).not.toEqual([]);
  });

  it("every import reaching a privileged module declares it", () => {
    const silent = undeclaredPrivilegedImports(IMPORT_MAP, ACTUAL_IMPORTS, PRIVILEGED);
    expect(
      silent,
      "these imports resolve to a module that builds a service-role client (RLS bypassed)\n" +
        "but carry no `\"privilege\": \"service-role\"` declaration with a note:\n" +
        silent.join("\n")
    ).toEqual([]);
  });

  it("no entry claims service-role over a module that is not privileged", () => {
    const stale = phantomPrivilegeClaims(IMPORT_MAP, PRIVILEGED);
    expect(
      stale,
      "these entries declare service-role privilege but resolve to a module that builds no\n" +
        "such client. The claim overstates what was reviewed:\n" + stale.join("\n")
    ).toEqual([]);
  });
});

/**
 * ---- Mutation controls ----
 *
 * A gate that cannot fail is not a gate. Each control asserts the real map is clean,
 * then breaks exactly one thing IN MEMORY and asserts the same predicate reports it.
 * Nothing on disk is touched, so these run in CI on every commit rather than being a
 * procedure someone is trusted to have performed once.
 */
describe("command-centre: the provenance and privilege gates can fail (mutation controls)", () => {
  const files = importGraph().map(rel);
  const PRIVILEGED = privilegedModules(files);
  const clone = (): Record<string, ImportEntry> =>
    JSON.parse(JSON.stringify(IMPORT_MAP)) as Record<string, ImportEntry>;

  it("removing a file's provenance entry is caught", () => {
    const declared = new Set(DECLARED);
    const victim = files.find((f) => declared.has(f));
    expect(victim, "no declared file in the graph to mutate").toBeDefined();
    expect(undeclaredFiles(declared, files)).toEqual([]);
    declared.delete(victim!);
    expect(undeclaredFiles(declared, files)).toEqual([victim]);
  });

  it("removing an import's map entry is caught", () => {
    const map = clone();
    const victim = [...ACTUAL_IMPORTS][0];
    expect(victim, "no actual import to mutate").toBeDefined();
    expect(unmappedImports(map, ACTUAL_IMPORTS)).toEqual([]);
    delete map[victim];
    expect(unmappedImports(map, ACTUAL_IMPORTS)).toEqual([victim]);
  });

  it("removing or downgrading a privilege declaration is caught", () => {
    const declaredPrivileged = Object.keys(IMPORT_MAP)
      .filter((k) => IMPORT_MAP[k].privilege === "service-role")
      .sort();
    expect(
      declaredPrivileged,
      "no import declares service-role privilege, so this control proves nothing"
    ).not.toEqual([]);
    expect(undeclaredPrivilegedImports(IMPORT_MAP, ACTUAL_IMPORTS, PRIVILEGED)).toEqual([]);

    const removed = clone();
    for (const k of declaredPrivileged) delete removed[k].privilege;
    expect(undeclaredPrivilegedImports(removed, ACTUAL_IMPORTS, PRIVILEGED)).toEqual(
      declaredPrivileged
    );

    const downgraded = clone();
    for (const k of declaredPrivileged) downgraded[k].privilege = "anon";
    expect(undeclaredPrivilegedImports(downgraded, ACTUAL_IMPORTS, PRIVILEGED)).toEqual(
      declaredPrivileged
    );
  });

  it("a declaration with no stated reason is caught", () => {
    const map = clone();
    const victim = Object.keys(map).find((k) => map[k].privilege === "service-role");
    expect(victim).toBeDefined();
    map[victim!].note = "   ";
    expect(undeclaredPrivilegedImports(map, ACTUAL_IMPORTS, PRIVILEGED)).toEqual([victim]);
  });

  it("claiming service-role over a module that is not privileged is caught", () => {
    const map = clone();
    expect(phantomPrivilegeClaims(map, PRIVILEGED)).toEqual([]);
    const innocent = Object.keys(map).find((k) => map[k].privilege !== "service-role");
    expect(innocent).toBeDefined();
    map[innocent!].privilege = "service-role";
    expect(phantomPrivilegeClaims(map, PRIVILEGED)).toEqual([innocent]);
  });

  it("a module that BECOMES privileged with no import change is caught", () => {
    // The case no other check in this file can see: no specifier moves, no file enters
    // the graph, and an already-mapped module starts building a service-role client.
    const victim = Object.keys(IMPORT_MAP).find((k) => {
      const t = resolveEntryTarget(k);
      return t !== null && !PRIVILEGED.has(t) && IMPORT_MAP[k].privilege !== "service-role";
    });
    expect(victim, "no non-privileged in-repo import to promote").toBeDefined();
    const promoted = new Set([...PRIVILEGED, resolveEntryTarget(victim!)!]);
    expect(undeclaredPrivilegedImports(IMPORT_MAP, ACTUAL_IMPORTS, promoted)).toContain(victim);
  });
});
