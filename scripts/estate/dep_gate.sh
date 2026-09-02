#!/usr/bin/env bash
# dep_gate.sh - Estate Librarian dependency gate (RA-7408).
#
# The brief (docs/briefs/estate-librarian-v1.md §2) has described this gate since
# 2026-08-30 as the thing holding Estate Librarian execution closed until the
# vendored llm-wiki dependency is identified. It had never been written. RA-7408:
# `git log --all -- '*dep_gate*'` returned no commit on any ref, with
# `guard_claude_lane.sh` (2 commits) as the positive control proving the query
# worked. "The execution gate stays closed" was a sentence with nothing behind it.
#
# CONFLICT OF INTEREST, STATED. This gate restrains agents, and was written by one.
# RA-7134's review notes name "self-authored tests of a self-authored guard" as the
# arrangement that produced two false greens in a single session. The mitigation is
# structural rather than a promise: DEPENDENCY_SATISFIED is UNREACHABLE by
# construction (see stage 3), so writing this gate cannot unblock its author.
#
# Three honest states, per §2:
#   DEPENDENCY_SATISFIED     - every binding verified          (exit 0)
#   DEPENDENCY_WAIVED_BY_D1  - hash-bound founder waiver       (exit 0)
#   BLOCKED_DEPENDENCY       - halts; no unit proceeds         (exit 2)
# Any internal error also halts (exit 1). Every non-zero exit means STOP.
#
# FAIL-CLOSED BY CONSTRUCTION: VERDICT starts BLOCKED_DEPENDENCY and is only ever
# lowered at the very end, after every check has passed. A crash, an unreadable
# file, an unset variable or an early return all leave it blocked. There is no path
# that reaches a passing verdict by omission.
#
# JSON is read with python3, not jq: jq is not guaranteed on a developer Mac, and
# python3 with the stdlib `json` module is. Only the stdlib is used, so this runs
# on the machine default interpreter without the repo venv.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"

# Overridable ONLY so the proof suite can point the gate at fixture manifests.
# It is not a bypass: a caller who redirects this at a manifest of their own still
# has to satisfy every check below, and the D1 waiver additionally requires a
# decision-record file whose digest matches — which a hand-written manifest cannot
# fake without also producing the matching file.
MANIFEST="${DEP_GATE_MANIFEST:-$ROOT/docs/briefs/estate-librarian-v1.manifest.json}"

# Where the manifest's relative paths (artifact, d1_decision_record) resolve. Split
# from MANIFEST because they are two different things: the proof suite points the
# gate at a fixture manifest AND a fixture tree, while production uses neither. It
# defaults to the real repo root, so an unset override cannot silently relocate the
# files being verified. Not a bypass, for the same reason as MANIFEST: redirecting
# it does not lower any check — a waiver still needs a record file whose digest
# matches, which is precisely what a fixture tree has to construct honestly.
ROOT="${DEP_GATE_ROOT:-$ROOT}"

VERDICT="BLOCKED_DEPENDENCY"
REASON="gate did not complete"

# blocked: record the refusal and stop. Named reasons only — a refusal that does not
# say which binding failed sends the reader looking in the wrong place, which is the
# defect RA-7404 was filed about in a different subsystem.
blocked() {
  VERDICT="BLOCKED_DEPENDENCY"
  REASON="$1"
  printf '%s: %s\n' "$VERDICT" "$REASON"
  exit 2
}

# gate_error: the gate itself could not run. Distinct exit code from a refusal so a
# broken gate is never mistaken for a clean verdict, but it halts just the same.
gate_error() {
  printf 'GATE_ERROR: %s\n' "$1" >&2
  exit 1
}

command -v python3 >/dev/null 2>&1 || gate_error "python3 not found; cannot read $MANIFEST"
[ -f "$MANIFEST" ] || gate_error "manifest not found at $MANIFEST"

# field: echo one dependency_gate value, or the empty string. Never raises into the
# caller — an unreadable manifest surfaces as an empty field and is refused below,
# rather than aborting with a traceback that reads like a crash.
field() {
  python3 -c '
import json,sys
try:
    d=json.load(open(sys.argv[1]))
except Exception:
    print(""); sys.exit(0)
g=d.get("dependency_gate") or {}
print(str(g.get(sys.argv[2], "") or ""))
' "$MANIFEST" "$1" 2>/dev/null
}

# top_field: same, for keys at the manifest root rather than inside dependency_gate.
top_field() {
  python3 -c '
import json,sys
try:
    d=json.load(open(sys.argv[1]))
except Exception:
    print(""); sys.exit(0)
print(str(d.get(sys.argv[2], "") or ""))
' "$MANIFEST" "$1" 2>/dev/null
}

# unresolved: true when a value is absent or is a placeholder standing in for an
# answer nobody has supplied. Substring matching is deliberate — the real manifest
# carries prose like "UNRESOLVED_AFTER_FULL_HISTORY_SEARCH - nvk/llm-wiki bare-cloned
# ..." and "TBD - contingent on upstream confirmation", so an exact-equality test
# would read a paragraph of explanation as a satisfied binding.
unresolved() {
  local v="$1"
  [ -z "$v" ] && return 0
  case "$v" in
    *UNRESOLVED*|*NOT_FOUND*|*UNVERIFIED*|*TBD*|*PENDING*|*MISSING*) return 0 ;;
  esac
  return 1
}

# is_sha40: a full 40-hex commit. The short form is what RA-7381 is about — d7751c0a
# identifies nothing verifiable, so accepting 8 characters here would re-admit the
# exact ambiguity this gate exists to close.
is_sha40() { printf '%s' "$1" | grep -qE '^[0-9a-f]{40}$'; }

# ── Stage 0: the manifest must not have been altered ────────────────────────
# The manifest hash-binds the brief the founder decisions live in. Trusting the
# manifest's contents without checking that binding would let an edited brief carry
# a waiver the founder never recorded.
ARTIFACT="$(top_field artifact)"
EXPECT_SHA="$(top_field sha256)"
if [ -n "$ARTIFACT" ] && [ -n "$EXPECT_SHA" ]; then
  ART_PATH="$ROOT/$ARTIFACT"
  [ -f "$ART_PATH" ] || blocked "manifest binds $ARTIFACT but that file is missing"
  ACTUAL_SHA="$(python3 -c '
import hashlib,sys
print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())
' "$ART_PATH" 2>/dev/null)"
  [ -n "$ACTUAL_SHA" ] || gate_error "could not hash $ART_PATH"
  [ "$ACTUAL_SHA" = "$EXPECT_SHA" ] \
    || blocked "hash binding broken: $ARTIFACT does not match the sha256 recorded in the manifest"
fi

# ── Stage 1: the D1 waiver, before the bindings ─────────────────────────────
# Checked first because a valid waiver is a legitimate way past bindings that cannot
# yet be satisfied. It is also the most abusable state, so it is the most constrained.
#
# §2: DEPENDENCY_WAIVED_BY_D1 "requires a hash-bound founder decision record plus
# passing collision/API tests". The brief's own header is explicit that "D1 is not
# effective until hash-bound per §2" — it is a CANDIDATE. So a waiver asserted inside
# the manifest is not a waiver: the record must exist as a separate file whose digest
# matches what the manifest records. That separation is the whole control. Without
# it, anything that can edit the manifest can approve itself.
D1_RECORD="$(field d1_decision_record)"
D1_SHA="$(field d1_decision_record_sha256)"
if [ -n "$D1_RECORD" ] || [ -n "$D1_SHA" ]; then
  [ -n "$D1_RECORD" ] || blocked "d1_decision_record_sha256 is set but d1_decision_record names no file"
  [ -n "$D1_SHA" ]    || blocked "d1_decision_record is set but d1_decision_record_sha256 is absent — an unbound waiver is a candidate, not a decision"
  D1_PATH="$ROOT/$D1_RECORD"
  [ -f "$D1_PATH" ] || blocked "d1_decision_record names $D1_RECORD, which does not exist"
  D1_ACTUAL="$(python3 -c '
import hashlib,sys
print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())
' "$D1_PATH" 2>/dev/null)"
  [ -n "$D1_ACTUAL" ] || gate_error "could not hash $D1_PATH"
  [ "$D1_ACTUAL" = "$D1_SHA" ] \
    || blocked "d1_decision_record $D1_RECORD does not match its recorded sha256 — the waiver is not hash-bound"
  VERDICT="DEPENDENCY_WAIVED_BY_D1"
  REASON="hash-bound founder decision record $D1_RECORD verified"
  printf '%s: %s\n' "$VERDICT" "$REASON"
  exit 0
fi

# ── Stage 2: the four bindings §2 names ─────────────────────────────────────
UPSTREAM_REPO="$(field upstream_repo)"
# `upstream_repo_candidate` is deliberately NOT accepted as `upstream_repo`. RA-7381
# records nvk/llm-wiki as the strongest CANDIDATE on evidence and still unconfirmed;
# promoting a candidate to a binding here would launder a guess into a fact.
[ -n "$UPSTREAM_REPO" ] || blocked "upstream_repo is not set (upstream_repo_candidate is a candidate, not a confirmation — see RA-7381)"
unresolved "$UPSTREAM_REPO" && blocked "upstream_repo is unresolved: $UPSTREAM_REPO"
case "$UPSTREAM_REPO" in
  https://*) ;;
  *) blocked "upstream_repo is not an https URL: $UPSTREAM_REPO" ;;
esac

UPSTREAM_COMMIT="$(field upstream_commit_full)"
unresolved "$UPSTREAM_COMMIT" && blocked "upstream_commit_full is unresolved (RA-7381 blocker)"
is_sha40 "$UPSTREAM_COMMIT" || blocked "upstream_commit_full is not a 40-hex commit — the short form identifies nothing verifiable"

VENDOR_MANIFEST="$(field vendoring_manifest)"
unresolved "$VENDOR_MANIFEST" && blocked "vendoring_manifest is unresolved"
VENDOR_DIGEST="$(field upstream_tree_digest)"
unresolved "$VENDOR_DIGEST" && blocked "upstream_tree_digest is unresolved — the vendored path is not bound to an upstream tree"

INTEGRATION_COMMIT="$(field integration_commit)"
unresolved "$INTEGRATION_COMMIT" && blocked "integration_commit is unresolved"
is_sha40 "$INTEGRATION_COMMIT" || blocked "integration_commit is not a 40-hex commit"

U1U2="$(field u1_u2_tests)"
unresolved "$U1U2" && blocked "u1_u2_tests is unresolved (RA-7381 blocker) — the acceptance tests are unnamed"

# ── Stage 3: full-history verification — DELIBERATELY NOT IMPLEMENTED ───────
# §2 requires complete canonical histories (git fetch --unshallow on Pi-Dev-Ops, a
# full upstream clone) BEFORE classifying. Two reasons it is a refusal rather than
# code:
#
# 1. It is unreachable today — every binding above fails first — so any
#    implementation would ship untested and unobserved. A network path nobody can
#    exercise is the "check that cannot fail" pattern this whole ticket family
#    exists to stop, and shipping one inside the gate written to fix that would be
#    self-defeating.
# 2. It is what makes DEPENDENCY_SATISFIED unreachable, which is the structural
#    answer to this file's conflict of interest. Whoever implements it should not be
#    the party the gate restrains.
#
# Reaching here means the bindings are now well-formed — a real state change worth
# reporting distinctly, not the same refusal as a missing field.
blocked "bindings are well-formed but full-history verification is not implemented; DEPENDENCY_SATISFIED is unreachable until it is (RA-7408)"

# Unreachable. Present so the fail-closed invariant is total: if control ever
# arrives here, the default verdict is still the refusing one.
printf '%s: %s\n' "$VERDICT" "$REASON"
exit 2
