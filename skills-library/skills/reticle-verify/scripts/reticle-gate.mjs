#!/usr/bin/env node
// Reticle Done gate: exit 0 only when Reticle PROVES the saved flows covering this change still hold.
//
//   node reticle-gate.mjs --repo <dir> --app-url http://localhost:3917 [--base origin/main]
//                         [--evidence <file.json>] [--self-test]
//
// Exit codes: 0 = verified yes · 1 = a flow failed, drifted, or the verdict was not "yes"
//             2 = could not check (daemon/app down, no saved flows, bad args). Never a pass.
// --self-test plants a copy of one flow whose text check cannot be true, replays it, and
// requires it to FAIL before trusting any green (proves the gate can fail). The copy is removed.
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import { reticleCalls, parseJson } from './reticle-mcp.mjs';

const args = Object.fromEntries(
  process.argv.slice(2).reduce((acc, a, i, all) => {
    if (a.startsWith('--')) acc.push([a.slice(2), all[i + 1] && !all[i + 1].startsWith('--') ? all[i + 1] : true]);
    return acc;
  }, []),
);
const repo = path.resolve(args.repo || process.cwd());
const appUrl = args['app-url'];
const base = args.base || 'origin/main';
const report = { gate: 'reticle-verify', repo, appUrl, base, at: new Date().toISOString() };

function finish(code, verdict, reason) {
  Object.assign(report, { exit: code, verdict, reason });
  if (args.evidence && args.evidence !== true) fs.writeFileSync(args.evidence, JSON.stringify(report, null, 2) + '\n');
  console.log(JSON.stringify(report, null, 2));
  process.exit(code);
}
const git = (...a) => execFileSync('git', ['-C', repo, ...a], { encoding: 'utf8' }).trim();
const reachable = (url) => new Promise((ok) => {
  const req = http.get(url, { timeout: 60000 }, (res) => { res.resume(); ok(res.statusCode < 500); });
  req.on('error', () => ok(false));
  req.on('timeout', () => { req.destroy(); ok(false); });
});

if (!appUrl) finish(2, 'UNPROVEN', '--app-url is required (the running dev server the daemon drives)');

// 1. Identity: which revision this evidence binds to.
try {
  report.head = git('rev-parse', 'HEAD');
  report.dirty = git('status', '--porcelain').split('\n').filter(Boolean).length;
  report.changedFiles = git('diff', '--name-only', `${base}...HEAD`).split('\n').filter(Boolean);
} catch (e) {
  finish(2, 'UNPROVEN', `git failed in ${repo}: ${e.message.split('\n')[0]}`);
}

// 2. Saved flows: no flows means nothing can be proved, which is not a pass.
let projectId;
try {
  projectId = JSON.parse(fs.readFileSync(path.join(repo, '.reticle.json'), 'utf8')).projectId;
} catch {
  finish(2, 'UNPROVEN', 'no .reticle.json: Reticle is not installed in this repo');
}
const flowDir = path.join(repo, '.reticle', 'flows', projectId);
const flows = fs.existsSync(flowDir) ? fs.readdirSync(flowDir).filter((f) => f.endsWith('.json')).map((f) => f.slice(0, -5)) : [];
report.projectId = projectId;
report.savedFlows = flows;
if (flows.length === 0) finish(2, 'UNPROVEN', `no saved flows in ${path.relative(repo, flowDir)}`);

// 3. The things being driven must be up.
if (!(await reachable(appUrl))) finish(2, 'UNPROVEN', `app not reachable at ${appUrl}`);

async function replay(flowName) {
  const acq = await reticleCalls([['reticle_run', { tool: 'reticle_lease', args: { action: 'acquire', url: appUrl } }]]);
  const lease = parseJson(acq[0].text)?.sessionId;
  if (!lease) throw new Error(`could not lease a tab: ${acq[0].text.slice(0, 200)}`);
  const out = await reticleCalls([
    ['reticle_run', { tool: 'reticle_flow_replay', args: { flowName, sessionId: lease } }],
    ['reticle_run', { tool: 'reticle_lease', args: { action: 'release', sessionId: lease } }],
  ]);
  return parseJson(out[0].text) ?? { status: 'unparsed', raw: out[0].text.slice(0, 500) };
}

try {
  // 4. Optional self-test: a planted impossible check must fail.
  if (args['self-test']) {
    const src = flows.map((f) => JSON.parse(fs.readFileSync(path.join(flowDir, `${f}.json`), 'utf8')))
      .find((f) => f.steps?.some((s) => s.expect?.text?.contains));
    if (!src) finish(2, 'UNPROVEN', 'self-test needs a saved flow with a text check');
    const control = structuredClone(src);
    control.name = 'zz-reticle-gate-control';
    control.intentId = `flow:${control.name}`;
    control.steps.find((s) => s.expect?.text?.contains).expect.text.contains = `reticle-gate planted absence ${Date.now()}`;
    const file = path.join(flowDir, `${control.name}.json`);
    fs.writeFileSync(file, JSON.stringify(control, null, 2));
    let result;
    try { result = await replay(control.name); } finally { fs.rmSync(file, { force: true }); }
    report.selfTest = { source: src.name, status: result.status, caught: result.status !== 'ok' };
    if (result.status === 'ok') finish(1, 'GATE_BLIND', 'planted impossible check passed: this gate cannot fail, so its green means nothing');
  }

  // 5. Change-scoped verdict from Reticle itself.
  const [v] = await reticleCalls([['reticle_verify', { action: 'change', files: report.changedFiles.length ? report.changedFiles : ['.'] }]]);
  const verdict = parseJson(v.text);
  if (!verdict) finish(2, 'UNPROVEN', `reticle_verify returned no JSON: ${(v.error || v.text).slice(0, 300)}`);
  report.reticle = {
    verified: verdict.verified,
    because: verdict.because,
    flowsRun: verdict.flowsRun,
    suite: verdict.suite,
    // Flows Reticle re-ran without knowing which source files they cover: coverage is a guess.
    unknownProvenance: verdict.unknownProvenance,
    undrivenControls: verdict.untouched?.length ?? 0,
  };
  if (verdict.verified !== 'yes') finish(1, 'FAILED', `Reticle verdict "${verdict.verified}": ${verdict.because}`);
  if (verdict.suite?.failed) finish(1, 'FAILED', `${verdict.suite.failed} flow(s) failed`);
  if (report.dirty) finish(1, 'UNBOUND', `flows passed, but ${report.dirty} uncommitted change(s) mean the evidence does not bind to HEAD`);
  finish(0, 'PROVEN', verdict.because);
} catch (e) {
  finish(2, 'UNPROVEN', e.message);
}
