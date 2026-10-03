/**
 * RA-7898 T5 (look rules) and G2/G3 (no new write path) — mechanical checks
 * over the files this change adds. docs/specs/modular-boards.md §6, §7.
 */
import { execFileSync } from "node:child_process";
import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

const DASH = path.resolve(__dirname, "..");
const REPO = path.resolve(DASH, "..");

function files(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const p = path.join(dir, name);
    return statSync(p).isDirectory() ? files(p) : [p];
  });
}

const BOARD_FILES = [...files(path.join(DASH, "components/boards")), ...files(path.join(DASH, "lib/boards"))];
const CODE = BOARD_FILES.filter((f) => /\.(tsx?|css)$/.test(f));
const rel = (f: string) => path.relative(DASH, f);

describe("look rules (T5)", () => {
  it("found the board files (positive control)", () => {
    expect(CODE.some((f) => f.endsWith("ModuleFrame.tsx"))).toBe(true);
    expect(CODE.length).toBeGreaterThan(20);
  });

  it("no hex colour literal in components/boards or lib/boards", () => {
    const hits = CODE.flatMap((f) => (readFileSync(f, "utf8").match(/#[0-9a-fA-F]{3,8}\b/g) ?? []).map((h) => `${rel(f)}: ${h}`));
    expect(hits).toEqual([]);
  });

  it("no literal array of data rows in the view components", () => {
    // An array literal of object literals in a view is a table of made-up rows.
    const views = CODE.filter((f) => f.includes(`${path.sep}views${path.sep}`) && f.endsWith(".tsx"));
    const hits = views.filter((f) => /\[\s*\{\s*\w+\s*:/.test(readFileSync(f, "utf8"))).map(rel);
    // The only matches are ring slices whose values are computed from the live payload.
    expect(hits.sort()).toEqual(["components/boards/views/fleet-chain.tsx", "components/boards/views/metrics.tsx"]);
    for (const f of hits) {
      for (const m of readFileSync(path.join(DASH, f), "utf8").matchAll(/\{ label: "[^"]+", value: ([^,]+),/g)) {
        expect(m[1], `${f} slice value must be computed, not a literal`).not.toMatch(/^\d+$/);
      }
    }
  });

  it("the frame title is never uppercased", () => {
    const css = readFileSync(path.join(DASH, "components/boards/boards.module.css"), "utf8");
    const title = css.match(/\.title\s*\{[^}]*\}/)![0];
    expect(title).not.toMatch(/uppercase/);
    expect(readFileSync(path.join(DASH, "components/boards/ModuleFrame.tsx"), "utf8")).not.toMatch(/<h3[^>]*uppercase/);
  });

  it("no icon-library import in the board files", () => {
    const hits = CODE.filter((f) => /from ["'](lucide-react|@heroicons\/react|@fortawesome)/.test(readFileSync(f, "utf8"))).map(rel);
    expect(hits).toEqual([]);
  });

  it("the static North Star text names its source file", () => {
    expect(readFileSync(path.join(DASH, "components/boards/views/founder.tsx"), "utf8")).toContain("docs/governance/NEXUS-NORTH-STAR.md");
  });
});

describe("no new write path (G2, G3)", () => {
  it("board code makes no non-GET request", () => {
    const hits = CODE.filter((f) => /method\s*:|["'](POST|PUT|PATCH|DELETE)["']/.test(readFileSync(f, "utf8"))).map(rel);
    expect(hits).toEqual([]);
  });

  it("tree: no API route belongs to boards, and no API route or table file mentions them", () => {
    expect(() => statSync(path.join(DASH, "app/api/boards"))).toThrow();
    const apiFiles = files(path.join(DASH, "app/api")).filter((f) => /\.(ts|tsx)$/.test(f));
    expect(apiFiles.length).toBeGreaterThan(10); // positive control: the walk found the routes
    expect(apiFiles.filter((f) => /lib\/boards|components\/boards/.test(readFileSync(f, "utf8"))).map(rel)).toEqual([]);
    const sql = [...files(path.join(REPO, "supabase")), ...files(path.join(REPO, "mesh/schema"))].filter((f) => f.endsWith(".sql"));
    // A table whose name ends in "board(s)" would be board storage (intake_board_rounds is not).
    const boardTable = /create table\s+(if not exists\s+)?[\w."]*boards?"?\s*\(/i;
    expect(sql.length).toBeGreaterThan(5); // positive control: the walk found the migrations
    expect(sql.filter((f) => boardTable.test(readFileSync(f, "utf8"))).map((f) => path.relative(REPO, f))).toEqual([]);
  });

  // The diff-relative half needs main's history. A shallow checkout has none: the
  // test is then reported as SKIPPED (visible in the run), never as a pass.
  const hasMain = (() => {
    try { execFileSync("git", ["-C", REPO, "rev-parse", "--verify", "origin/main"], { stdio: "ignore" }); return true; } catch { return false; }
  })();
  it.skipIf(!hasMain)("diff: no added API route, mutating handler or table against origin/main", () => {
    const diff = execFileSync("git", ["-C", REPO, "diff", "--name-status", "origin/main...HEAD"], { encoding: "utf8" });
    const added = diff.split("\n").filter((l) => l.startsWith("A\t")).map((l) => l.slice(2));
    expect(added.filter((f) => f.startsWith("dashboard/app/api/"))).toEqual([]);
    expect(added.filter((f) => /^(supabase|mesh\/schema)\//.test(f))).toEqual([]);
    const patch = execFileSync("git", ["-C", REPO, "diff", "origin/main...HEAD", "--", "dashboard/app/api", "supabase", "mesh/schema", "app/server/routes"], { encoding: "utf8" });
    const addedLines = patch.split("\n").filter((l) => l.startsWith("+") && !l.startsWith("+++"));
    expect(addedLines.filter((l) => /export\s+(async\s+)?function\s+(POST|PUT|PATCH|DELETE)\b|create\s+table/i.test(l))).toEqual([]);
  });

  it("the boards pages live under /control, which proxy.ts protects", () => {
    const proxy = readFileSync(path.join(DASH, "proxy.ts"), "utf8");
    expect(proxy).toMatch(/PROTECTED_PAGE_PREFIXES[\s\S]*?"\/control"/);
    expect(statSync(path.join(DASH, "app/(main)/control/boards/page.tsx")).isFile()).toBe(true);
    expect(statSync(path.join(DASH, "app/(main)/control/boards/kiosk/page.tsx")).isFile()).toBe(true);
  });
});
