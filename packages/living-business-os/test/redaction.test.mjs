import { afterAll, describe, expect, it } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';
import { MARKER, PKG, cleanupTemp, readJson, runCli } from './helpers.mjs';
import { mapError, redactIssues } from '../lib/envelope.mjs';

afterAll(cleanupTemp);

const inp = (name) => readJson(path.join(PKG, 'test/golden/inputs', `${name}.json`)).input;
const surface = readJson(path.join(PKG, 'contract-surface.json'));
const run = (args, stdin) => runCli(PKG, args, { stdin });
const clean = (r) => {
  expect(r.stdout).not.toContain(MARKER);
  expect(r.stderr).not.toContain(MARKER);
};

describe('redaction: planted marker never appears in a failure envelope (14.4)', () => {
  it('(i) unknown top-level key in validate: count only', () => {
    const input = { ...inp('intent-accept-minimal'), [MARKER]: 1 };
    const r = run(['validate', 'business-intent'], JSON.stringify(input));
    expect(r.status).toBe(2);
    expect(r.json.error.issues).toEqual([{ path: [], code: 'unrecognized_keys', count: 1 }]);
    clean(r);
  });
  it('(ii) unknown key inside evidence of a decide signal', () => {
    const input = inp('decide-worked-example');
    input.signals[0].evidence[0][MARKER] = 1;
    const r = run(['decide'], JSON.stringify(input));
    expect(r.status).toBe(2);
    expect(r.json.error.issues).toEqual([{ path: ['signals', 0, 'evidence', 0], code: 'unrecognized_keys', count: 1 }]);
    clean(r);
  });
  it('(iii) wrong type in confidence', () => {
    const input = { ...inp('signal-accept-minimal'), confidence: MARKER };
    const r = run(['validate', 'opportunity-signal'], JSON.stringify(input));
    expect(r.status).toBe(2);
    expect(r.json.error.issues).toEqual([{ path: ['confidence'], code: 'invalid_type' }]);
    clean(r);
  });
  it('(iv) malformed JSON containing the marker', () => {
    const r = run(['decide'], `{"intent": ${MARKER}`);
    expect(r.status).toBe(2);
    expect(r.json.error.code).toBe('INVALID_INPUT');
    expect(r.json.error.issues).toEqual([]);
    clean(r);
  });
  it('(v) --input path containing the marker', () => {
    const r = run(['decide', '--input', `/nonexistent/${MARKER}.json`], '');
    expect(r.status).toBe(3);
    expect(r.json.error.code).toBe('USAGE');
    clean(r);
  });
  it('(vi) internal-error mapper returns fixed text', () => {
    const mapped = mapError(new Error(`boom ${MARKER}`));
    expect(mapped.exit).toBe(70);
    expect(mapped.error).toEqual({ code: 'INTERNAL', message: expect.any(String), issues: [] });
    expect(JSON.stringify(mapped)).not.toContain(MARKER);
    expect(JSON.stringify(mapError(Object.assign(new Error(MARKER), { stack: MARKER })))).not.toContain(MARKER);
  });
  it('a marker used as a tenant id in a custom rule stays out', () => {
    const input = inp('signal-accept-minimal');
    input.evidence[0].organizationId = MARKER;
    const r = run(['validate', 'opportunity-signal'], JSON.stringify(input));
    expect(r.status).toBe(2);
    expect(r.json.error.issues[0].code).toBe('FOREIGN_EVIDENCE');
    clean(r);
  });
  it('a marker used as a path segment becomes "?"', () => {
    const issues = redactIssues([{ code: 'invalid_type', path: ['signals', 0, MARKER, 'id'] }], surface.schema_keys);
    expect(issues).toEqual([{ path: ['signals', 0, '?', 'id'], code: 'invalid_type' }]);
  });
});

describe('redactIssues allowlist', () => {
  const keys = surface.schema_keys;
  it('passes the five zod codes through', () => {
    for (const code of ['invalid_type', 'too_small', 'too_big', 'invalid_format', 'invalid_value']) {
      expect(redactIssues([{ code, path: ['goals'], message: MARKER }], keys)).toEqual([{ path: ['goals'], code }]);
    }
  });
  it('maps the three custom rules by message prefix', () => {
    const c = (message) => redactIssues([{ code: 'custom', path: ['x'], message }], keys)[0].code;
    expect(c('Evidence kind research cannot carry data class owned (provenance mismatch)')).toBe('PROVENANCE_MISMATCH');
    expect(c('Private evidence (owned or client_approved) must name its organisation')).toBe('PRIVATE_EVIDENCE_NEEDS_ORG');
    expect(c('Evidence belongs to another tenant; cross-tenant references are refused')).toBe('FOREIGN_EVIDENCE');
  });
  it('maps every other code, including the other custom rules, to RULE_FAILED', () => {
    expect(redactIssues([{ code: 'custom', path: [], message: 'Direct marketing requires ...' }], keys)[0].code).toBe('RULE_FAILED');
    expect(redactIssues([{ code: 'invalid_union', path: [] }], keys)[0].code).toBe('RULE_FAILED');
    expect(redactIssues([{ code: 'not_multiple_of', path: [] }], keys)[0].code).toBe('RULE_FAILED');
  });
  it('reports unrecognized_keys as a count and never lists key names', () => {
    expect(redactIssues([{ code: 'unrecognized_keys', keys: ['a', MARKER], path: [] }], keys)).toEqual([{ path: [], code: 'unrecognized_keys', count: 2 }]);
  });
});

describe('success echo of synthetic input is documented, not hidden', () => {
  it('validate returns the parsed value on success', () => {
    const input = { ...inp('intent-accept-minimal'), businessName: MARKER };
    const r = run(['validate', 'business-intent'], JSON.stringify(input));
    expect(r.status).toBe(0);
    expect(r.json.result.businessName).toBe(MARKER);
  });
  it('the skill file says so', () => {
    const skill = fs.readFileSync(path.join(PKG, '../../skills/living-business-os/SKILL.md'), 'utf8');
    expect(skill).toMatch(/synthetic/i);
    expect(skill).toMatch(/echo|returns? (the )?(parsed|input)/i);
  });
});
