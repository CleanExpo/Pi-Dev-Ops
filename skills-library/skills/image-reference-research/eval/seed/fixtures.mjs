// Deterministic, offline eval fixtures. No downloaded images, no network — grayscale matrices
// generated procedurally so dedup + licence classification are provable in CI. Structure mirrors
// the 50-image licence-native seed described in references/eval-harness.md; the pattern set here
// is the machine-checkable core (near-duplicate groups + hard negatives + licence-tag labels).
const N = 32;
const clamp = (v) => Math.max(0, Math.min(255, Math.round(v)));

function make(fn) {
  const m = [];
  for (let y = 0; y < N; y++) {
    const row = [];
    for (let x = 0; x < N; x++) row.push(clamp(fn(x, y)));
    m.push(row);
  }
  return m;
}
function brightness(m, d) { return m.map((r) => r.map((v) => clamp(v + d))); }
function boxBlur(m) {
  const out = m.map((r) => r.slice());
  for (let y = 1; y < N - 1; y++)
    for (let x = 1; x < N - 1; x++) {
      let s = 0;
      for (let dy = -1; dy <= 1; dy++) for (let dx = -1; dx <= 1; dx++) s += m[y + dy][x + dx];
      out[y][x] = clamp(s / 9);
    }
  return out;
}

// Base patterns — each structurally distinct so their dHashes are far apart (hard negatives).
const gradH = make((x) => x * 8);
const gradV = make((_x, y) => y * 8);
const vstripes = make((x) => ((x >> 2) & 1 ? 210 : 40));
const checker = make((x, y) => ((x + y) >> 2) & 1 ? 30 : 220);
const radial = make((x, y) => {
  const dx = x - N / 2, dy = y - N / 2;
  return 230 - Math.hypot(dx, dy) * 9;
});
// Two vertical bright bands — several horizontal edges give a dHash well clear of the flat
// gradient, the monotonic gradients, and the stripe/checker patterns.
const band = make((x) => ((x >= 5 && x < 11) || (x >= 20 && x < 26) ? 225 : 30));

// Duplicate groups: a base + near-duplicate variants (brightness shift, mild blur) that must
// collapse. Distinct bases must NOT collapse with each other.
export const groups = [
  { id: 'A', base: gradH, variants: [brightness(gradH, 40), boxBlur(gradH)] },
  { id: 'B', base: vstripes, variants: [brightness(vstripes, -30)] },
  { id: 'C', base: radial, variants: [brightness(radial, 25), boxBlur(radial)] },
  { id: 'D', base: checker, variants: [brightness(checker, 35)] },
];
export const singletons = [
  { id: 'S1', matrix: gradV },
  { id: 'S2', matrix: band },
];

// Flat list of { id, groupId, matrix }. groupId is the ground-truth duplicate cluster.
export function images() {
  const out = [];
  for (const g of groups) {
    out.push({ id: `${g.id}0`, groupId: g.id, matrix: g.base });
    g.variants.forEach((m, i) => out.push({ id: `${g.id}${i + 1}`, groupId: g.id, matrix: m }));
  }
  for (const s of singletons) out.push({ id: s.id, groupId: s.id, matrix: s.matrix });
  return out;
}

// Licence-classification labels: { tag, licensedInternal, expected }.
export const licenceCases = [
  { tag: 'cc0', expected: 'publicly-reproducible' },
  { tag: 'CC-BY-4.0', expected: 'publicly-reproducible' },
  { tag: 'cc-by-sa-3.0', expected: 'publicly-reproducible' },
  { tag: 'public-domain', expected: 'publicly-reproducible' },
  { tag: 'gov-open', expected: 'publicly-reproducible' },
  { tag: 'all-rights-reserved', expected: 'protected-do-not-republish' },
  { tag: 'cc-by-nc', expected: 'protected-do-not-republish' },
  { tag: 'cc-by-nd', expected: 'protected-do-not-republish' },
  { tag: 'copyright', expected: 'protected-do-not-republish' },
  { tag: '', expected: 'unknown-rights-quarantine' },
  { tag: 'some-unknown-tag', expected: 'unknown-rights-quarantine' },
  { tag: 'artlist', licensedInternal: true, expected: 'licensed-internal' },
];
