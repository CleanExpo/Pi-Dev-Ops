// Shared helpers for the node-level tests. Synthetic data only.
import { spawn, spawnSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

export const PKG = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
export const GOLDEN = path.join(PKG, 'test/golden');
export const ENV = { ...process.env, LC_ALL: 'C', LANG: 'C', TZ: 'UTC' };
delete ENV.NODE_OPTIONS;

const made = [];
export function cleanupTemp() {
  for (const d of made.splice(0)) fs.rmSync(d, { recursive: true, force: true });
}

export function tempDir(prefix = 'lbos-test-') {
  const d = fs.mkdtempSync(path.join(os.tmpdir(), prefix));
  made.push(d);
  return d;
}

/** Fresh copy of the package, without node_modules. withDeps symlinks the real ones in. */
export function copyPackage({ withDeps = true } = {}) {
  const root = tempDir();
  const dir = path.join(root, 'pkg');
  fs.cpSync(PKG, dir, {
    recursive: true,
    filter: (src) => path.basename(src) !== 'node_modules',
  });
  if (withDeps) fs.symlinkSync(path.join(PKG, 'node_modules'), path.join(dir, 'node_modules'));
  return dir;
}

export function runCli(dir, args, { stdin = '', env = ENV, timeout = 20000 } = {}) {
  const r = spawnSync(process.execPath, [path.join(dir, 'bin/lbos.mjs'), ...args], {
    input: stdin,
    env,
    encoding: 'utf8',
    timeout,
    maxBuffer: 1 << 26,
  });
  let json = null;
  try {
    json = JSON.parse(r.stdout);
  } catch {
    json = null;
  }
  return { status: r.status, stdout: r.stdout, stderr: r.stderr, json };
}

export function runCliAsync(dir, args, stdin) {
  return new Promise((resolve) => {
    const child = spawn(process.execPath, [path.join(dir, 'bin/lbos.mjs'), ...args], { env: ENV });
    let stdout = '';
    let stderr = '';
    child.stdout.on('data', (d) => (stdout += d));
    child.stderr.on('data', (d) => (stderr += d));
    child.on('close', (status) => {
      let json = null;
      try {
        json = JSON.parse(stdout);
      } catch {
        json = null;
      }
      resolve({ status, stdout, stderr, json });
    });
    child.stdin.end(stdin);
  });
}

export function listGolden() {
  const dir = path.join(GOLDEN, 'inputs');
  return fs
    .readdirSync(dir)
    .filter((n) => n.endsWith('.json'))
    .sort()
    .map((n) => ({
      file: n,
      fixture: JSON.parse(fs.readFileSync(path.join(dir, n), 'utf8')),
      expectedText: fs.readFileSync(path.join(GOLDEN, 'expected', n), 'utf8'),
    }));
}

export function readJson(p) {
  return JSON.parse(fs.readFileSync(p, 'utf8'));
}

export const MARKER = 'ZZ-PLANTED-7731';

export function cliInputFor(fixture) {
  if (fixture.command === 'validate' || fixture.command === 'idempotency-key') return fixture.input;
  return fixture.input;
}

export function cliArgsFor(fixture) {
  if (fixture.command === 'validate') return ['validate', fixture.contract];
  return [fixture.command];
}

export function gitIn(cwd, ...args) {
  const r = spawnSync('git', args, {
    cwd,
    encoding: 'utf8',
    env: { ...process.env, GIT_AUTHOR_NAME: 't', GIT_AUTHOR_EMAIL: 't@example.invalid', GIT_COMMITTER_NAME: 't', GIT_COMMITTER_EMAIL: 't@example.invalid' },
  });
  if (r.status !== 0) throw new Error(`git ${args.join(' ')}: ${r.stderr}`);
  return r.stdout;
}
