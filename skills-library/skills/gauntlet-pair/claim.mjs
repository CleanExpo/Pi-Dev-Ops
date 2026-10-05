#!/usr/bin/env node
// Advisory project claim for gauntlet pairs. Stops Claude Desktop and Claude CLI
// grinding the same project at once. Advisory on purpose: a hard lock that wedges
// is worse than a claim you can see and override.
//
//   claim.mjs claim   <project> <desktop|cli> [--force]
//   claim.mjs release <project> <desktop|cli>
//   claim.mjs status
//
// Exit codes: 0 ok · 2 usage · 3 held by the other surface

import { mkdirSync, rmdirSync, readFileSync, writeFileSync, renameSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { homedir } from 'node:os';

const DIR = join(homedir(), '.claude', 'gauntlet');
const FILE = join(DIR, 'claims.json');
const LOCK = join(DIR, '.claims.lock');
const SURFACES = ['desktop', 'cli'];
const STALE_MS = 12 * 60 * 60 * 1000;

// Never process.exit() inside withLock — exit skips finally, stranding the lock
// directory and wedging every later call. Throw, unwind, release, then exit.
class Exit extends Error { constructor(code, msg) { super(msg); this.code = code; } }
const die = (code, msg) => { throw new Exit(code, msg); };
const age = (ts) => {
  const h = (Date.now() - ts) / 3600000;
  return h < 1 ? `${Math.round(h * 60)}m` : `${h.toFixed(1)}h`;
};

// mkdir is atomic, so it is the mutex. Without it two surfaces starting together
// both read an empty file and both believe they won.
function withLock(fn) {
  mkdirSync(DIR, { recursive: true });
  for (let i = 0; i < 50; i++) {
    try {
      mkdirSync(LOCK);
      try { return fn(); } finally { rmdirSync(LOCK); }
    } catch (e) {
      if (e.code !== 'EEXIST') throw e;
      try {
        if (Date.now() - statSync(LOCK).mtimeMs > 30000) { rmdirSync(LOCK); continue; }
      } catch { /* lock vanished under us; retry */ }
      Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 100);
    }
  }
  die(1, 'claim: could not acquire lock after 5s');
}

const load = () => {
  try { return JSON.parse(readFileSync(FILE, 'utf8')); }
  catch { return { schemaVersion: 1, claims: {} }; }
};

const save = (data) => {
  const tmp = `${FILE}.tmp.${process.pid}`;
  writeFileSync(tmp, `${JSON.stringify(data, null, 2)}\n`);
  renameSync(tmp, FILE); // atomic on POSIX — never a half-written claims file
};

const held = (c) => c && !c.releasedAt;

const [cmd, project, surface] = process.argv.slice(2);
const force = process.argv.includes('--force');

if (cmd === 'status') {
  const { claims } = load();
  const live = Object.values(claims).filter(held);
  if (!live.length) { console.log('No live claims.'); process.exit(0); }
  for (const c of live) {
    console.log(`${c.surface.padEnd(7)} ${c.project.padEnd(24)} held ${age(c.claimedAt)}${Date.now() - c.claimedAt > STALE_MS ? '  [STALE]' : ''}`);
  }
  process.exit(0);
}

if (!['claim', 'release'].includes(cmd) || !project || !SURFACES.includes(surface)) {
  // Safe to exit directly: no lock is held before withLock runs.
  console.error('usage: claim.mjs claim|release <project> <desktop|cli> [--force]  |  claim.mjs status');
  process.exit(2);
}

try {
  withLock(() => {
  const data = load();
  const existing = data.claims[project];

  if (cmd === 'release') {
    if (!held(existing)) { console.log(`${project}: no live claim to release`); return; }
    if (existing.surface !== surface && !force) {
      die(3, `${project} is claimed by ${existing.surface}, not ${surface}. Use --force to override.`);
    }
    existing.releasedAt = Date.now();
    save(data);
    console.log(`released ${project} (was ${existing.surface}, held ${age(existing.claimedAt)})`);
    return;
  }

  if (held(existing) && existing.surface !== surface && !force) {
    die(3, [
      `REFUSED: ${project} is already claimed by ${existing.surface} (held ${age(existing.claimedAt)}).`,
      `Pick a different project, or release it: claim.mjs release ${project} ${existing.surface}`,
    ].join('\n'));
  }

  data.claims[project] = { project, surface, claimedAt: held(existing) && existing.surface === surface ? existing.claimedAt : Date.now(), releasedAt: null };
  save(data);
  console.log(`claimed ${project} for ${surface}`);
  });
} catch (e) {
  if (!(e instanceof Exit)) throw e;
  console.error(e.message);
  process.exit(e.code);
}
