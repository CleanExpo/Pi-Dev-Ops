// The production build must not need the network. `next/font/google` downloads
// every face from fonts.googleapis.com during `next build`; when that fetch
// fails, Turbopack aborts the whole build (main CI run 36682119471, 30/09/2026:
// 18 errors, "Can't resolve '@vercel/turbopack-next/internal/font/google/font'"),
// the prod smoke job is skipped, and production keeps serving the old build.
// Fonts are self-hosted with `next/font/local` from app/fonts/ instead, and
// the last test proves every src path the loaders name really exists.
import { describe, expect, it } from "vitest";
import { readdirSync, readFileSync, statSync, existsSync } from "fs";
import path from "path";

const ROOT = path.resolve(__dirname, "..");
const SKIP = new Set(["node_modules", ".next", "__tests__"]);

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    if (SKIP.has(name)) return [];
    const full = path.join(dir, name);
    if (statSync(full).isDirectory()) return sourceFiles(full);
    return /\.(tsx?|jsx?|mjs)$/.test(name) ? [full] : [];
  });
}

describe("fonts are self-hosted", () => {
  const files = sourceFiles(ROOT);

  it("scans real source (positive control)", () => {
    expect(files).toContain(path.join(ROOT, "app", "layout.tsx"));
  });

  it("no module imports next/font/google", () => {
    const offenders = files.filter((f) => readFileSync(f, "utf8").includes("next/font/google"));
    expect(offenders.map((f) => path.relative(ROOT, f))).toEqual([]);
  });

  it("every next/font/local src file exists", () => {
    const missing: string[] = [];
    let checked = 0;
    for (const f of files) {
      const text = readFileSync(f, "utf8");
      if (!text.includes("next/font/local")) continue;
      for (const m of text.matchAll(/path:\s*["']([^"']+\.woff2)["']/g)) {
        checked++;
        if (!existsSync(path.resolve(path.dirname(f), m[1]))) missing.push(`${path.relative(ROOT, f)} -> ${m[1]}`);
      }
    }
    expect(checked).toBeGreaterThan(0);
    expect(missing).toEqual([]);
  });
});
