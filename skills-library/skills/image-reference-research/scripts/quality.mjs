// Quality score for an image record: 0..1 from resolution, aspect sanity, and format. Pure.
// Low scores flag references that are too small/degenerate to be useful design references.

const GOOD_FORMATS = new Set(['jpg', 'jpeg', 'png', 'webp', 'tiff', 'avif']);

export function qualityScore(record) {
  const w = Number(record.width) || 0;
  const h = Number(record.height) || 0;
  if (w <= 0 || h <= 0) return 0;

  // Resolution: full credit at >= 2 megapixels, linear below.
  const mp = (w * h) / 1_000_000;
  const resScore = Math.min(1, mp / 2);

  // Aspect: penalise extreme ratios (banners, slivers) that rarely read as usable references.
  const ratio = Math.max(w, h) / Math.min(w, h);
  const aspectScore = ratio <= 2.5 ? 1 : ratio <= 4 ? 0.6 : 0.2;

  // Format: known raster formats score full; unknown/vector get a partial.
  const fmt = String(record.format || '').toLowerCase();
  const formatScore = GOOD_FORMATS.has(fmt) ? 1 : 0.5;

  // Weighted: resolution dominates, aspect and format temper it.
  const score = 0.6 * resScore + 0.25 * aspectScore + 0.15 * formatScore;
  return Math.round(score * 1000) / 1000;
}

// Convenience: keep records at or above a floor (default 0.35).
export function passesQuality(record, floor = 0.35) {
  return qualityScore(record) >= floor;
}
