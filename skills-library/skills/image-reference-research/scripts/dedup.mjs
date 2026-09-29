// Dedup primitives: exact (sha256) + perceptual (dHash) with Hamming-distance grouping.
// Pure Node, zero dependencies. In production a decoder (jimp, Phase 1) turns an image into the
// grayscale matrix `dhashFromGray` expects; the eval feeds fixture matrices directly so the
// hashing logic is provable offline.
import { createHash } from 'node:crypto';

export function sha256(buf) {
  return createHash('sha256').update(buf).digest('hex');
}

// Nearest-neighbour resample of a grayscale matrix (array of rows, values 0-255) to WxH.
function resample(matrix, w, h) {
  const sh = matrix.length, sw = matrix[0].length;
  const out = [];
  for (let y = 0; y < h; y++) {
    const row = [];
    const sy = Math.min(sh - 1, Math.floor((y * sh) / h));
    for (let x = 0; x < w; x++) {
      const sx = Math.min(sw - 1, Math.floor((x * sw) / w));
      row.push(matrix[sy][sx]);
    }
    out.push(row);
  }
  return out;
}

// 64-bit difference hash: resample to 9x8, compare each pixel to its right neighbour → 64 bits.
export function dhashFromGray(matrix) {
  const g = resample(matrix, 9, 8);
  let bits = '';
  for (let y = 0; y < 8; y++) {
    for (let x = 0; x < 8; x++) bits += g[y][x] < g[y][x + 1] ? '1' : '0';
  }
  // pack 64 bits → 16 hex chars
  let hex = '';
  for (let i = 0; i < 64; i += 4) hex += parseInt(bits.slice(i, i + 4), 2).toString(16);
  return hex;
}

export function hammingHex(a, b) {
  if (!a || !b || a.length !== b.length) return 64;
  let d = 0;
  for (let i = 0; i < a.length; i++) {
    let x = parseInt(a[i], 16) ^ parseInt(b[i], 16);
    while (x) { d += x & 1; x >>= 1; }
  }
  return d;
}

// Collapse duplicates: exact canonical URL, then sha256, then perceptual (Hamming <= threshold).
// Returns { kept: [record], groups: [[ids]] } — groups list every id that merged into a kept one.
export function dedupe(records, { phashThreshold = 8 } = {}) {
  const kept = [];
  const groups = [];
  const byUrl = new Map();
  const bySha = new Map();
  for (const r of records) {
    if (r.canonicalImageUrl && byUrl.has(r.canonicalImageUrl)) { merge(byUrl.get(r.canonicalImageUrl), r); continue; }
    if (r.sha256 && bySha.has(r.sha256)) { merge(bySha.get(r.sha256), r); continue; }
    const near = kept.find((k) => k.phash && r.phash && hammingHex(k.phash, r.phash) <= phashThreshold);
    if (near) { merge(near, r); continue; }
    kept.push(r);
    groups.push([r.id]);
    if (r.canonicalImageUrl) byUrl.set(r.canonicalImageUrl, r);
    if (r.sha256) bySha.set(r.sha256, r);
  }
  function merge(keptRec, dup) {
    const gi = kept.indexOf(keptRec);
    groups[gi].push(dup.id);
  }
  return { kept, groups };
}
