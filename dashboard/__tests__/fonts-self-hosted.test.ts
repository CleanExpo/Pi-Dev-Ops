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

// Minimal WOFF2 cmap reader (WOFF2 spec section 5): enough to ask "does this file
// map codepoint X". Google served every subset of a family (latin, greek,
// cyrillic...), so a self-hosted file cut to latin alone silently drops glyphs;
// the π wordmark in app/page.tsx and app/(main)/layout.tsx renders in font-mono.
function woff2Cmap(file: string): (cp: number) => boolean {
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
  const data = brotliDecompressSync(b.subarray(pos, pos + b.readUInt32BE(20)));
  expect(cmapAt).toBeGreaterThanOrEqual(0);
  const n = data.readUInt16BE(cmapAt + 2);
  for (let i = 0; i < n; i++) {
    const rec = cmapAt + 4 + i * 8;
    const sub = cmapAt + data.readUInt32BE(rec + 4);
    const format = data.readUInt16BE(sub);
    if (format === 12) {
      const groups = data.readUInt32BE(sub + 12);
      return (cp) => {
        for (let g = 0; g < groups; g++) {
          const at = sub + 16 + g * 12;
          if (cp >= data.readUInt32BE(at) && cp <= data.readUInt32BE(at + 4)) return true;
        }
        return false;
      };
    }
    if (format === 4) {
      const segs = data.readUInt16BE(sub + 6) / 2;
      return (cp) => {
        for (let g = 0; g < segs; g++) {
          const end = data.readUInt16BE(sub + 14 + g * 2);
          const start = data.readUInt16BE(sub + 16 + segs * 2 + g * 2);
          if (cp >= start && cp <= end && cp !== 0xffff) return true;
        }
        return false;
      };
    }
  }
  throw new Error(`no format 4/12 cmap in ${file}`);
}

describe("self-hosted fonts keep the glyphs Google served", () => {
  const dir = path.join(ROOT, "app", "fonts");
  const woffs = readdirSync(dir).filter((f) => f.endsWith(".woff2"));

  it("every font maps Latin A (positive control for the reader)", () => {
    expect(woffs.length).toBeGreaterThan(0);
    const without = woffs.filter((f) => !woff2Cmap(path.join(dir, f))(0x41));
    expect(without).toEqual([]);
  });

  it.each(["inter-var.woff2", "jetbrains-mono-var.woff2", "syne-var.woff2"])(
    "%s maps π (Greek) and Ł (Latin-extended), as Google served",
    (name) => {
      const has = woff2Cmap(path.join(dir, name));
      expect(has(0x3c0)).toBe(true); // π, the product wordmark
      expect(has(0x0141)).toBe(true); // Ł, latin-ext
    }
  );
});
