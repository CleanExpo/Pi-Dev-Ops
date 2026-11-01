// MANIFEST.json generation, checking and compatibility enforcement.
//
//   node scripts/manifest.mjs --write            regenerate MANIFEST.json from `git ls-files`
//   node scripts/manifest.mjs --check            verify the filesystem against MANIFEST.json
//   node scripts/manifest.mjs --compat <base>    enforce the version rule against <base>
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  IntegrityError, MANIFEST_NAME, PACKAGE_NAME, digestOf, isGolden, isSurface, parseManifest,
  sha256Hex, subsetDigest, verifyPackage,
} from '../lib/verify.mjs';

const PKG = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const git = (cwd, ...args) => execFileSync('git', args, { cwd, encoding: 'buffer', maxBuffer: 1 << 28, stdio: ['ignore', 'pipe', 'pipe'] });

function trackedFiles() {
  const out = git(PKG, 'ls-files', '-z', '--', '.').toString('utf8');
  return out.split('\0').filter(Boolean).filter((p) => p !== MANIFEST_NAME);
}

function contractVersion() {
  const m = /CONTRACT_VERSION\s*=\s*'([^']+)'/.exec(fs.readFileSync(path.join(PKG, 'src/index.ts'), 'utf8'));
  if (!m) throw new Error('CONTRACT_VERSION not found in src/index.ts');
  return m[1];
}

function buildManifest() {
  const files = trackedFiles().map((rel) => {
    const abs = path.join(PKG, rel);
    const st = fs.lstatSync(abs);
    if (!st.isFile()) throw new Error(`tracked path is not a regular file: ${rel}`);
    const buf = fs.readFileSync(abs);
    return { path: rel, sha256: sha256Hex(buf), bytes: buf.length, mode: st.mode & 0o111 ? '100755' : '100644' };
  });
  files.sort((a, b) => Buffer.compare(Buffer.from(a.path), Buffer.from(b.path)));
  return {
    schema: 'lbos-manifest/1',
    package: PACKAGE_NAME,
    package_version: JSON.parse(fs.readFileSync(path.join(PKG, 'package.json'), 'utf8')).version,
    contract_version: contractVersion(),
    package_digest: digestOf(files),
    golden_digest: subsetDigest(files, isGolden),
    surface_digest: subsetDigest(files, isSurface),
    files,
  };
}

function fail(msg) {
  console.error(`manifest: ${msg}`);
  process.exit(1);
}

function write() {
  const m = buildManifest();
  fs.writeFileSync(path.join(PKG, MANIFEST_NAME), JSON.stringify(m, null, 2) + '\n');
  console.log(`manifest written: ${m.files.length} files, package_digest ${m.package_digest}`);
}

function check() {
  const v = verifyPackage(PKG);
  if (!v.ok) fail(`${v.reason}${v.detail ? `: ${v.detail}` : ''}`);
  let tracked;
  try {
    tracked = trackedFiles();
  } catch {
    tracked = null; // no git (vendored copy): the filesystem check above is the whole check
  }
  if (tracked) {
    const listed = v.manifest.files.map((f) => f.path).sort();
    const a = JSON.stringify([...tracked].sort());
    if (a !== JSON.stringify(listed)) fail('MANIFEST does not list exactly the tracked files; run --write after git add');
    const modes = new Map(
      git(PKG, 'ls-files', '-s', '-z', '--', '.').toString('utf8').split('\0').filter(Boolean).map((l) => [l.split('\t')[1], l.slice(0, 6)]),
    );
    for (const f of v.manifest.files) if (modes.get(f.path) !== f.mode) fail(`git mode differs from MANIFEST for ${f.path}`);
  }
  if (v.manifest.contract_version !== contractVersion()) fail('contract_version differs from src/index.ts');
  console.log(`manifest ok: package_digest ${v.manifest.package_digest}`);
}

// ---------- compatibility (section 11.3 / 11.4) ----------

const RANK = { none: 0, patch: 1, minor: 2, major: 3 };
const semver = (v) => {
  const m = /^(\d+)\.(\d+)\.(\d+)$/.exec(v);
  if (!m) fail(`not a plain semantic version: ${v}`);
  return m.slice(1).map(Number);
};
const isObj = (v) => v !== null && typeof v === 'object' && !Array.isArray(v);

/** Every object in old is a deep subset of new (same values, only new keys); arrays keep length and order. */
export function deepSubset(o, n) {
  if (Array.isArray(o)) return Array.isArray(n) && o.length === n.length && o.every((x, i) => deepSubset(x, n[i]));
  if (isObj(o)) return isObj(n) && Object.keys(o).every((k) => k in n && deepSubset(o[k], n[k]));
  return o === n;
}

/** Surface: arrays of scalars are sets (additions allowed); objects may gain keys; scalars must not change. */
export function surfaceAdditive(o, n) {
  if (Array.isArray(o)) {
    if (!Array.isArray(n)) return false;
    if (o.every((x) => !isObj(x) && !Array.isArray(x))) return o.every((x) => n.includes(x));
    return deepSubset(o, n);
  }
  if (isObj(o)) return isObj(n) && Object.keys(o).every((k) => k in n && surfaceAdditive(o[k], n[k]));
  return o === n;
}

function baseFile(toplevel, base, rel) {
  return git(toplevel, 'show', `${base}:${rel}`);
}

function compat(base) {
  const v = verifyPackage(PKG);
  if (!v.ok) fail(`head package does not verify (${v.reason} ${v.detail}); run --write`);
  const head = v.manifest;
  const toplevel = git(PKG, 'rev-parse', '--show-toplevel').toString().trim();
  const relPkg = path.relative(fs.realpathSync(toplevel), fs.realpathSync(PKG)).split(path.sep).join('/');
  const rel = (p) => `${relPkg}/${p}`;

  let baseText;
  try {
    baseText = baseFile(toplevel, base, rel(MANIFEST_NAME)).toString('utf8');
  } catch {
    // Distinguish "package absent at the base" from "unreadable": ask the tree itself.
    let listing;
    try {
      listing = git(toplevel, 'ls-tree', '--name-only', base, '--', relPkg).toString().trim();
    } catch {
      fail(`cannot read base ${base}`);
    }
    if (listing !== '') fail('base has the package directory but its MANIFEST is unreadable; not a first publication');
    if (head.package_version !== '1.0.0') fail(`FIRST_PUBLICATION must be version 1.0.0, found ${head.package_version}`);
    console.log('compat ok: FIRST_PUBLICATION (package absent at base) at 1.0.0');
    return;
  }
  let prior;
  try {
    prior = parseManifest(baseText);
  } catch (e) {
    fail(`base MANIFEST is malformed (${e instanceof IntegrityError ? e.reason : 'invalid'}); not treated as a first publication`);
  }

  const [bM, bm, bp] = semver(prior.package_version);
  const [hM, hm, hp] = semver(head.package_version);
  if (hM < bM || (hM === bM && (hm < bm || (hm === bm && hp < bp)))) {
    fail(`version went down: ${prior.package_version} at base, ${head.package_version} at head`);
  }
  const actual = hM > bM ? 'major' : hm > bm ? 'minor' : hp > bp ? 'patch' : 'none';

  let required = 'none';
  const need = (level, why) => {
    if (RANK[level] > RANK[required]) required = level;
    reasons.push(`${level}: ${why}`);
  };
  const reasons = [];

  if (prior.golden_digest !== head.golden_digest) {
    const oldG = new Map(prior.files.filter((f) => isGolden(f.path)).map((f) => [f.path, f]));
    const newG = new Map(head.files.filter((f) => isGolden(f.path)).map((f) => [f.path, f]));
    for (const p of oldG.keys()) if (!newG.has(p)) need('major', `golden removed: ${p}`);
    for (const [p, f] of newG) {
      if (!oldG.has(p)) need('minor', `golden added: ${p}`);
      else if (oldG.get(p).sha256 !== f.sha256) {
        const before = JSON.parse(baseFile(toplevel, base, rel(p)).toString('utf8'));
        const after = JSON.parse(fs.readFileSync(path.join(PKG, p), 'utf8'));
        if (deepSubset(before, after)) need('minor', `golden extended additively: ${p}`);
        else need('major', `golden output changed: ${p}`);
      }
    }
  }
  if (prior.surface_digest !== head.surface_digest) {
    const before = JSON.parse(baseFile(toplevel, base, rel('contract-surface.json')).toString('utf8'));
    const after = JSON.parse(fs.readFileSync(path.join(PKG, 'contract-surface.json'), 'utf8'));
    if (surfaceAdditive(before, after)) need('minor', 'contract surface extended additively');
    else need('major', 'contract surface has a removal or a change');
  }

  if (RANK[actual] < RANK[required]) {
    fail(`version ${prior.package_version} -> ${head.package_version} is a ${actual} bump but the change needs at least ${required}:\n  ${reasons.join('\n  ')}`);
  }
  console.log(`compat ok: ${prior.package_version} -> ${head.package_version} (${actual}); required at least ${required}`);
}

const [mode, arg] = process.argv.slice(2);
try {
  if (mode === '--write') write();
  else if (mode === '--check') check();
  else if (mode === '--compat' && arg) compat(arg);
  else fail('usage: manifest.mjs --write | --check | --compat <base-ref>');
} catch (e) {
  fail(e instanceof Error ? e.message : String(e));
}
