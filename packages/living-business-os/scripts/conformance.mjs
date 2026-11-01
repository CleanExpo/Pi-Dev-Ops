// Conformance: the single command that says whether this package is what it claims.
//
//   node scripts/conformance.mjs                full run
//   node scripts/conformance.mjs --env-only     only assert the environment
//   node scripts/conformance.mjs --rebuild-only only the dist reproducibility check
//
// Full run: environment asserted, package verified, dist rebuilt (outside the package)
// and compared file for file, goldens compared byte for byte in canonical form, then
// the package is verified again to prove nothing was written inside it.
import { spawnSync } from 'node:child_process';
import crypto from 'node:crypto';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { verifyPackage } from '../lib/verify.mjs';

const PKG = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const mode = process.argv[2] ?? '--full';

function fail(msg) {
  console.error(`conformance FAILED: ${msg}`);
  process.exit(1);
}

function assertEnvironment() {
  const prov = JSON.parse(fs.readFileSync(path.join(PKG, 'PROVENANCE.json'), 'utf8'));
  if (process.version !== prov.capture.node) fail(`Node ${process.version}, expected ${prov.capture.node}`);
  if (process.env.LC_ALL !== 'C' || process.env.LANG !== 'C') fail(`locale must be C (LC_ALL=${process.env.LC_ALL}, LANG=${process.env.LANG})`);
  const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
  if (tz !== prov.capture.time_zone) fail(`time zone ${tz}, expected ${prov.capture.time_zone}`);
  const loc = new Intl.Collator().resolvedOptions().locale;
  if (loc !== prov.capture.collator_locale) fail(`collator locale ${loc}, expected ${prov.capture.collator_locale}`);
  console.log(`environment ok: ${process.version}, TZ ${tz}, locale C, collator ${loc}`);
}

function listFiles(dir) {
  const out = new Map();
  const walk = (rel) => {
    for (const name of fs.readdirSync(path.join(dir, rel))) {
      const r = rel ? `${rel}/${name}` : name;
      const st = fs.lstatSync(path.join(dir, r));
      if (st.isDirectory()) walk(r);
      else out.set(r, crypto.createHash('sha256').update(fs.readFileSync(path.join(dir, r))).digest('hex'));
    }
  };
  walk('');
  return out;
}

function rebuildCheck() {
  const tsup = path.join(PKG, 'node_modules/tsup/dist/cli-default.js');
  if (!fs.existsSync(tsup)) fail('tsup is not installed; run npm ci');
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'lbos-rebuild-'));
  try {
    const r = spawnSync(process.execPath, [tsup, '--out-dir', tmp], { cwd: PKG, encoding: 'utf8' });
    if (r.status !== 0) fail(`rebuild failed:\n${r.stdout}${r.stderr}`);
    const built = listFiles(tmp);
    const committed = listFiles(path.join(PKG, 'dist'));
    const problems = [];
    for (const [f, h] of built) {
      if (!committed.has(f)) problems.push(`extra file emitted by the rebuild, not in dist: ${f}`);
      else if (committed.get(f) !== h) problems.push(`dist differs from rebuild: ${f}`);
    }
    for (const f of committed.keys()) if (!built.has(f)) problems.push(`dist has a file the rebuild does not produce: ${f}`);
    if (problems.length) fail(`dist is not reproducible from src\n  ${problems.join('\n  ')}`);
    console.log(`rebuild ok: ${built.size} files identical to dist/`);
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }
}

function reverify(label) {
  const v = verifyPackage(PKG);
  if (!v.ok) fail(`package does not verify ${label}: ${v.reason} ${v.detail}`);
  console.log(`package verified ${label}: ${v.manifest.package_digest}`);
}

function goldens() {
  const vitest = path.join(PKG, 'node_modules/vitest/vitest.mjs');
  const files = ['test/golden.test.mjs', 'test/golden-cli.test.mjs', 'test/corpus-coverage.test.mjs', 'test/provenance.test.mjs'];
  const r = spawnSync(process.execPath, [vitest, 'run', ...files], { cwd: PKG, encoding: 'utf8', env: process.env });
  process.stdout.write(r.stdout);
  if (r.status !== 0) {
    process.stderr.write(r.stderr);
    fail('goldens, acceptance corpus or provenance checks failed');
  }
}

assertEnvironment();
if (mode === '--env-only') process.exit(0);
if (mode === '--rebuild-only') {
  rebuildCheck();
  process.exit(0);
}
reverify('before');
rebuildCheck();
goldens();
reverify('after');
console.log('conformance ok');
