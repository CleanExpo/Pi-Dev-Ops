// The production build must not need the network. `next/font/google` downloads
// every face from fonts.googleapis.com during `next build`; when that fetch
// fails, Turbopack aborts the whole build (main CI run 36682119471, 30/09/2026:
// 18 errors, "Can't resolve '@vercel/turbopack-next/internal/font/google/font'"),
// the prod smoke job is skipped, and production keeps serving the old build.
// Fonts are self-hosted with `next/font/local` from app/fonts/ instead, and
// the last test proves every src path the loaders name really exists.
import { describe, expect, it } from "vitest";
import { readdirSync, readFileSync, statSync, existsSync } from "fs";
import { brotliDecompressSync } from "zlib";
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

// Minimal WOFF2 cmap reader (WOFF2 spec section 5): returns every codepoint the
// file maps to a real glyph. next/font/google put every subset Google serves on
// the page (latin, latin-ext, greek, cyrillic, vietnamese...), so a self-hosted
// file must cover the same set or text silently falls back to another face (the
// π wordmark in app/page.tsx renders in font-mono). The expected set per file is
// pinned in fixtures/font-served-codepoints.json, taken from Google's own files.
function woff2Codepoints(file: string): Set<number> {
  const b = readFileSync(file);
  expect(b.toString("latin1", 0, 4)).toBe("wOF2");
  const numTables = b.readUInt16BE(12);
  let pos = 48;
  const base128 = () => {
    let v = 0;
    for (let i = 0; i < 5; i++) {
      const byte = b[pos++];
      v = v * 128 + (byte & 0x7f);
      if (!(byte & 0x80)) return v;
    }
    throw new Error("bad UIntBase128");
  };
  let offset = 0;
  let cmapAt = -1;
  for (let t = 0; t < numTables; t++) {
    const flags = b[pos++];
    const tagIdx = flags & 0x3f;
    if (tagIdx === 63) pos += 4;
    const orig = base128();
    const version = (flags >> 6) & 3;
    const transformed = tagIdx === 10 || tagIdx === 11 ? version === 0 : version !== 0;
    const len = transformed ? base128() : orig;
    if (tagIdx === 0) cmapAt = offset;
    offset += len;
  }
  const d = brotliDecompressSync(b.subarray(pos, pos + b.readUInt32BE(20)));
  expect(cmapAt).toBeGreaterThanOrEqual(0);
  const out = new Set<number>();
  const n = d.readUInt16BE(cmapAt + 2);
  for (let i = 0; i < n; i++) {
    const sub = cmapAt + d.readUInt32BE(cmapAt + 4 + i * 8 + 4);
    const format = d.readUInt16BE(sub);
    if (format === 12) {
      for (let g = 0, groups = d.readUInt32BE(sub + 12); g < groups; g++) {
        const at = sub + 16 + g * 12;
        const [start, end, glyph] = [d.readUInt32BE(at), d.readUInt32BE(at + 4), d.readUInt32BE(at + 8)];
        for (let cp = start; cp <= end; cp++) if (glyph + cp - start) out.add(cp);
      }
    } else if (format === 4) {
      const segs = d.readUInt16BE(sub + 6) / 2;
      const ends = sub + 14, starts = ends + segs * 2 + 2, deltas = starts + segs * 2, ros = deltas + segs * 2;
      for (let g = 0; g < segs; g++) {
        const [end, start] = [d.readUInt16BE(ends + g * 2), d.readUInt16BE(starts + g * 2)];
        const delta = d.readInt16BE(deltas + g * 2), ro = d.readUInt16BE(ros + g * 2);
        for (let cp = start; cp <= end && cp !== 0xffff; cp++) {
          let glyph = ro ? d.readUInt16BE(ros + g * 2 + ro + (cp - start) * 2) : cp;
          if (ro && glyph === 0) continue;
          glyph = (glyph + delta) & 0xffff;
          if (glyph) out.add(cp);
        }
      }
    }
  }
  expect(out.size).toBeGreaterThan(0);
  return out;
}

describe("self-hosted fonts keep every glyph Google served", () => {
  const dir = path.join(ROOT, "app", "fonts");
  const served: Record<string, { count: number; ranges: [number, number][] }> = JSON.parse(
    readFileSync(path.join(__dirname, "fixtures", "font-served-codepoints.json"), "utf8")
  ).files;

  it("the manifest names exactly the committed font files", () => {
    const woffs = readdirSync(dir).filter((f) => f.endsWith(".woff2")).sort();
    expect(Object.keys(served).sort()).toEqual(woffs);
  });

  it.each(Object.keys(served))("%s maps every codepoint Google served", (name) => {
    const expected = served[name].ranges.flatMap(([a, z]) => Array.from({ length: z - a + 1 }, (_, i) => a + i));
    expect(expected.length).toBe(served[name].count);
    const has = woff2Codepoints(path.join(dir, name));
    const missing = expected.filter((cp) => !has.has(cp)).map((cp) => "U+" + cp.toString(16).toUpperCase());
    expect(missing).toEqual([]);
  });

  it("the π wordmark glyph is in the mono and sans faces", () => {
    for (const f of ["jetbrains-mono-var.woff2", "inter-var.woff2"]) expect(woff2Codepoints(path.join(dir, f)).has(0x3c0)).toBe(true);
  });
});
