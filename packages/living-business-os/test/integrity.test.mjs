import { afterAll, describe, expect, it } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { ENV, PKG, cleanupTemp, copyPackage, readJson, runCli } from './helpers.mjs';
import { verifyPackage } from '../lib/verify.mjs';

afterAll(cleanupTemp);

const writeManifest = (dir, m) => fs.writeFileSync(path.join(dir, 'MANIFEST.json'), JSON.stringify(m, null, 2) + '\n');
const manifestOf = (dir) => readJson(path.join(dir, 'MANIFEST.json'));

/** Every case starts from a fresh, untouched copy that must pass first (T3). */
function baseline({ withDeps = true } = {}) {
  const dir = copyPackage({ withDeps });
  const v = verifyPackage(dir);
  expect(v, JSON.stringify(v)).toMatchObject({ ok: true });
  if (withDeps) {
    const r = runCli(dir, ['version']);
    expect(r.status).toBe(0);
    expect(r.json.identity).toBe('verified');
  }
  return dir;
}

function expectRefused(dir, reason) {
  const v = verifyPackage(dir);
  expect(v.ok).toBe(false);
  if (reason) expect(v.reason).toBe(reason);
  const r = runCli(dir, ['version']);
  expect(r.status).toBe(4);
  expectUnverified(r);
  return r;
}

function expectUnverified(r) {
  expect(r.json.ok).toBe(false);
  expect(r.json.identity).toBe('unverified');
  expect(r.json.contract_version).toBeNull();
  expect(r.json.package_version).toBeNull();
  expect(r.json.package_digest).toBeNull();
  expect(r.json.result).toBeNull();
  expect(r.json.error.code).toBe('INTEGRITY');
  expect(r.stderr).toBe('');
}

describe('baseline and positive control (A1)', () => {
  it('an untouched copy verifies, MANIFEST.json is not reported as an extra file', () => {
    const dir = baseline();
    const v = verifyPackage(dir);
    expect(v.ok).toBe(true);
    expect(v.manifest.files.map((f) => f.path)).not.toContain('MANIFEST.json');
  });
  it('node_modules is ignored', () => {
    const dir = baseline();
    fs.mkdirSync(path.join(dir, 'node_modules/.cache-x'), { recursive: true });
    expect(verifyPackage(dir).ok).toBe(true);
  });
});

describe('tamper cases are refused with exit 4 and an unverified identity', () => {
  for (const f of ['src/contracts.ts', 'dist/index.js']) {
    it(`one byte flipped in ${f}`, () => {
      const dir = baseline();
      const p = path.join(dir, f);
      const b = fs.readFileSync(p);
      b[10] = b[10] ^ 1;
      fs.writeFileSync(p, b);
      expectRefused(dir, 'HASH_MISMATCH');
    });
  }
  it('a byte appended (hash and size both change)', () => {
    const dir = baseline();
    fs.appendFileSync(path.join(dir, 'src/contracts.ts'), '\n');
    expectRefused(dir);
  });
  it('a deleted file', () => {
    const dir = baseline();
    fs.rmSync(path.join(dir, 'src/decision-engine.ts'));
    expectRefused(dir, 'MISSING_FILE');
  });
  it('an added file', () => {
    const dir = baseline();
    fs.writeFileSync(path.join(dir, 'src/extra.ts'), 'export {};\n');
    expectRefused(dir, 'EXTRA_FILE');
  });
  it('a file mode changed to executable', () => {
    const dir = baseline();
    fs.chmodSync(path.join(dir, 'src/contracts.ts'), 0o755);
    expectRefused(dir, 'MODE_MISMATCH');
  });
  it('a symlink placed in the package', () => {
    const dir = baseline();
    fs.symlinkSync('/etc/hosts', path.join(dir, 'src/link.ts'));
    expectRefused(dir, 'SYMLINK');
  });
  it('a symlink replacing a listed file', () => {
    const dir = baseline();
    fs.rmSync(path.join(dir, 'src/contracts.ts'));
    fs.symlinkSync(path.join(PKG, 'src/contracts.ts'), path.join(dir, 'src/contracts.ts'));
    expectRefused(dir, 'SYMLINK');
  });
  it('MANIFEST missing', () => {
    const dir = baseline();
    fs.rmSync(path.join(dir, 'MANIFEST.json'));
    const r = expectRefused(dir, 'MANIFEST_MISSING');
    expect(r.json.error.message).toBeTruthy();
  });
  it('MANIFEST not valid JSON', () => {
    const dir = baseline();
    fs.writeFileSync(path.join(dir, 'MANIFEST.json'), '{ not json');
    expectRefused(dir, 'MANIFEST_INVALID');
  });
  it('MANIFEST valid JSON of the wrong shape', () => {
    const dir = baseline();
    fs.writeFileSync(path.join(dir, 'MANIFEST.json'), '[]');
    expectRefused(dir, 'MANIFEST_INVALID');
  });
  for (const [label, bad] of [['../x', '../x'], ['/etc/x', '/etc/x'], ['a backslash', 'src\\contracts.ts']]) {
    it(`a MANIFEST entry using ${label}`, () => {
      const dir = baseline();
      const m = manifestOf(dir);
      m.files.push({ path: bad, sha256: '0'.repeat(64), bytes: 1, mode: '100644' });
      writeManifest(dir, m);
      expectRefused(dir, 'MANIFEST_PATH_UNSAFE');
    });
  }
  it('a MANIFEST entry appearing twice', () => {
    const dir = baseline();
    const m = manifestOf(dir);
    m.files.push({ ...m.files[0] });
    writeManifest(dir, m);
    expectRefused(dir, 'DUPLICATE_PATH');
  });
  it('MANIFEST package_digest altered', () => {
    const dir = baseline();
    const m = manifestOf(dir);
    m.package_digest = '0'.repeat(64);
    writeManifest(dir, m);
    expectRefused(dir, 'DIGEST_MISMATCH');
  });
  it('MANIFEST golden_digest altered', () => {
    const dir = baseline();
    const m = manifestOf(dir);
    m.golden_digest = '0'.repeat(64);
    writeManifest(dir, m);
    expectRefused(dir, 'METADATA_MISMATCH');
  });
  it('MANIFEST surface_digest altered', () => {
    const dir = baseline();
    const m = manifestOf(dir);
    m.surface_digest = '0'.repeat(64);
    writeManifest(dir, m);
    expectRefused(dir, 'METADATA_MISMATCH');
  });
  it('package_version different from package.json', () => {
    const dir = baseline();
    const m = manifestOf(dir);
    m.package_version = '9.9.9';
    writeManifest(dir, m);
    expectRefused(dir, 'VERSION_MISMATCH');
  });
  it('CONTRACT_VERSION different from MANIFEST (start-up step 4)', () => {
    const dir = baseline();
    const m = manifestOf(dir);
    m.contract_version = 'lbos.contracts.v2';
    writeManifest(dir, m);
    expect(verifyPackage(dir).ok).toBe(true); // bytes are fine: only the runner can see this one
    const r = runCli(dir, ['version']);
    expect(r.status).toBe(4);
    expectUnverified(r);
  });
  it('zod removed from node_modules: DEPENDENCY_MISSING (start-up step 3)', () => {
    const dir = baseline({ withDeps: false });
    expect(verifyPackage(dir).ok).toBe(true);
    const r = runCli(dir, ['version']);
    expect(r.status).toBe(4);
    expect(r.json.error.code).toBe('DEPENDENCY_MISSING');
    expect(r.json.identity).toBe('unverified');
    expect(r.json.package_digest).toBeNull();
    expect(r.json.contract_version).toBeNull();
  });
  it('no import is attempted when verification fails (a poisoned dist never runs)', () => {
    const dir = baseline();
    const marker = path.join(dir, '..', 'dist-ran.txt');
    fs.writeFileSync(path.join(dir, 'dist/index.js'), `import fs from 'node:fs'; fs.writeFileSync(${JSON.stringify(marker)}, 'ran');\n`);
    const r = runCli(dir, ['version']);
    expect(r.status).toBe(4);
    expect(fs.existsSync(marker)).toBe(false);
  });
  it('temporary build output left in the package is an extra file', () => {
    const dir = baseline();
    fs.mkdirSync(path.join(dir, '.build-tmp'));
    fs.writeFileSync(path.join(dir, '.build-tmp/x.js'), 'x');
    expectRefused(dir, 'EXTRA_FILE');
  });
});

describe('stale or non-reproducible dist is caught by the conformance rebuild check', () => {
  const run = (dir, ...a) =>
    spawnSync(process.execPath, [path.join(dir, 'scripts/conformance.mjs'), ...a], { cwd: dir, env: ENV, encoding: 'utf8' });

  it('baseline rebuild matches', () => {
    const dir = baseline();
    const r = run(dir, '--rebuild-only');
    expect(r.status, r.stdout + r.stderr).toBe(0);
  }, 120000);
  it('source changed, dist not rebuilt', () => {
    const dir = baseline();
    fs.appendFileSync(path.join(dir, 'src/index.ts'), '\nexport const EXTRA = 1;\n');
    const r = run(dir, '--rebuild-only');
    expect(r.status).not.toBe(0);
    expect(r.stdout + r.stderr).toMatch(/dist differs|rebuild/i);
  }, 120000);
  it('an extra file emitted by the rebuild (entry added) is caught', () => {
    const dir = baseline();
    fs.writeFileSync(path.join(dir, 'src/second.ts'), 'export const second = 1;\n');
    fs.writeFileSync(path.join(dir, 'tsup.config.ts'), fs.readFileSync(path.join(dir, 'tsup.config.ts'), 'utf8').replace("entry: ['src/index.ts']", "entry: ['src/index.ts', 'src/second.ts']"));
    const r = run(dir, '--rebuild-only');
    expect(r.status).not.toBe(0);
    expect(r.stdout + r.stderr).toMatch(/extra|not in dist|differs/i);
  }, 120000);
  it('the rebuild never writes inside the package (A5) and re-verifies afterwards', () => {
    const dir = baseline();
    const before = verifyPackage(dir);
    expect(before.ok).toBe(true);
    const r = run(dir, '--rebuild-only');
    expect(r.status, r.stdout + r.stderr).toBe(0);
    expect(verifyPackage(dir).ok).toBe(true);
  }, 120000);
});
