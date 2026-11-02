import { describe, expect, it } from 'vitest';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import {
  businessIntentSchema,
  opportunitySignalSchema,
  fulfilmentRequestSchema,
  customerInteractionSchema,
} from '../src/index.ts';
import { ERROR_EXIT, EXIT, LIMITS } from '../lib/envelope.mjs';
import { ENV, PKG, listGolden, readJson } from './helpers.mjs';

const surface = readJson(path.join(PKG, 'contract-surface.json'));

function keysOf(schema, acc = new Set()) {
  const def = schema?._zod?.def ?? schema?.def;
  if (!def) return acc;
  if (def.shape) {
    for (const [k, v] of Object.entries(def.shape)) {
      acc.add(k);
      keysOf(v, acc);
    }
  }
  for (const inner of [def.innerType, def.element, def.in, def.out, def.left, def.right]) if (inner) keysOf(inner, acc);
  return acc;
}

describe('contract-surface.json', () => {
  it('schema_keys lists every key the schemas declare (plus the CLI input keys)', () => {
    const declared = new Set();
    for (const s of [businessIntentSchema, opportunitySignalSchema, fulfilmentRequestSchema, customerInteractionSchema]) keysOf(s, declared);
    expect(declared.size).toBeGreaterThan(40);
    const missing = [...declared].filter((k) => !surface.schema_keys.includes(k));
    expect(missing).toEqual([]);
    for (const k of ['intent', 'signals', 'answeredQuestionIds']) expect(surface.schema_keys).toContain(k);
  });
  it('commands and contracts match the runner', () => {
    expect(surface.commands).toEqual(['version', 'validate', 'decide', 'questions', 'idempotency-key']);
    expect(surface.contracts).toEqual(['business-intent', 'opportunity-signal', 'fulfilment-request', 'customer-interaction']);
  });
  it('error codes and exit codes match the code that emits them', () => {
    expect(surface.error_codes).toEqual(ERROR_EXIT);
    expect(surface.exit_codes).toEqual(Object.values(EXIT).sort((a, b) => a - b));
    expect(surface.limits).toEqual(LIMITS);
  });
  it('every question id the goldens produce is listed (verify_signal ids match the pattern)', () => {
    const ids = new Set();
    for (const g of listGolden()) {
      const e = JSON.parse(g.expectedText);
      if (g.fixture.command === 'questions' && e.ok) for (const q of e.ok) ids.add(q.id);
    }
    for (const id of ids) {
      const listed = surface.question_ids.some((p) => (p.endsWith('*') ? id.startsWith(p.slice(0, -1)) : p === id));
      expect(listed, id).toBe(true);
    }
    expect(ids.size).toBeGreaterThanOrEqual(4);
  });
  it('envelope keys are exactly those the runner prints', () => {
    const r = spawnSync(process.execPath, [path.join(PKG, 'bin/lbos.mjs'), 'version'], { env: ENV, encoding: 'utf8' });
    expect(Object.keys(JSON.parse(r.stdout))).toEqual(surface.envelope_keys);
  });
});
