import { describe, expect, it } from 'vitest';
import crypto from 'node:crypto';
import { digestOf } from '../lib/verify.mjs';

const sha = (s) => crypto.createHash('sha256').update(s).digest('hex');

describe('package_digest definition (A2)', () => {
  const a = { path: 'a.txt', mode: '100644', sha256: sha('a\n') };
  const x = { path: 'bin/x.mjs', mode: '100755', sha256: sha('x\n') };

  it('uses the fixed content hashes from the spec table', () => {
    expect(a.sha256).toBe('87428fc522803d31065e7bce3cf03fe475096631e5e07bbd7a0fde60c4cf25c7');
    expect(x.sha256).toBe('73cb3858a687a8494ca3323053016282f3dad39d42cf62ca4e79dda2aac7d9ac');
  });
  it('matches the fixed test vector', () => {
    expect(digestOf([a, x])).toBe('c397447d871ed9ab5a148175923159c41708a84d048ce8b524a15a1a1e57eacd');
  });
  it('does not depend on input order', () => {
    expect(digestOf([x, a])).toBe(digestOf([a, x]));
  });
  it('sorts by UTF-8 bytes, not by locale', () => {
    const upper = { path: 'B.txt', mode: '100644', sha256: sha('b') };
    const lower = { path: 'a.txt', mode: '100644', sha256: sha('a') };
    const e = { path: 'é.txt', mode: '100644', sha256: sha('e') };
    const expected = crypto
      .createHash('sha256')
      .update(
        [upper, lower, e]
          .map((p) => `${p.path}\0${p.mode}\0${p.sha256}\n`)
          .join(''),
      )
      .digest('hex');
    // bytes: "B" (0x42) < "a" (0x61) < "é" (0xc3...)
    expect(digestOf([e, lower, upper])).toBe(expected);
  });
  it('changes when the mode changes', () => {
    expect(digestOf([a, { ...x, mode: '100644' }])).not.toBe(digestOf([a, x]));
  });
  it('rejects duplicate paths', () => {
    expect(() => digestOf([a, a])).toThrow(/duplicate/i);
  });
});
