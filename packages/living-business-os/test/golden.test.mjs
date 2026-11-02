import { describe, expect, it } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';
import {
  businessIntentSchema,
  opportunitySignalSchema,
  fulfilmentRequestSchema,
  customerInteractionSchema,
  fulfilmentIdempotencyKey,
  rankImprovements,
  selectWeeklyQuestions,
} from '../src/index.ts';
import { canonical } from '../lib/canonical.mjs';
import { GOLDEN, listGolden } from './helpers.mjs';

const schemas = {
  'business-intent': businessIntentSchema,
  'opportunity-signal': opportunitySignalSchema,
  'fulfilment-request': fulfilmentRequestSchema,
  'customer-interaction': customerInteractionSchema,
};

function call(f) {
  switch (f.command) {
    case 'validate':
      return schemas[f.contract].parse(f.input);
    case 'decide':
      return rankImprovements(f.input.intent, f.input.signals);
    case 'questions':
      return selectWeeklyQuestions(f.input.intent, f.input.signals, new Set(f.input.answeredQuestionIds ?? []));
    case 'idempotency-key':
      return { key: fulfilmentIdempotencyKey(f.input) };
    default:
      throw new Error(`bad command ${f.command}`);
  }
}

export function outcomeOf(f) {
  try {
    return { ok: call(f) };
  } catch (e) {
    if (e && Array.isArray(e.issues)) return { zod_issues: e.issues.map((i) => ({ path: i.path, code: i.code })) };
    return { throws: String(e && e.message) };
  }
}

const all = listGolden();

describe('golden: package code reproduces the Synthex 5445287f7 outcomes byte for byte', () => {
  it('has one expected file per input and no strays', () => {
    const inputs = fs.readdirSync(path.join(GOLDEN, 'inputs')).sort();
    const expected = fs.readdirSync(path.join(GOLDEN, 'expected')).sort();
    expect(expected).toEqual(inputs);
    expect(all.length).toBeGreaterThanOrEqual(150);
  });

  it.each(all.map((g) => [g.file, g]))('%s', (_name, g) => {
    expect(canonical(outcomeOf(g.fixture))).toBe(g.expectedText);
  });

  it('every fixture behaves as its declared kind says', () => {
    const problems = [];
    for (const g of all) {
      const e = JSON.parse(g.expectedText);
      const f = g.fixture;
      if (f.kind === 'accept' && !('ok' in e)) problems.push(`${g.file}: accept but ${JSON.stringify(e)}`);
      if (f.kind === 'reject') {
        const hit = e.zod_issues?.some((i) => JSON.stringify(i.path) === JSON.stringify(f.reject_path));
        if (!hit) problems.push(`${g.file}: reject for the wrong reason ${JSON.stringify(e)}`);
      }
    }
    expect(problems).toEqual([]);
  });

  it('matches the worked example in the spec (10.8)', () => {
    const byName = Object.fromEntries(all.map((g) => [g.file, JSON.parse(g.expectedText)]));
    const decide = byName['decide-worked-example.json'].ok;
    expect(decide).toHaveLength(1);
    expect(decide[0]).toMatchObject({
      decision: 'draft_for_review',
      priorityIndex: 3.77,
      reasons: [],
      evidenceRefs: ['ev-1'],
      approvalStatus: 'required',
    });
    const q = byName['questions-worked-example.json'].ok;
    expect(q[0]).toMatchObject({ id: 'service_priorities', priority: 80 });
    expect(byName['key-accept-spaces-slash.json'].ok.key).toBe('unite_group:org-demo-1:ord%207%2Fa');
    expect(byName['decide-tenant-mismatch.json']).toEqual({ throws: 'TENANT_MISMATCH' });
  });

  it('questions keeps the source behaviour: no id de-duplication (T1)', () => {
    const e = JSON.parse(all.find((g) => g.file === 'questions-duplicate-signal-ids-no-dedupe.json').expectedText);
    const ids = e.ok.map((q) => q.id);
    expect(ids.filter((i) => i === 'verify_signal:sig-1').length).toBe(3);
  });

  it('decide de-duplicates identical ids and refuses conflicting ones (T1)', () => {
    const byName = Object.fromEntries(all.map((g) => [g.file, JSON.parse(g.expectedText)]));
    expect(byName['decide-dedupe-identical.json'].ok).toHaveLength(1);
    expect(byName['decide-conflicting-signal-id.json']).toEqual({ throws: 'CONFLICTING_SIGNAL_ID' });
  });
});
