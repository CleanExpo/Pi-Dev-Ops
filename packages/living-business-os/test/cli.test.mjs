import { afterAll, describe, expect, it } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';
import { PKG, cleanupTemp, readJson, runCli, runCliAsync, tempDir } from './helpers.mjs';

afterAll(cleanupTemp);

const inp = (name) => readJson(path.join(PKG, 'test/golden/inputs', `${name}.json`)).input;
const decideInput = () => inp('decide-worked-example');
const run = (args, stdin = '') => runCli(PKG, args, { stdin });
const KEYS = ['ok', 'command', 'identity', 'contract_version', 'package_version', 'package_digest', 'draft_only', 'approval_required', 'result', 'error'];

describe('envelope and version', () => {
  it('version exits 0, prints exactly one pretty JSON object, identity verified', () => {
    const r = run(['version']);
    expect(r.status).toBe(0);
    expect(r.stderr).toBe('');
    expect(r.stdout).toContain('"identity": "verified"');
    expect(r.stdout.endsWith('}\n')).toBe(true);
    expect(Object.keys(r.json)).toEqual(KEYS);
    expect(r.json).toMatchObject({
      ok: true, command: 'version', identity: 'verified', contract_version: 'lbos.contracts.v1',
      package_version: '1.0.0', draft_only: true, approval_required: true, error: null,
      result: { origin_sha: '5445287f72b990f82b90808d942908a247786b66' },
    });
    expect(r.json.package_digest).toMatch(/^[0-9a-f]{64}$/);
  });

  it('version ignores stdin', () => {
    expect(run(['version'], 'garbage {{{').status).toBe(0);
  });

  it('package_digest in the envelope equals the manifest digest', () => {
    expect(run(['version']).json.package_digest).toBe(readJson(path.join(PKG, 'MANIFEST.json')).package_digest);
  });
});

describe('commands on the worked example', () => {
  it('decide returns a draft-only proposal', () => {
    const r = run(['decide'], JSON.stringify(decideInput()));
    expect(r.status).toBe(0);
    expect(r.json.result).toHaveLength(1);
    expect(r.json.result[0]).toMatchObject({ decision: 'draft_for_review', priorityIndex: 3.77, approvalStatus: 'required' });
    expect(r.json.draft_only).toBe(true);
  });
  it('questions accepts the worked example with an empty answeredQuestionIds array', () => {
    const r = run(['questions'], JSON.stringify({ ...decideInput(), answeredQuestionIds: [] }));
    expect(r.status).toBe(0);
    expect(r.json.result[0]).toMatchObject({ id: 'service_priorities', priority: 80 });
  });
  it('idempotency-key', () => {
    const r = run(['idempotency-key'], JSON.stringify(inp('key-accept-spaces-slash')));
    expect(r.status).toBe(0);
    expect(r.json.result).toEqual({ key: 'unite_group:org-demo-1:ord%207%2Fa' });
  });
  it('validate returns the parsed value with defaults applied and strings trimmed', () => {
    const input = inp('intent-accept-trimmed');
    const r = run(['validate', 'business-intent'], JSON.stringify(input));
    expect(r.status).toBe(0);
    expect(r.json.result.businessName).toBe('Demo Cafe');
    expect(r.json.result.constraints.preferredServices).toEqual([]);
  });
  it('tenant mismatch is exit 6 with the fixed message and no issues', () => {
    const r = run(['decide'], JSON.stringify(inp('decide-tenant-mismatch')));
    expect(r.status).toBe(6);
    expect(r.json.ok).toBe(false);
    expect(r.json.result).toBeNull();
    expect(r.json.error).toEqual({ code: 'TENANT_MISMATCH', message: 'Signal belongs to another organisation', issues: [] });
  });
  it.each([
    ['decide-unknown-service', 'decide', 'UNKNOWN_SERVICE'],
    ['decide-conflicting-signal-id', 'decide', 'CONFLICTING_SIGNAL_ID'],
    ['questions-tenant-mismatch', 'questions', 'TENANT_MISMATCH'],
    ['questions-unknown-service', 'questions', 'UNKNOWN_SERVICE'],
  ])('%s is exit 6 %s', (name, cmd, code) => {
    const r = run([cmd], JSON.stringify(inp(name)));
    expect(r.status).toBe(6);
    expect(r.json.error.code).toBe(code);
  });
  it('evidence from another tenant (a ZodError) is exit 2 with FOREIGN_EVIDENCE', () => {
    const r = run(['decide'], JSON.stringify(inp('decide-foreign-evidence')));
    expect(r.status).toBe(2);
    expect(r.json.error.code).toBe('INVALID_INPUT');
    expect(r.json.error.issues).toEqual([{ path: ['signals', 0, 'evidence', 0, 'organizationId'], code: 'FOREIGN_EVIDENCE' }]);
  });
  it('a schema failure in a later signal wins over a domain error in an earlier one, as in the source', () => {
    const r = run(['questions'], JSON.stringify(inp('questions-invalid-signal-beats-tenant')));
    expect(r.status).toBe(2);
    expect(r.json.error.issues[0].path).toEqual(['signals', 1, 'risk']);
  });
});

describe('usage errors (exit 3)', () => {
  it.each([
    [['bogus']],
    [[]],
    [['validate']],
    [['validate', 'no-such-contract']],
    [['version', 'extra']],
    [['decide', '--input']],
    [['decide', '--wat']],
    [['validate', 'business-intent', 'extra']],
  ])('%j', (args) => {
    const r = run(args, '{}');
    expect(r.status).toBe(3);
    expect(r.json.error.code).toBe('USAGE');
    expect(r.json.error.issues).toEqual([]);
  });
  it('--input reads a file', () => {
    const f = path.join(tempDir(), 'in.json');
    fs.writeFileSync(f, JSON.stringify(decideInput()));
    const r = run(['decide', '--input', f]);
    expect(r.status).toBe(0);
  });
  it('--input missing file is USAGE', () => {
    const r = run(['decide', '--input', '/nonexistent/in.json']);
    expect(r.status).toBe(3);
    expect(r.json.error.code).toBe('USAGE');
  });
});

describe('malformed, empty and wrongly shaped input (exit 2)', () => {
  it('empty stdin', () => {
    const r = run(['decide'], '');
    expect(r.status).toBe(2);
    expect(r.json.error.code).toBe('INVALID_INPUT');
  });
  it('empty object gives an issues list', () => {
    const r = run(['decide'], '{}');
    expect(r.status).toBe(2);
    expect(r.json.error.issues.length).toBeGreaterThan(0);
  });
  it('malformed JSON', () => {
    const r = run(['decide'], '{"intent": ');
    expect(r.status).toBe(2);
    expect(r.json.error.issues).toEqual([]);
  });
  it('NaN as text is malformed JSON', () => {
    const r = run(['validate', 'opportunity-signal'], '{"confidence": NaN}');
    expect(r.status).toBe(2);
  });
  it.each([['[]'], ['"text"'], ['42'], ['null'], ['true']])('wrong top-level type %s', (text) => {
    for (const args of [['decide'], ['questions'], ['validate', 'business-intent'], ['idempotency-key']]) {
      const r = run(args, text);
      expect(r.status, `${args} ${text}`).toBe(2);
      expect(r.json.error.code).toBe('INVALID_INPUT');
    }
  });
  it('unknown top-level key in decide input', () => {
    const r = run(['decide'], JSON.stringify({ ...decideInput(), extra: 1 }));
    expect(r.status).toBe(2);
    expect(r.json.error.issues).toContainEqual({ code: 'unrecognized_keys', count: 1, path: [] });
  });
  it('signals must be an array', () => {
    const r = run(['decide'], JSON.stringify({ ...decideInput(), signals: {} }));
    expect(r.status).toBe(2);
    expect(r.json.error.issues[0]).toMatchObject({ path: ['signals'], code: 'invalid_type' });
  });
  it('questions with answeredQuestionIds omitted is INVALID_INPUT (the field is required, only the array may be empty)', () => {
    const r = run(['questions'], JSON.stringify(decideInput()));
    expect(r.status).toBe(2);
    expect(r.json.error.code).toBe('INVALID_INPUT');
    expect(r.json.error.issues).toEqual([{ path: ['answeredQuestionIds'], code: 'invalid_type' }]);
  });
  it.each([['a string', 'service_priorities'], ['null', null], ['an object', {}], ['a number', 3]])('questions with answeredQuestionIds as %s is INVALID_INPUT', (_n, v) => {
    const r = run(['questions'], JSON.stringify({ ...decideInput(), answeredQuestionIds: v }));
    expect(r.status).toBe(2);
    expect(r.json.error.issues).toEqual([{ path: ['answeredQuestionIds'], code: 'invalid_type' }]);
  });
  it('decide does not accept answeredQuestionIds', () => {
    const r = run(['decide'], JSON.stringify({ ...decideInput(), answeredQuestionIds: [] }));
    expect(r.status).toBe(2);
  });
  it('duplicate answered question ids are refused', () => {
    const r = run(['questions'], JSON.stringify({ ...decideInput(), answeredQuestionIds: ['a', 'a'] }));
    expect(r.status).toBe(2);
    expect(r.json.error.issues[0]).toMatchObject({ path: ['answeredQuestionIds'], code: 'invalid_value' });
  });
  it('more than 100 answered question ids are refused', () => {
    const ids = Array.from({ length: 101 }, (_, i) => `q${i}`);
    const r = run(['questions'], JSON.stringify({ ...decideInput(), answeredQuestionIds: ids }));
    expect(r.status).toBe(2);
    expect(r.json.error.issues[0]).toMatchObject({ path: ['answeredQuestionIds'], code: 'too_big' });
  });
  it('answered question ids are used', () => {
    const r = run(['questions'], JSON.stringify({ ...decideInput(), answeredQuestionIds: ['service_priorities'] }));
    expect(r.status).toBe(0);
    expect(r.json.result).toEqual([]);
  });
  it('non-string answered ids are refused', () => {
    const r = run(['questions'], JSON.stringify({ ...decideInput(), answeredQuestionIds: [1] }));
    expect(r.status).toBe(2);
  });
  it('questions input may not carry unknown keys', () => {
    const r = run(['questions'], JSON.stringify({ ...decideInput(), answeredQuestionIds: [], nope: 1 }));
    expect(r.status).toBe(2);
  });
});

describe('large input and timing (exit 5)', () => {
  it('262,145 bytes is refused before parsing', () => {
    const r = run(['decide'], 'x'.repeat(262145));
    expect(r.status).toBe(5);
    expect(r.json.error.code).toBe('INPUT_TOO_LARGE');
  });
  it('exactly 262,144 bytes is read (and then fails as invalid JSON, not as too large)', () => {
    const r = run(['decide'], ' '.repeat(262144));
    expect(r.status).toBe(2);
  });
  it('size is counted while reading: a huge stream is cut off', () => {
    const r = run(['decide'], 'x'.repeat(5 * 1024 * 1024));
    expect(r.status).toBe(5);
  });
  it('501 signals is refused after parsing', () => {
    const base = decideInput();
    const signals = Array.from({ length: 501 }, (_, i) => ({ ...base.signals[0], id: `s${i}` }));
    const r = run(['decide'], JSON.stringify({ intent: base.intent, signals }));
    expect(r.status).toBe(5);
    expect(r.json.error.code).toBe('INPUT_TOO_LARGE');
  });
  it('500 valid signals finish in under 2 seconds', () => {
    const base = decideInput();
    const signals = Array.from({ length: 500 }, (_, i) => ({ ...base.signals[0], id: `s${i}` }));
    const text = JSON.stringify({ intent: base.intent, signals });
    expect(text.length).toBeLessThan(262144);
    const t0 = Date.now();
    const r = run(['decide'], text);
    expect(r.status).toBe(0);
    expect(r.json.result).toHaveLength(500);
    expect(Date.now() - t0).toBeLessThan(2000);
  });
  it('a stream that never ends is exit 5 at about 5 seconds', async () => {
    const { spawn } = await import('node:child_process');
    const t0 = Date.now();
    const child = spawn(process.execPath, [path.join(PKG, 'bin/lbos.mjs'), 'decide'], { env: { ...process.env, LC_ALL: 'C', TZ: 'UTC' } });
    let out = '';
    child.stdout.on('data', (d) => (out += d));
    child.stdin.write('{"intent":');
    const status = await new Promise((res) => child.on('close', res));
    const took = Date.now() - t0;
    expect(status).toBe(5);
    expect(JSON.parse(out).error.code).toBe('INPUT_TOO_LARGE');
    expect(took).toBeGreaterThanOrEqual(4900);
    expect(took).toBeLessThan(9000);
  }, 20000);
});

describe('duplicate operation and idempotency (14.6)', () => {
  it('repeated runs give byte-identical stdout', () => {
    const text = JSON.stringify(decideInput());
    const a = run(['decide'], text).stdout;
    const b = run(['decide'], text).stdout;
    expect(a).toBe(b);
    const k = JSON.stringify(inp('key-accept-spaces-slash'));
    expect(run(['idempotency-key'], k).stdout).toBe(run(['idempotency-key'], k).stdout);
  });
  it('decide de-duplicates identical signal ids', () => {
    const r = run(['decide'], JSON.stringify(inp('decide-dedupe-identical')));
    expect(r.json.result).toHaveLength(1);
  });
  it('questions does not de-duplicate (source behaviour)', () => {
    const r = run(['questions'], JSON.stringify(inp('questions-duplicate-signal-ids-no-dedupe')));
    expect(r.status).toBe(0);
    expect(r.json.result.filter((q) => q.id === 'verify_signal:sig-1').length).toBe(3);
  });
});

describe('concurrency of independent runs', () => {
  it('parallel runs do not interfere', async () => {
    const text = JSON.stringify(decideInput());
    const results = await Promise.all(Array.from({ length: 6 }, () => runCliAsync(PKG, ['decide'], text)));
    expect(new Set(results.map((r) => r.stdout)).size).toBe(1);
    expect(results.every((r) => r.status === 0)).toBe(true);
  });
});
