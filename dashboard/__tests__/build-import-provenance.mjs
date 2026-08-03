#!/usr/bin/env node
/**
 * build-import-provenance.mjs — generate the import-level provenance skeleton.
 *
 * File-level provenance proves a file has a declared origin. It does NOT prove that
 * what its imports RESOLVE TO behaves the same in both apps. That gap is real and was
 * hit immediately: `@/lib/supabase/server` resolves in the source to an anon-key,
 * RLS-enforced client and in the target to a service-role client that bypasses RLS.
 * Same specifier, compatible shapes, clean typecheck, silent privilege change.
 *
 * Emits every import in every ported file with its source and target resolution so a
 * human can declare a judgment: same | different-but-checked | must-change.
 *
 * Usage: node __tests__/build-import-provenance.mjs
 */
import { existsSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";

const ROOT = resolve(process.cwd());
const PROV_PATH = join(ROOT, "__tests__", "command-centre-provenance.json");
const PROV = JSON.parse(readFileSync(PROV_PATH, "utf8"));
const BASELINE = PROV._baseline_root;

const cand = (b) => [`${b}.ts`, `${b}.tsx`, join(b, "index.ts"), join(b, "index.tsx"), b];

function resolveIn(spec, fromFile, root, aliasRoot) {
  let base;
  if (spec.startsWith("@/")) base = join(aliasRoot, spec.slice(2));
  else if (spec.startsWith(".")) base = resolve(dirname(fromFile), spec);
  else return { kind: "package", path: spec };
  for (const c of cand(base)) {
    if (existsSync(c) && statSync(c).isFile()) return { kind: "file", path: c.slice(root.length + 1).replace(/\\/g, "/") };
  }
  return { kind: "unresolved", path: spec };
}

const out = PROV.imports ?? {};
let added = 0;

for (const [ported, source] of Object.entries(PROV.files)) {
  const pPath = join(ROOT, ported);
  const sPath = join(BASELINE, source);
  if (!existsSync(pPath) || !pPath.match(/\.(ts|tsx)$/)) continue;

  const pSrc = readFileSync(pPath, "utf8");
  for (const m of pSrc.matchAll(/(?:from|import)\s+['"]([^'"]+)['"]/g)) {
    const spec = m[1];
    const key = `${ported} :: ${spec}`;
    if (out[key]) continue;

    const inTarget = resolveIn(spec, pPath, ROOT, ROOT);
    // The same specifier as written in the SOURCE file, resolved in source context.
    const inSource = existsSync(sPath)
      ? resolveIn(spec, sPath, BASELINE, BASELINE)
      : { kind: "baseline-missing", path: spec };

    out[key] = {
      specifier: spec,
      resolves_in_source: `${inSource.kind}: ${inSource.path}`,
      resolves_in_target: `${inTarget.kind}: ${inTarget.path}`,
      judgment: "UNDECLARED",
      note: "",
    };
    added++;
  }
}

PROV.imports = out;
PROV._imports_note =
  "Import-level provenance. judgment must be one of: same | different-but-checked | must-change. " +
  "UNDECLARED fails the suite exactly as an undeclared FILE does. File provenance proves origin; " +
  "this proves the imports still mean what they meant.";
writeFileSync(PROV_PATH, JSON.stringify(PROV, null, 2), "utf8");
console.log(`  import entries: ${Object.keys(out).length} (${added} new)`);
const undeclared = Object.values(out).filter((v) => v.judgment === "UNDECLARED").length;
console.log(`  UNDECLARED: ${undeclared}`);
