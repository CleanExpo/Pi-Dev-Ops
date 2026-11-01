// Capture goldens from the Synthex source (the only authority for behaviour).
//
//   node scripts/capture-golden.mjs --source <synthex-checkout> [--sha <sha>]
//
// Runs the three source files exactly as committed at <sha> (read with git show,
// never from the working tree) under tsx taken from the Synthex checkout. The
// environment is asserted and recorded in PROVENANCE.json. Output is the
// canonical serialisation of each outcome: {"ok"} | {"throws"} | {"zod_issues"}.
import { execFileSync, spawnSync } from 'node:child_process';
import crypto from 'node:crypto';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { canonical } from '../lib/canonical.mjs';

const PKG = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const DEFAULT_SHA = '5445287f72b990f82b90808d942908a247786b66';
const FILES = ['contracts.ts', 'decision-engine.ts', 'weekly-questions.ts'];
const sha256 = (buf) => crypto.createHash('sha256').update(buf).digest('hex');

function arg(name) {
  const i = process.argv.indexOf(name);
  return i === -1 ? undefined : process.argv[i + 1];
}

const source = arg('--source');
const sha = arg('--sha') ?? DEFAULT_SHA;
if (!source) {
  console.error('usage: capture-golden.mjs --source <synthex-checkout> [--sha <sha>]');
  process.exit(3);
}

// Environment assertions (spec 13.2).
const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
const collator = new Intl.Collator().resolvedOptions().locale;
if (process.version !== 'v22.22.3') throw new Error(`Node ${process.version}, expected v22.22.3`);
if (tz !== 'UTC') throw new Error(`time zone ${tz}, expected UTC`);
if (process.env.LC_ALL !== 'C' || process.env.LANG !== 'C') throw new Error('LC_ALL and LANG must be C');

const RUNNER = `
import fs from 'node:fs';
import {
  businessIntentSchema, opportunitySignalSchema, fulfilmentRequestSchema,
  customerInteractionSchema, fulfilmentIdempotencyKey,
} from './lib/contracts.ts';
import { rankImprovements } from './lib/decision-engine.ts';
import { selectWeeklyQuestions } from './lib/weekly-questions.ts';
const schemas: Record<string, { parse(v: unknown): unknown }> = {
  'business-intent': businessIntentSchema, 'opportunity-signal': opportunitySignalSchema,
  'fulfilment-request': fulfilmentRequestSchema, 'customer-interaction': customerInteractionSchema,
};
const inputs = JSON.parse(fs.readFileSync('inputs.json', 'utf8'));
function call(f: any): unknown {
  switch (f.command) {
    case 'validate': return schemas[f.contract].parse(f.input);
    case 'decide': return rankImprovements(f.input.intent, f.input.signals);
    case 'questions': return selectWeeklyQuestions(f.input.intent, f.input.signals, new Set(f.input.answeredQuestionIds ?? []));
    case 'idempotency-key': return { key: fulfilmentIdempotencyKey(f.input) };
    default: throw new Error('bad command ' + f.command);
  }
}
const outcomes = inputs.map((f: any) => {
  try { return { ok: call(f) }; } catch (e: any) {
    if (e && Array.isArray(e.issues)) return { zod_issues: e.issues.map((i: any) => ({ path: i.path, code: i.code })) };
    return { throws: String(e && e.message) };
  }
});
process.stdout.write(JSON.stringify({ outcomes }));
`;

const git = (...a) => execFileSync('git', ['-C', source, ...a], { maxBuffer: 1 << 26 });
const scratch = fs.mkdtempSync(path.join(os.tmpdir(), 'lbos-capture-'));
try {
  fs.mkdirSync(path.join(scratch, 'lib'));
  fs.writeFileSync(path.join(scratch, 'package.json'), '{"type":"module"}\n');
  const sourceHashes = {};
  for (const f of FILES) {
    const bytes = git('show', `${sha}:lib/living-business-os/${f}`);
    sourceHashes[f] = sha256(bytes);
    fs.writeFileSync(path.join(scratch, 'lib', f), bytes);
    if (!fs.readFileSync(path.join(PKG, 'src', f)).equals(bytes)) throw new Error(`src/${f} differs from Synthex ${sha}`);
  }
  const testBytes = git('show', `${sha}:tests/unit/living-business-os/contracts.test.ts`);
  fs.symlinkSync(path.join(source, 'node_modules'), path.join(scratch, 'node_modules'));

  const inputsDir = path.join(PKG, 'test/golden/inputs');
  const names = fs.readdirSync(inputsDir).filter((n) => n.endsWith('.json')).sort();
  const inputs = names.map((n) => JSON.parse(fs.readFileSync(path.join(inputsDir, n), 'utf8')));
  fs.writeFileSync(path.join(scratch, 'inputs.json'), JSON.stringify(inputs));
  fs.writeFileSync(path.join(scratch, 'runner.mts'), RUNNER);

  const tsx = path.join(source, 'node_modules/.bin/tsx');
  const run = spawnSync(tsx, ['runner.mts'], { cwd: scratch, encoding: 'utf8', maxBuffer: 1 << 26 });
  if (run.status !== 0) throw new Error(`runner failed: ${run.stderr}`);
  const { outcomes } = JSON.parse(run.stdout);

  const expectedDir = path.join(PKG, 'test/golden/expected');
  fs.rmSync(expectedDir, { recursive: true, force: true });
  fs.mkdirSync(expectedDir, { recursive: true });
  for (const [i, n] of names.entries()) fs.writeFileSync(path.join(expectedDir, n), canonical(outcomes[i]));

  const pkgOf = (name) => JSON.parse(fs.readFileSync(path.join(source, 'node_modules', name, 'package.json'), 'utf8')).version;
  const provenance = {
    source: { repo: 'CleanExpo/Synthex', sha, path: 'lib/living-business-os/', files: sourceHashes },
    source_tests: { path: 'tests/unit/living-business-os/contracts.test.ts', sha256: sha256(testBytes), cases: 20 },
    capture: {
      node: process.version, time_zone: tz, collator_locale: collator, lc_all: process.env.LC_ALL,
      lang: process.env.LANG, tsx: pkgOf('tsx'), zod: pkgOf('zod'), fixtures: names.length,
    },
  };
  fs.writeFileSync(path.join(PKG, 'PROVENANCE.json'), canonical(provenance));
  console.log(`captured ${names.length} goldens from ${sha}`);
} finally {
  fs.rmSync(scratch, { recursive: true, force: true });
}
