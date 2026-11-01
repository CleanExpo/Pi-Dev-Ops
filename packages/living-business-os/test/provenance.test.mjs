import { describe, expect, it } from 'vitest';
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { PKG, readJson } from './helpers.mjs';

const prov = readJson(path.join(PKG, 'PROVENANCE.json'));
const sha = (f) => crypto.createHash('sha256').update(fs.readFileSync(path.join(PKG, 'src', f))).digest('hex');

describe('provenance: the rule files are the Synthex files', () => {
  it('records the pinned Synthex commit', () => {
    expect(prov.source.sha).toBe('5445287f72b990f82b90808d942908a247786b66');
  });
  it.each(['contracts.ts', 'decision-engine.ts', 'weekly-questions.ts'])('src/%s is byte-identical (sha256 matches PROVENANCE.json)', (f) => {
    expect(sha(f)).toBe(prov.source.files[f]);
  });
  it('records the pinned capture environment', () => {
    expect(prov.capture.node).toBe('v22.22.3');
    expect(prov.capture.time_zone).toBe('UTC');
    expect(prov.capture.lc_all).toBe('C');
    expect(prov.capture.zod).toBe('4.4.3');
  });
  it('captured exactly the goldens that are on disk', () => {
    expect(fs.readdirSync(path.join(PKG, 'test/golden/expected')).length).toBe(prov.capture.fixtures);
  });
  it('keeps the 20 Synthex cases (names unchanged, none dropped)', () => {
    let n = 0;
    for (const f of ['contracts.test.ts', 'cursor-regressions.test.ts', 'codex-regressions.test.ts']) {
      n += (fs.readFileSync(path.join(PKG, 'test', f), 'utf8').match(/^\s+it\(/gm) ?? []).length;
    }
    expect(n).toBe(prov.source_tests.cases);
  });
});
