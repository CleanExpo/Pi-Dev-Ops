import { describe, expect, it } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';
import { GOLDEN, PKG, listGolden, readJson } from './helpers.mjs';

const { source_token_counts: declared, rules } = readJson(path.join(GOLDEN, 'rules.json'));
const TOKENS = {
  min: /\.min\(/g, max: /\.max\(/g, int: /\.int\(/g, nonnegative: /\.nonnegative\(/g, finite: /\.finite\(/g,
  nullable: /\.nullable\(/g, optional: /\.optional\(/g, default: /\.default\(/g, literal: /z\.literal\(/g,
  enum: /z\.enum\(/g, datetime: /\.datetime\(/g, url: /\.url\(/g, strict: /\.strict\(/g, trim: /\.trim\(/g,
  addIssue: /ctx\.addIssue\(/g, refuseForeignEvidence: /refuseForeignEvidence\(/g, boolean: /z\.boolean\(/g,
};

describe('acceptance corpus (A3): every rule in contracts.ts has a fixture', () => {
  it('rules.json still describes the rules present in src/contracts.ts', () => {
    // A new refinement, bound, default, enum or literal changes a count here, which forces
    // rules.json (and therefore fixtures) to be updated in the same change.
    const src = fs.readFileSync(path.join(PKG, 'src/contracts.ts'), 'utf8');
    const actual = {};
    for (const [k, re] of Object.entries(TOKENS)) actual[k] = (src.match(re) ?? []).length;
    expect(actual).toEqual(declared);
  });

  it('every listed rule is covered by at least one fixture', () => {
    const covered = new Map();
    for (const g of listGolden()) for (const c of g.fixture.covers) covered.set(c, (covered.get(c) ?? 0) + 1);
    const missing = rules.filter((r) => !covered.has(r));
    expect(missing).toEqual([]);
  });

  it('has both a must-accept and a must-reject set, each non-trivial', () => {
    const kinds = listGolden().map((g) => g.fixture.kind);
    expect(kinds.filter((k) => k === 'accept').length).toBeGreaterThanOrEqual(30);
    expect(kinds.filter((k) => k === 'reject').length).toBeGreaterThanOrEqual(60);
  });

  it('numeric and string bounds have fixtures on both sides of the boundary', () => {
    const covers = (rule, kind) => listGolden().some((g) => g.fixture.kind === kind && g.fixture.covers.includes(rule));
    for (const rule of ['intent.goals.max10', 'signal.confidence.max', 'signal.risk.max', 'signal.confidence.min', 'signal.risk.min']) {
      expect(covers(rule, 'accept'), `${rule} accept`).toBe(true);
      expect(covers(rule, 'reject'), `${rule} reject`).toBe(true);
    }
  });
});
