import { afterAll, describe, expect, it } from 'vitest';
import { canonical } from '../lib/canonical.mjs';
import { PKG, cleanupTemp, cliArgsFor, listGolden, runCliAsync } from './helpers.mjs';

afterAll(cleanupTemp);

const ALLOWED = new Set(['invalid_type', 'too_small', 'too_big', 'invalid_format', 'invalid_value', 'unrecognized_keys', 'PROVENANCE_MISMATCH', 'PRIVATE_EVIDENCE_NEEDS_ORG', 'FOREIGN_EVIDENCE', 'RULE_FAILED']);

async function pool(items, n, fn) {
  const out = new Array(items.length);
  let next = 0;
  await Promise.all(
    Array.from({ length: n }, async () => {
      while (next < items.length) {
        const i = next++;
        out[i] = await fn(items[i]);
      }
    }),
  );
  return out;
}

describe('CLI over every golden: envelope .result equals the golden outcome (T4)', () => {
  it('maps every fixture to the stated result, exit code and redacted issues', async () => {
    const all = listGolden();
    const results = await pool(all, 8, (g) => runCliAsync(PKG, cliArgsFor(g.fixture), JSON.stringify(g.fixture.input)));
    const problems = [];
    const seenCodes = new Set();
    all.forEach((g, i) => {
      const r = results[i];
      const e = JSON.parse(g.expectedText);
      const tag = g.file;
      if (!r.json) return problems.push(`${tag}: no JSON envelope (${r.stdout} ${r.stderr})`);
      if (r.stderr !== '') problems.push(`${tag}: stderr not empty`);
      if ('ok' in e) {
        if (r.status !== 0) problems.push(`${tag}: exit ${r.status}`);
        else if (canonical(r.json.result) !== canonical(e.ok)) problems.push(`${tag}: result differs`);
      } else if ('throws' in e) {
        if (r.status !== 6 || r.json.error?.code !== e.throws) problems.push(`${tag}: expected exit 6 ${e.throws}, got ${r.status} ${r.json.error?.code}`);
      } else {
        if (r.status !== 2) return problems.push(`${tag}: expected exit 2, got ${r.status}`);
        const issues = r.json.error.issues;
        if (issues.length !== e.zod_issues.length) return problems.push(`${tag}: issue count ${issues.length} vs ${e.zod_issues.length}`);
        const cmd = g.fixture.command;
        issues.forEach((iss, k) => {
          seenCodes.add(e.zod_issues[k].code);
          if (!ALLOWED.has(iss.code)) problems.push(`${tag}: code ${iss.code} not allowlisted`);
          const gp = e.zod_issues[k].path;
          const prefix = cmd === 'decide' || cmd === 'questions' ? (iss.path[0] === 'intent' ? 1 : 2) : 0;
          if (JSON.stringify(iss.path.slice(prefix)) !== JSON.stringify(gp)) problems.push(`${tag}: path ${JSON.stringify(iss.path)} vs ${JSON.stringify(gp)}`);
          if (e.zod_issues[k].code === 'unrecognized_keys' && typeof iss.count !== 'number') problems.push(`${tag}: no count`);
        });
      }
    });
    expect(problems).toEqual([]);
    // Guard: the redaction allowlist is meant to cover every zod code the goldens produce.
    for (const c of seenCodes) expect([...ALLOWED, 'custom'], `golden zod code ${c}`).toContain(c);
  }, 120000);
});
