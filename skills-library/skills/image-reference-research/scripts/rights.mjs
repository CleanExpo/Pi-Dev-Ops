// Deterministic licence-tag → class mapping. Single source of truth shared by the eval and, once
// wired (Phase 1), the production rights classifier. The agent still reads evidence per
// references/rights-classes.md; this maps a KNOWN licence tag to its class, fail-closed on unknown.

const OPEN = new Set([
  'cc0', 'publicdomain', 'pdm', 'public-domain', 'cc-by', 'cc-by-sa', 'cc-by-2.0', 'cc-by-3.0',
  'cc-by-4.0', 'cc-by-sa-2.0', 'cc-by-sa-3.0', 'cc-by-sa-4.0', 'gov-open',
]);
const RESERVED = new Set([
  'all-rights-reserved', 'arr', 'cc-by-nc', 'cc-by-nc-nd', 'cc-by-nd', 'copyright', 'rights-managed',
]);

// tag: a normalised licence identifier lifted from the source (Commons template, Openverse field,
// terms page). licensedInternal: true when the estate holds a licence for the source (e.g. Artlist).
export function classifyLicenceTag(tag, { licensedInternal = false } = {}) {
  if (licensedInternal) return 'licensed-internal';
  if (!tag) return 'unknown-rights-quarantine';
  const t = String(tag).trim().toLowerCase();
  if (OPEN.has(t)) return 'publicly-reproducible';
  if (RESERVED.has(t)) return 'protected-do-not-republish';
  return 'unknown-rights-quarantine';
}

// A record may appear on a board only if its class is board-eligible AND it is not quarantined.
export const BOARD_ELIGIBLE = new Set([
  'publicly-reproducible', 'nominative-reference-only', 'licensed-internal',
]);

export function isBoardEligible(record) {
  return !record.quarantined && BOARD_ELIGIBLE.has(record.licenceClass);
}
