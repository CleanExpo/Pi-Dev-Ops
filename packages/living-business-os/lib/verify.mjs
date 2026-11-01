// Package integrity check. Plain Node, no dependencies, no git: it runs on the
// filesystem, so it works inside a vendored copy (Synthex cutover, M2).
//
// Digest definition: payload entries only (MANIFEST.json is never an entry),
// sorted by UTF-8 bytes of the path; for each entry the UTF-8 line
//   <path> NUL <mode> NUL <sha256 lowercase hex> LF
// is written, and package_digest is sha256 of the concatenated lines.
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';

export const MANIFEST_NAME = 'MANIFEST.json';
export const PACKAGE_NAME = '@unite-group/living-business-os';
const SHA_RE = /^[0-9a-f]{64}$/;
const MODES = new Set(['100644', '100755']);

export function sha256Hex(buf) {
  return crypto.createHash('sha256').update(buf).digest('hex');
}

export class IntegrityError extends Error {
  constructor(reason, detail = '') {
    super(`${reason}${detail ? `: ${detail}` : ''}`);
    this.reason = reason;
    this.detail = detail;
  }
}

function byUtf8(a, b) {
  return Buffer.compare(Buffer.from(a.path, 'utf8'), Buffer.from(b.path, 'utf8'));
}

export function digestOf(entries) {
  const sorted = [...entries].sort(byUtf8);
  for (let i = 1; i < sorted.length; i++) {
    if (sorted[i].path === sorted[i - 1].path) throw new IntegrityError('DUPLICATE_PATH', 'duplicate path in entries');
  }
  const h = crypto.createHash('sha256');
  for (const e of sorted) h.update(Buffer.from(`${e.path}\0${e.mode}\0${e.sha256}\n`, 'utf8'));
  return h.digest('hex');
}

/** golden_digest / surface_digest are the same digest over a subset of the entries. */
export function subsetDigest(entries, predicate) {
  return digestOf(entries.filter((e) => predicate(e.path)));
}
export const isGolden = (p) => p.startsWith('test/golden/expected/');
export const isSurface = (p) => p === 'contract-surface.json';

function unsafePath(p) {
  return typeof p !== 'string' || p === '' || p.startsWith('/') || p.includes('\\') || p.split('/').some((s) => s === '..' || s === '' || s === '.');
}

/** Shape-check manifest text. Throws IntegrityError. Also used for the base manifest by --compat. */
export function parseManifest(text) {
  let m;
  try {
    m = JSON.parse(text);
  } catch {
    throw new IntegrityError('MANIFEST_INVALID', 'not valid JSON');
  }
  const ok =
    m && typeof m === 'object' && !Array.isArray(m) &&
    m.schema === 'lbos-manifest/1' && m.package === PACKAGE_NAME &&
    typeof m.package_version === 'string' && typeof m.contract_version === 'string' &&
    SHA_RE.test(m.package_digest ?? '') && SHA_RE.test(m.golden_digest ?? '') && SHA_RE.test(m.surface_digest ?? '') &&
    Array.isArray(m.files) &&
    m.files.every((f) => f && typeof f === 'object' && typeof f.path === 'string' && SHA_RE.test(f.sha256 ?? '') && Number.isInteger(f.bytes) && MODES.has(f.mode));
  if (!ok) throw new IntegrityError('MANIFEST_INVALID', 'unexpected shape');
  return m;
}

/** Read and shape-check MANIFEST.json. Throws IntegrityError. */
export function readManifest(dir) {
  let text;
  try {
    text = fs.readFileSync(path.join(dir, MANIFEST_NAME), 'utf8');
  } catch {
    throw new IntegrityError('MANIFEST_MISSING', MANIFEST_NAME);
  }
  return parseManifest(text);
}

/** Walk the package with lstat. Returns payload entries; throws IntegrityError on symlinks and special files. */
export function collectPayload(dir) {
  const out = [];
  const walk = (rel) => {
    for (const name of fs.readdirSync(path.join(dir, rel)).sort()) {
      const relPath = rel ? `${rel}/${name}` : name;
      if (!rel && name === 'node_modules') continue;
      if (!rel && name === MANIFEST_NAME) continue;
      const abs = path.join(dir, relPath);
      const st = fs.lstatSync(abs);
      if (st.isSymbolicLink()) throw new IntegrityError('SYMLINK', relPath);
      if (st.isDirectory()) walk(relPath);
      else if (st.isFile()) {
        const buf = fs.readFileSync(abs);
        out.push({ path: relPath, sha256: sha256Hex(buf), bytes: buf.length, mode: st.mode & 0o111 ? '100755' : '100644' });
      } else throw new IntegrityError('NON_REGULAR', relPath);
    }
  };
  walk('');
  return out;
}

/** Full check. Never throws: returns { ok, reason, detail, manifest }. */
export function verifyPackage(dir) {
  let manifest;
  try {
    manifest = readManifest(dir);
    const seen = new Set();
    for (const f of manifest.files) {
      if (unsafePath(f.path)) throw new IntegrityError('MANIFEST_PATH_UNSAFE', 'unsafe manifest path');
      if (seen.has(f.path)) throw new IntegrityError('DUPLICATE_PATH', 'duplicate manifest path');
      seen.add(f.path);
    }
    const actual = collectPayload(dir);
    const want = new Map(manifest.files.map((f) => [f.path, f]));
    const have = new Map(actual.map((f) => [f.path, f]));
    for (const p of want.keys()) if (!have.has(p)) throw new IntegrityError('MISSING_FILE', p);
    for (const p of have.keys()) if (!want.has(p)) throw new IntegrityError('EXTRA_FILE', p);
    for (const [p, w] of want) {
      const h = have.get(p);
      if (h.sha256 !== w.sha256) throw new IntegrityError('HASH_MISMATCH', p);
      if (h.bytes !== w.bytes) throw new IntegrityError('BYTES_MISMATCH', p);
      if (h.mode !== w.mode) throw new IntegrityError('MODE_MISMATCH', p);
    }
    if (digestOf(manifest.files) !== manifest.package_digest) throw new IntegrityError('DIGEST_MISMATCH', 'package_digest');
    if (subsetDigest(manifest.files, isGolden) !== manifest.golden_digest) throw new IntegrityError('METADATA_MISMATCH', 'golden_digest');
    if (subsetDigest(manifest.files, isSurface) !== manifest.surface_digest) throw new IntegrityError('METADATA_MISMATCH', 'surface_digest');
    const pkg = JSON.parse(fs.readFileSync(path.join(dir, 'package.json'), 'utf8'));
    if (pkg.version !== manifest.package_version) throw new IntegrityError('VERSION_MISMATCH', 'package_version');
    return { ok: true, manifest };
  } catch (e) {
    if (e instanceof IntegrityError) return { ok: false, reason: e.reason, detail: e.detail, manifest: null };
    return { ok: false, reason: 'MANIFEST_INVALID', detail: 'unreadable', manifest: null };
  }
}
