#!/usr/bin/env node
// lbos: the Living Business OS runner. It verifies the installed package before it
// imports any package code, then runs one pure function and prints one JSON envelope.
// It holds no business logic: the rules live in dist/ (built from src/).
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { verifyPackage } from '../lib/verify.mjs';
import { EXIT, LIMITS, buildEnvelope, errorBody, mapError, redactIssues, ERROR_EXIT } from '../lib/envelope.mjs';
import { readInputText, readableFile } from '../lib/input.mjs';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const COMMANDS = ['version', 'validate', 'decide', 'questions', 'idempotency-key'];
const CONTRACTS = {
  'business-intent': 'businessIntentSchema',
  'opportunity-signal': 'opportunitySignalSchema',
  'fulfilment-request': 'fulfilmentRequestSchema',
  'customer-interaction': 'customerInteractionSchema',
};

function emit(envelope, exit, { internal = false } = {}) {
  if (internal) process.stderr.write('lbos: internal error\n');
  process.stdout.write(JSON.stringify(envelope, null, 2) + '\n', () => process.exit(exit));
}

function parseArgs(argv) {
  const positionals = [];
  let input;
  let usage = false;
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--input') {
      if (i + 1 >= argv.length || input !== undefined) usage = true;
      else input = argv[++i];
    } else if (a.startsWith('--')) usage = true;
    else positionals.push(a);
  }
  const command = positionals.shift();
  if (!COMMANDS.includes(command)) usage = true;
  else if (command === 'validate') {
    if (positionals.length !== 1 || !(positionals[0] in CONTRACTS)) usage = true;
  } else if (positionals.length !== 0) usage = true;
  if (command === 'version' && input !== undefined) usage = true;
  return { command: COMMANDS.includes(command) ? command : null, positionals, input, usage };
}

function failure(code, issues = []) {
  return { error: errorBody(code, issues), exit: ERROR_EXIT[code] };
}

const isObject = (v) => v !== null && typeof v === 'object' && !Array.isArray(v);

/** Shape of the decide/questions wrapper. Returns issues (empty when fine). */
function wrapperIssues(command, obj) {
  const allowed = command === 'questions' ? ['intent', 'signals', 'answeredQuestionIds'] : ['intent', 'signals'];
  const issues = [];
  const unknown = Object.keys(obj).filter((k) => !allowed.includes(k));
  if (unknown.length) issues.push({ path: [], code: 'unrecognized_keys', count: unknown.length });
  if (!isObject(obj.intent)) issues.push({ path: ['intent'], code: 'invalid_type' });
  if (!Array.isArray(obj.signals)) issues.push({ path: ['signals'], code: 'invalid_type' });
  if (command === 'questions' && obj.answeredQuestionIds !== undefined) {
    const a = obj.answeredQuestionIds;
    if (!Array.isArray(a)) issues.push({ path: ['answeredQuestionIds'], code: 'invalid_type' });
    else {
      a.forEach((v, i) => typeof v !== 'string' && issues.push({ path: ['answeredQuestionIds', i], code: 'invalid_type' }));
      if (a.length > LIMITS.max_answered_question_ids) issues.push({ path: ['answeredQuestionIds'], code: 'too_big' });
      if (new Set(a).size !== a.length) issues.push({ path: ['answeredQuestionIds'], code: 'invalid_value' });
    }
  }
  return issues;
}

/** A ZodError from rankImprovements/selectWeeklyQuestions: attribute it to the intent or the first failing signal. */
function attribute(pkg, obj, err) {
  const intent = pkg.businessIntentSchema.safeParse(obj.intent);
  if (!intent.success) return intent.error.issues.map((i) => ({ ...i, path: ['intent', ...i.path] }));
  for (let i = 0; i < obj.signals.length; i++) {
    const s = pkg.opportunitySignalSchema.safeParse(obj.signals[i]);
    if (!s.success) return s.error.issues.map((x) => ({ ...x, path: ['signals', i, ...x.path] }));
  }
  return err.issues;
}

async function execute({ command, positionals, input }, pkg, manifest, schemaKeys) {
  if (command === 'version') {
    const prov = JSON.parse(fs.readFileSync(path.join(ROOT, 'PROVENANCE.json'), 'utf8'));
    return { ok: true, result: { origin_sha: prov.source.sha } };
  }
  if (input !== undefined && !readableFile(input)) return failure('USAGE');
  let text;
  try {
    text = await readInputText({ file: input, stdin: process.stdin });
  } catch (e) {
    return failure(e && e.limit ? 'INPUT_TOO_LARGE' : input !== undefined ? 'USAGE' : 'INTERNAL');
  }
  let obj;
  try {
    obj = JSON.parse(text);
  } catch {
    return failure('INVALID_INPUT');
  }
  if (!isObject(obj)) return failure('INVALID_INPUT', [{ path: [], code: 'invalid_type' }]);
  const zodFailure = (err, issues) =>
    failure('INVALID_INPUT', redactIssues(issues ?? err.issues, schemaKeys));
  try {
    if (command === 'validate') return { ok: true, result: pkg[CONTRACTS[positionals[0]]].parse(obj) };
    if (command === 'idempotency-key') return { ok: true, result: { key: pkg.fulfilmentIdempotencyKey(obj) } };
    const wi = wrapperIssues(command, obj);
    if (wi.length) return failure('INVALID_INPUT', wi);
    if (obj.signals.length > LIMITS.max_signals) return failure('INPUT_TOO_LARGE');
    if (command === 'decide') return { ok: true, result: pkg.rankImprovements(obj.intent, obj.signals) };
    return { ok: true, result: pkg.selectWeeklyQuestions(obj.intent, obj.signals, new Set(obj.answeredQuestionIds ?? [])) };
  } catch (e) {
    if (e && Array.isArray(e.issues)) {
      const issues = command === 'decide' || command === 'questions' ? attribute(pkg, obj, e) : e.issues;
      return zodFailure(e, issues);
    }
    const mapped = mapError(e);
    return { error: mapped.error, exit: mapped.exit };
  }
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const unverified = (code) => {
    emit(buildEnvelope({ command: args.command, identity: 'unverified', ok: false, error: errorBody(code) }), EXIT.INTEGRITY);
  };

  // Start-up steps 1 and 2: manifest and byte verification, before any import.
  const v = verifyPackage(ROOT);
  if (!v.ok) return unverified('INTEGRITY');
  // Step 3: only now import the package code.
  let pkg;
  try {
    pkg = await import('../dist/index.js');
  } catch {
    return unverified('DEPENDENCY_MISSING');
  }
  // Step 4.
  if (pkg.CONTRACT_VERSION !== v.manifest.contract_version) return unverified('INTEGRITY');

  const wrap = (ok, result, error) => buildEnvelope({ command: args.command, identity: 'verified', ok, result, error, manifest: v.manifest });
  if (args.usage) return emit(wrap(false, null, errorBody('USAGE')), EXIT.USAGE);

  const surface = JSON.parse(fs.readFileSync(path.join(ROOT, 'contract-surface.json'), 'utf8'));
  const out = await execute(args, pkg, v.manifest, surface.schema_keys);
  if (out.error) return emit(wrap(false, null, out.error), out.exit, { internal: out.exit === EXIT.INTERNAL });
  return emit(wrap(true, out.result, null), EXIT.SUCCESS);
}

main().catch(() => {
  process.stderr.write('lbos: internal error\n');
  process.stdout.write(
    JSON.stringify(
      buildEnvelope({ command: null, identity: 'unverified', ok: false, error: errorBody('INTERNAL') }),
      null,
      2,
    ) + '\n',
    () => process.exit(EXIT.INTERNAL),
  );
});
