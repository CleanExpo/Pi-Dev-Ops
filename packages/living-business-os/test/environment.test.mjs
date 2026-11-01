import { describe, expect, it } from 'vitest';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { ENV, PKG } from './helpers.mjs';

const run = (env) =>
  spawnSync(process.execPath, [path.join(PKG, 'scripts/conformance.mjs'), '--env-only'], { env, encoding: 'utf8' });

describe('conformance asserts its environment (G14)', () => {
  it('passes under the pinned environment', () => {
    const r = run(ENV);
    expect(r.status, r.stdout + r.stderr).toBe(0);
  });
  it('fails under a different time zone', () => {
    const r = run({ ...ENV, TZ: 'Australia/Sydney' });
    expect(r.status).not.toBe(0);
    expect(r.stdout + r.stderr).toMatch(/time zone/i);
  });
  it('fails under a different locale', () => {
    const r = run({ ...ENV, LC_ALL: 'de_DE.UTF-8', LANG: 'de_DE.UTF-8' });
    expect(r.status).not.toBe(0);
    expect(r.stdout + r.stderr).toMatch(/locale|LC_ALL/i);
  });
  it('runs on the pinned Node version', () => {
    expect(process.version).toBe('v22.22.3');
    expect(Intl.DateTimeFormat().resolvedOptions().timeZone).toBe('UTC');
  });
});
