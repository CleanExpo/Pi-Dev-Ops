// Offline acceptance harness. No network. Proves the machine-checkable core of the skill:
//   - perceptual dedup F1 >= 0.9 (near-duplicate groups collapse, hard negatives stay apart)
//   - licence-class accuracy >= 0.95 (licence tag -> class mapping)
//   - board invariant: 0 protected / unknown / quarantined images ever reach a board
// Run: node scripts/eval.mjs  (exit 0 = pass, 1 = fail). See references/eval-harness.md.
import { dhashFromGray, dedupe } from './dedup.mjs';
import { classifyLicenceTag, isBoardEligible } from './rights.mjs';
import { renderBoard } from './board.mjs';
import { images, licenceCases } from '../eval/seed/fixtures.mjs';

const THRESHOLDS = { dedupF1: 0.9, licenceAccuracy: 0.95 };
let failed = false;
const say = (ok, label, detail) => {
  if (!ok) failed = true;
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${label}${detail ? `  — ${detail}` : ''}`);
};

// ---- 1. Perceptual dedup F1 ----
const imgs = images();
const records = imgs.map((im) => ({
  id: im.id,
  groupId: im.groupId,
  canonicalImageUrl: `https://fixture.local/${im.id}.png`, // unique → only phash can merge
  sha256: `sha-${im.id}`, // unique → isolates the perceptual path
  phash: dhashFromGray(im.matrix),
}));

const { groups } = dedupe(records, { phashThreshold: 8 });
const clusterOf = new Map();
groups.forEach((ids, ci) => ids.forEach((id) => clusterOf.set(id, ci)));

let tp = 0, fp = 0, fn = 0;
for (let i = 0; i < records.length; i++)
  for (let j = i + 1; j < records.length; j++) {
    const a = records[i], b = records[j];
    const sameTrue = a.groupId === b.groupId;
    const samePred = clusterOf.get(a.id) === clusterOf.get(b.id);
    if (sameTrue && samePred) tp++;
    else if (!sameTrue && samePred) fp++;
    else if (sameTrue && !samePred) fn++;
  }
const precision = tp + fp ? tp / (tp + fp) : 1;
const recall = tp + fn ? tp / (tp + fn) : 1;
const f1 = precision + recall ? (2 * precision * recall) / (precision + recall) : 0;
say(f1 >= THRESHOLDS.dedupF1, `dedup F1 ${f1.toFixed(3)} (>= ${THRESHOLDS.dedupF1})`,
  `P=${precision.toFixed(2)} R=${recall.toFixed(2)} tp=${tp} fp=${fp} fn=${fn}`);

// ---- 2. Licence-class accuracy ----
let correct = 0;
for (const c of licenceCases) {
  const got = classifyLicenceTag(c.tag, { licensedInternal: c.licensedInternal });
  if (got === c.expected) correct++;
  else console.log(`   licence miss: tag="${c.tag}" got=${got} expected=${c.expected}`);
}
const acc = correct / licenceCases.length;
say(acc >= THRESHOLDS.licenceAccuracy, `licence accuracy ${acc.toFixed(3)} (>= ${THRESHOLDS.licenceAccuracy})`,
  `${correct}/${licenceCases.length}`);

// ---- 3. Board invariant: no protected / unknown / quarantined image is ever boarded ----
const boardCandidates = [
  { id: 'ok', licenceClass: 'publicly-reproducible', canonicalImageUrl: 'https://x/1', licenceEvidenceUrl: 'https://x/l' },
  { id: 'prot', licenceClass: 'protected-do-not-republish', canonicalImageUrl: 'https://x/2' },
  { id: 'unk', licenceClass: 'unknown-rights-quarantine', canonicalImageUrl: 'https://x/3' },
  { id: 'q', licenceClass: 'publicly-reproducible', quarantined: true, canonicalImageUrl: 'https://x/4' },
];
const { included, excluded, html } = renderBoard(boardCandidates);
const leaked = boardCandidates.filter((r) => isBoardEligible(r) && (r.licenceClass !== 'publicly-reproducible' && r.licenceClass !== 'nominative-reference-only' && r.licenceClass !== 'licensed-internal' || r.quarantined));
say(included === 1 && excluded === 3 && leaked.length === 0 && !html.includes('/2') && !html.includes('/3') && !html.includes('/4'),
  'board invariant', `included=${included} excluded=${excluded}`);

console.log(failed ? '\nEVAL FAILED' : '\nEVAL PASSED');
process.exit(failed ? 1 : 0);
