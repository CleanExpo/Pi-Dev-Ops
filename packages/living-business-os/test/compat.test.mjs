import { afterAll, describe, expect, it } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { ENV, PKG, cleanupTemp, gitIn, readJson, tempDir } from './helpers.mjs';

afterAll(cleanupTemp);

const REL = 'packages/living-business-os';
const node = (cwd, ...args) => spawnSync(process.execPath, args, { cwd, env: ENV, encoding: 'utf8' });

function copyPkgInto(root) {
  const dest = path.join(root, REL);
  fs.mkdirSync(path.dirname(dest), { recursive: true });
  fs.cpSync(PKG, dest, { recursive: true, filter: (s) => path.basename(s) !== 'node_modules' });
  return dest;
}

function rewrite(pkgDir) {
  gitIn(pkgDir, 'add', '-f', '-A');
  const r = node(pkgDir, 'scripts/manifest.mjs', '--write');
  if (r.status !== 0) throw new Error(`manifest --write failed: ${r.stdout}${r.stderr}`);
  gitIn(pkgDir, 'add', '-f', '-A');
}

function setVersion(pkgDir, v) {
  const p = path.join(pkgDir, 'package.json');
  const j = readJson(p);
  j.version = v;
  fs.writeFileSync(p, JSON.stringify(j, null, 2) + '\n');
}

/**
 * Build a scratch repository: a base commit, then a head working tree after `edit`.
 * Returns the compat result of `manifest.mjs --compat <base>` run from the head package.
 */
function scenario({ baseEdit, headEdit, noBasePackage = false }) {
  const root = tempDir('lbos-compat-');
  gitIn(root, 'init', '-q', '-b', 'main');
  let pkgDir;
  if (noBasePackage) {
    fs.writeFileSync(path.join(root, 'README.md'), 'base\n');
  } else {
    pkgDir = copyPkgInto(root);
    gitIn(root, 'add', '-f', '-A');
    if (baseEdit) {
      baseEdit(pkgDir);
      rewrite(pkgDir);
    }
  }
  gitIn(root, 'add', '-f', '-A');
  gitIn(root, 'commit', '-q', '-m', 'base');
  const base = gitIn(root, 'rev-parse', 'HEAD').trim();
  if (noBasePackage) {
    pkgDir = copyPkgInto(root);
    gitIn(root, 'add', '-f', '-A');
  }
  if (headEdit) headEdit(pkgDir);
  rewrite(pkgDir);
  const r = node(pkgDir, 'scripts/manifest.mjs', '--compat', base);
  const out = r.stdout + r.stderr;
  // A scenario must fail for the compatibility rule, never because the scratch head was malformed.
  if (/does not verify|usage:|Cannot find module/.test(out)) throw new Error(`scenario setup is broken: ${out}`);
  return { status: r.status, out };
}

const editJson = (rel, fn) => (dir) => {
  const p = path.join(dir, rel);
  const j = readJson(p);
  fn(j);
  fs.writeFileSync(p, JSON.stringify(j, null, 2) + '\n');
};
const GOLD = 'test/golden/expected/decide-worked-example.json';
const bump = (v) => (dir) => setVersion(dir, v);
const both = (...fns) => (dir) => fns.forEach((f) => f(dir));

describe('compatibility enforcement (--compat) negative controls', () => {
  it('control: no change at all passes', () => {
    expect(scenario({}).status).toBe(0);
  });
  it('control: a version bump with no golden or surface change passes', () => {
    expect(scenario({ headEdit: bump('1.0.1') }).status).toBe(0);
  });

  it('changed golden output with only a patch bump fails', () => {
    const r = scenario({ headEdit: both(editJson(GOLD, (j) => (j.ok[0].priorityIndex = 3.5)), bump('1.0.1')) });
    expect(r.status).not.toBe(0);
    expect(r.out).toMatch(/major/i);
  });
  it('changed golden output with a minor bump fails', () => {
    expect(scenario({ headEdit: both(editJson(GOLD, (j) => (j.ok[0].priorityIndex = 3.5)), bump('1.1.0')) }).status).not.toBe(0);
  });
  it('changed golden output with a major bump passes', () => {
    expect(scenario({ headEdit: both(editJson(GOLD, (j) => (j.ok[0].priorityIndex = 3.5)), bump('2.0.0')) }).status).toBe(0);
  });
  it('exit code changed with a minor bump fails; with major passes', () => {
    const change = editJson('contract-surface.json', (j) => (j.error_codes.TENANT_MISMATCH = 7));
    expect(scenario({ headEdit: both(change, bump('1.1.0')) }).status).not.toBe(0);
    expect(scenario({ headEdit: both(change, bump('2.0.0')) }).status).toBe(0);
  });
  it('envelope key removed with a minor bump fails', () => {
    const change = editJson('contract-surface.json', (j) => (j.envelope_keys = j.envelope_keys.filter((k) => k !== 'approval_required')));
    expect(scenario({ headEdit: both(change, bump('1.1.0')) }).status).not.toBe(0);
  });
  it('optional envelope field added: patch fails, minor passes', () => {
    const change = editJson('contract-surface.json', (j) => j.envelope_keys.push('notes'));
    expect(scenario({ headEdit: both(change, bump('1.0.1')) }).status).not.toBe(0);
    expect(scenario({ headEdit: both(change, bump('1.1.0')) }).status).toBe(0);
  });
  it('a command removed is major', () => {
    const change = editJson('contract-surface.json', (j) => (j.commands = j.commands.filter((c) => c !== 'questions')));
    expect(scenario({ headEdit: both(change, bump('1.1.0')) }).status).not.toBe(0);
  });
  it('a limit changed is major', () => {
    const change = editJson('contract-surface.json', (j) => (j.limits.max_signals = 600));
    expect(scenario({ headEdit: both(change, bump('1.1.0')) }).status).not.toBe(0);
  });

  it('additive result field (strict superset): patch fails, minor passes', () => {
    const change = editJson(GOLD, (j) => (j.ok[0].note = 'added'));
    expect(scenario({ headEdit: both(change, bump('1.0.1')) }).status).not.toBe(0);
    expect(scenario({ headEdit: both(change, bump('1.1.0')) }).status).toBe(0);
  });
  it('result field removed: minor fails', () => {
    const change = editJson(GOLD, (j) => delete j.ok[0].reasons);
    expect(scenario({ headEdit: both(change, bump('1.1.0')) }).status).not.toBe(0);
  });
  it('array length changed is not additive: minor fails', () => {
    const change = editJson(GOLD, (j) => j.ok.push({ ...j.ok[0], signalId: 'sig-2' }));
    expect(scenario({ headEdit: both(change, bump('1.1.0')) }).status).not.toBe(0);
  });
  it('tightening a corpus-covered rule (goals.max(10) to max(5), 7-goal must-accept fixture): minor fails', () => {
    const change = editJson('test/golden/expected/intent-accept-goals-7.json', (j) => {
      delete j.ok;
      j.zod_issues = [{ code: 'too_big', path: ['goals'] }];
    });
    expect(scenario({ headEdit: both(change, bump('1.1.0')) }).status).not.toBe(0);
    expect(scenario({ headEdit: both(change, bump('2.0.0')) }).status).toBe(0);
  });
  it('a new golden file (new contract case) is additive: minor passes, patch fails', () => {
    const add = (dir) => fs.writeFileSync(path.join(dir, 'test/golden/expected/zz-new.json'), '{\n  "ok": 1\n}\n');
    expect(scenario({ headEdit: both(add, bump('1.1.0')) }).status).toBe(0);
    expect(scenario({ headEdit: both(add, bump('1.0.1')) }).status).not.toBe(0);
  });
  it('a removed golden file is major', () => {
    const rm = (dir) => fs.rmSync(path.join(dir, 'test/golden/expected/decide-empty-signals.json'));
    expect(scenario({ headEdit: both(rm, bump('1.1.0')) }).status).not.toBe(0);
  });

  it('first publication (base lacks the package) at 1.0.0 passes', () => {
    const r = scenario({ noBasePackage: true });
    expect(r.status).toBe(0);
    expect(r.out).toMatch(/FIRST_PUBLICATION/);
  });
  it('first publication at any other version fails', () => {
    expect(scenario({ noBasePackage: true, headEdit: bump('1.0.1') }).status).not.toBe(0);
  });
  it('base MANIFEST malformed fails (never treated as first publication)', () => {
    const root = tempDir('lbos-compat-');
    gitIn(root, 'init', '-q', '-b', 'main');
    const pkgDir = copyPkgInto(root);
    fs.writeFileSync(path.join(pkgDir, 'MANIFEST.json'), '{ broken');
    gitIn(root, 'add', '-f', '-A');
    gitIn(root, 'commit', '-q', '-m', 'base');
    const base = gitIn(root, 'rev-parse', 'HEAD').trim();
    rewrite(pkgDir);
    const c = node(pkgDir, 'scripts/manifest.mjs', '--compat', base);
    expect(c.status).not.toBe(0);
    expect(c.stdout + c.stderr).not.toMatch(/FIRST_PUBLICATION/);
  });
  it('version regression (1.1.0 at the base, 1.0.5 at the head) fails', () => {
    const r = scenario({ baseEdit: bump('1.1.0'), headEdit: bump('1.0.5') });
    expect(r.status).not.toBe(0);
    expect(r.out).toMatch(/down|regress|lower/i);
  });
  it('head whose files do not match its MANIFEST fails', () => {
    const root = tempDir('lbos-compat-');
    gitIn(root, 'init', '-q', '-b', 'main');
    const pkgDir = copyPkgInto(root);
    gitIn(root, 'add', '-f', '-A');
    gitIn(root, 'commit', '-q', '-m', 'base');
    const base = gitIn(root, 'rev-parse', 'HEAD').trim();
    fs.appendFileSync(path.join(pkgDir, 'contract-surface.json'), ' ');
    const c = node(pkgDir, 'scripts/manifest.mjs', '--compat', base);
    expect(c.status).not.toBe(0);
  });
});
