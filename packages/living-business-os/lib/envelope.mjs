// Envelope, fixed error texts and issue redaction. Nothing here echoes input:
// messages are fixed per code, zod messages are never passed through, key names
// from unrecognised-key issues are reduced to a count, and path segments that are
// not known schema keys or array indices become "?".

export const EXIT = Object.freeze({
  SUCCESS: 0,
  INVALID_INPUT: 2,
  USAGE: 3,
  INTEGRITY: 4,
  INPUT_TOO_LARGE: 5,
  DOMAIN: 6,
  INTERNAL: 70,
});

export const ERROR_EXIT = Object.freeze({
  INVALID_INPUT: EXIT.INVALID_INPUT,
  USAGE: EXIT.USAGE,
  INTEGRITY: EXIT.INTEGRITY,
  DEPENDENCY_MISSING: EXIT.INTEGRITY,
  INPUT_TOO_LARGE: EXIT.INPUT_TOO_LARGE,
  TENANT_MISMATCH: EXIT.DOMAIN,
  UNKNOWN_SERVICE: EXIT.DOMAIN,
  CONFLICTING_SIGNAL_ID: EXIT.DOMAIN,
  INTERNAL: EXIT.INTERNAL,
});

export const LIMITS = Object.freeze({
  max_input_bytes: 262144,
  max_signals: 500,
  input_timeout_ms: 5000,
  max_answered_question_ids: 100,
});

export const MESSAGES = Object.freeze({
  INVALID_INPUT: 'Input failed validation',
  USAGE: 'Invalid command line',
  INTEGRITY: 'Package integrity check failed; this copy is not the pinned package',
  DEPENDENCY_MISSING: 'A required dependency could not be loaded',
  INPUT_TOO_LARGE: 'Input exceeds the size, count or time limit',
  TENANT_MISMATCH: 'Signal belongs to another organisation',
  UNKNOWN_SERVICE: 'Signal names a service outside the catalogue',
  CONFLICTING_SIGNAL_ID: 'Two signals share an id but differ in content',
  INTERNAL: 'Internal error',
});

const PASS_THROUGH = new Set(['invalid_type', 'too_small', 'too_big', 'invalid_format', 'invalid_value']);
const CUSTOM_PREFIXES = [
  ['Evidence kind ', 'PROVENANCE_MISMATCH'],
  ['Private evidence ', 'PRIVATE_EVIDENCE_NEEDS_ORG'],
  ['Evidence belongs to another tenant', 'FOREIGN_EVIDENCE'],
];

export function sanitizePath(path, schemaKeys) {
  return (Array.isArray(path) ? path : []).map((seg) => {
    if (typeof seg === 'number' && Number.isInteger(seg)) return seg;
    if (typeof seg === 'string' && schemaKeys.includes(seg)) return seg;
    return '?';
  });
}

export function redactIssues(issues, schemaKeys) {
  return issues.map((issue) => {
    const path = sanitizePath(issue.path, schemaKeys);
    if (issue.code === 'unrecognized_keys') {
      return { path, code: 'unrecognized_keys', count: Array.isArray(issue.keys) ? issue.keys.length : 0 };
    }
    if (PASS_THROUGH.has(issue.code)) return { path, code: issue.code };
    if (issue.code === 'custom' && typeof issue.message === 'string') {
      const hit = CUSTOM_PREFIXES.find(([prefix]) => issue.message.startsWith(prefix));
      if (hit) return { path, code: hit[1] };
    }
    return { path, code: 'RULE_FAILED' };
  });
}

export function errorBody(code, issues = []) {
  return { code, message: MESSAGES[code], issues };
}

const DOMAIN_CODES = new Set(['TENANT_MISMATCH', 'UNKNOWN_SERVICE', 'CONFLICTING_SIGNAL_ID']);

/** Map any thrown value to { exit, error }. Domain errors match by exact message; anything else is INTERNAL. */
export function mapError(err) {
  const message = err && typeof err === 'object' ? err.message : undefined;
  if (typeof message === 'string' && DOMAIN_CODES.has(message)) {
    return { exit: EXIT.DOMAIN, error: errorBody(message) };
  }
  return { exit: EXIT.INTERNAL, error: errorBody('INTERNAL') };
}

export function buildEnvelope({ command, identity, ok, result = null, error = null, manifest = null }) {
  const verified = identity === 'verified';
  return {
    ok,
    command,
    identity,
    contract_version: verified ? manifest.contract_version : null,
    package_version: verified ? manifest.package_version : null,
    package_digest: verified ? manifest.package_digest : null,
    draft_only: true,
    approval_required: true,
    result: ok ? result : null,
    error: ok ? null : error,
  };
}
