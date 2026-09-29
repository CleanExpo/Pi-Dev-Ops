#!/usr/bin/env python3
"""Fail-closed validator for engineering.md — the Senior Engineer's signed answer to a spec.

Exit codes: 0 = PASS, 1 = BLOCKED, 2 = usage error.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

CATEGORIES = (
    "data_model",
    "invariants",
    "failure_modes",
    "interface_contract",
    "concurrency",
    "migration",
    "rollback",
    "observability",
    "budget",
    "test_oracle",
)
# PRESCRIBED is the reviewer supplying an answer the spec did not give. It is deliberately
# distinct from DECIDED so downstream automation can tell an answered requirement from an
# invented one — a fabricated number that reads as DECIDED ends up on a dashboard.
LEGAL_STATES = {"DECIDED", "PRESCRIBED", "DEFERRED", "N/A"}
STATES_NEEDING_REASON = {"DEFERRED", "N/A"}
# "bench" is the seventeen-seat principal-engineer bench. The single-reviewer names stay legal so
# artifacts written before the bench existed still validate.
LEGAL_REVIEWERS = {"bench", "boris", "codex"}
BENCH_REVIEWER = "bench"
# A cross-cutting seat owns no category, so "stay in your lane" cannot bind it — it has no lane.
# Told to map each finding to whichever question it answers, with no cap, it maps everything: on
# the 2026-07-29 RestoreAssist run eng-compliance claimed nine of ten categories while every seat
# that owned a category claimed one or two. A seat reviewing the whole spec is doing the chair's
# job, and the chair is then arbitrating against a second chair. Three lets a cross-cutting seat
# land its strongest findings; the rest belong in cross_domain, addressed to the owning seat.
CROSS_CUTTING_CLAIM_CAP = 3
MIN_REASON_CHARS = 12
FRONTMATTER = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n?(.*)\Z", re.DOTALL)
HEADING = re.compile(r"^#{1,6}\s+(.*?)\s*$", re.MULTILINE)
SECTION = re.compile(r"^##\s+(?P<title>.*?)\s*$(?P<body>.*?)(?=^##\s|\Z)", re.MULTILINE | re.DOTALL)
BLOCKQUOTE = re.compile(r"^>\s?(.*\S.*)$", re.MULTILINE)

# Reason strings lifted verbatim from the brief's own examples. A true instance still has to be
# re-derived against the spec in front of you; a pasted exemplar passes every other check by
# construction, which makes N/A the cheapest complete-looking output for exactly the categories
# (concurrency, migration) that catch data corruption.
EXEMPLAR_REASON = {
    "no persistent state is written",
    "no caller outside this module",
    "no user-facing request path",
    "revisit before the second writer lands",
    "no measurement exists until the first bill",
    "no rows exist until the pilot tenant lands",
}

# Reasons that look like an answer but defer nothing concrete. A reason must name the
# condition that puts the question back on the table, not gesture at the future.
HOLLOW_REASON = re.compile(
    r"\A\W*(?:tbd|todo|later|n/?a|none|unknown|not (?:sure|needed|important|applicable)"
    r"|small (?:change|task)|trivial|obvious|skip(?:ped)?|will do|see spec)\W*\Z",
    re.IGNORECASE,
)

# --- positive proof, not detection ------------------------------------------------
# The deny-list above only matches whole strings, so anything phrased around it passes:
# "revisit post launch" is exactly as hollow as "later" and this estate has watched
# detect-the-bad-thing lose three separate times. So the gate no longer asks "is this
# reason bad?" — it asks "does this reason name a condition someone can go and check?"
# and refuses everything that cannot answer.
#
# A trigger has two halves and needs BOTH:
#   1. a connective that introduces a condition, and
#   2. a concrete referent — something countable, nameable, or addressable.
# "later, once we scale" has the connective and no referent. "the pilot tenant lands"
# has both. That is the whole test.

TRIGGER_CONNECTIVE = re.compile(
    r"\b(?:until|before|when|once|if|after|unless|as soon as|the moment)\b",
    re.IGNORECASE,
)

# Something a person could point at: a number, an identifier, a path or file, a version,
# or a domain noun this estate actually measures.
CONCRETE_REFERENT = re.compile(
    r"(?:\d"                                     # any digit — counts, dates, versions
    r"|[A-Za-z0-9_]+\.(?:py|ts|tsx|sql|json|md|db|toml|yml|yaml)\b"   # a file
    r"|\b[a-z]+(?:_[a-z0-9]+)+\b"                # snake_case identifier
    r"|/[A-Za-z0-9_./-]+"                        # a path
    r"|\b(?:row|rows|tenant|tenants|user|users|client|clients|request|requests"
    r"|migration|migrations|table|tables|index|indexes|bill|billing|writer|writers"
    r"|machine|machines|node|nodes|deploy|deploys|release|releases|endpoint|endpoints"
    r"|job|jobs|queue|queues|worker|workers|session|sessions|repo|repos|branch|branches"
    r"|customer|customers|record|records|tenant|pilot|volume|quota|limit)\b)",
    re.IGNORECASE,
)


def reason_names_a_trigger(reason: str) -> bool:
    """True when the reason names a condition that can actually be checked later.

    Requires a conditional connective AND a concrete referent. Prose that gestures at
    the future without naming what changes ("revisit post launch", "later once we
    scale") fails, because nothing in it can ever be evaluated to decide the question
    is back on the table.

    This is the DEFERRED bar. `N/A` is a different claim — see reason_is_grounded.
    """
    text = (reason or "").strip()
    if not text:
        return False
    return bool(TRIGGER_CONNECTIVE.search(text) and CONCRETE_REFERENT.search(text))


def reason_is_grounded(reason: str) -> bool:
    """True when an `N/A` reason names why the category cannot apply.

    DEFERRED says "not yet, and here is what will bring it back". N/A says "never,
    and here is why" — there is no future trigger to name, so demanding a conditional
    connective would be wrong. What N/A still owes is a concrete referent: "pure
    validator, no request path or stored rows" names the absent things and can be
    falsified by anyone who finds a request path. "not applicable" names nothing and
    cannot.
    """
    text = (reason or "").strip()
    if not text:
        return False
    return bool(CONCRETE_REFERENT.search(text))


# --- Q2: decomposition is a count, not a judgement --------------------------------
# "Two rounds then decompose" was unfalsifiable prose an author could argue with. The
# round number is in the frontmatter and a script can read it. Three rounds means the
# spec is too big — that is now arithmetic, not opinion.
MAX_REVIEW_ROUNDS = 2


def decomposition_required(round_number: int) -> bool:
    """True once a spec has consumed more review rounds than one spec should need."""
    try:
        return int(round_number) > MAX_REVIEW_ROUNDS
    except (TypeError, ValueError):
        return False


# --- Q3: the spec reviewer and the diff reviewer must be different agents ----------
# The release gate already demands an independent review bound to the exact final
# commit. Boris reviews the SPEC, that reviewer reviews the CHANGE. If one session does
# both, the second review inherits the first's conclusions and the independence the
# whole chain rests on is gone — the failure mode this estate has already paid for.
def reviewer_independence_violated(spec_reviewer_session: str, diff_reviewer_session: str | None) -> bool:
    """True when the same session reviewed both the spec and the diff.

    A missing diff reviewer is not a violation: Boris runs at spec time, long before a
    diff exists. Only a collision between two present identities is a breach.
    """
    spec_id = (spec_reviewer_session or "").strip()
    diff_id = (diff_reviewer_session or "").strip()
    if not spec_id or not diff_id:
        return False
    return spec_id == diff_id


# --- Q1: calibration floor ---------------------------------------------------------
# A reviewer that always returns the same shape carries no information. The estate's
# precedent is a Haiku reviewer that returned 545 NO and 0 PASS across 1,635 verdicts —
# and nobody noticed, because every individual verdict looked like a judgement. The
# collapse is invisible within one artifact; it only shows up across runs. So the gate
# keeps a ledger and refuses a reviewer whose history has gone flat.
MIN_HISTORY_FOR_CALIBRATION = 4


def calibration_collapsed(history: list[dict[str, int]]) -> bool:
    """True when a reviewer's recent state distributions show no variance.

    Two collapse signatures, both fatal:
      1. Every run produced an identical distribution — the reviewer is emitting its
         prompt, not reading the spec.
      2. Across the whole history not one category was ever DEFERRED or N/A — a
         reviewer that has never once said "this does not apply here" is not
         calibrated, it is agreeing with itself.

    Under MIN_HISTORY_FOR_CALIBRATION runs there is not enough evidence to accuse it.
    """
    runs = [run for run in (history or []) if run]
    if len(runs) < MIN_HISTORY_FOR_CALIBRATION:
        return False
    signatures = {tuple(sorted(run.items())) for run in runs}
    if len(signatures) == 1:
        return True
    return not any(run.get("DEFERRED") or run.get("N/A") for run in runs)


class Blocked(Exception):
    """Raised with the accumulated reasons the artifact cannot pass."""

    def __init__(self, failures: list[str]) -> None:
        super().__init__("; ".join(failures))
        self.failures = failures


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def flatten(text: str) -> str:
    """Whitespace- and case-insensitive form, so a quote survives re-wrapping."""
    return " ".join(text.split()).lower()


def sections(body: str) -> dict:
    return {slug(match.group("title")): match.group("body") for match in SECTION.finditer(body)}


def split_frontmatter(raw: str) -> tuple[dict, str]:
    match = FRONTMATTER.match(raw)
    if not match:
        raise Blocked(["engineering.md has no YAML frontmatter block"])
    try:
        loaded = yaml.safe_load(match.group(1))
    except yaml.YAMLError as exc:
        raise Blocked([f"frontmatter is not valid YAML: {exc}"]) from exc
    if not isinstance(loaded, dict):
        raise Blocked(["frontmatter must be a mapping"])
    return loaded, match.group(2)


def check_spec_binding(meta: dict, artifact: Path, failures: list[str]) -> str:
    """Evidence binds to the exact spec reviewed. Edit the spec and this goes stale.

    Returns the spec text so DECIDED quotes can be checked against it.
    """
    reference = str(meta.get("spec", "")).strip()
    if not reference:
        failures.append("frontmatter is missing `spec`")
        return ""
    spec = (artifact.parent / reference).resolve()
    if not spec.exists():
        failures.append(f"spec not found at {reference}")
        return ""
    text = spec.read_text(errors="replace")
    recorded = str(meta.get("spec_sha256", "")).strip().lower()
    if not recorded:
        failures.append("frontmatter is missing `spec_sha256`")
        return text
    actual = hashlib.sha256(spec.read_bytes()).hexdigest()
    if actual != recorded:
        failures.append(
            f"stale: {spec.name} changed since review "
            f"(recorded {recorded[:12]}…, actual {actual[:12]}…) — re-run Boris"
        )
    return text


def check_provenance(meta: dict, failures: list[str]) -> None:
    reviewer = str(meta.get("reviewer", "")).strip().lower()
    if reviewer not in LEGAL_REVIEWERS:
        failures.append(
            f"`reviewer` must be one of {sorted(LEGAL_REVIEWERS)}, got {reviewer or 'nothing'}"
        )

    # Q2 — decomposition is arithmetic, not argument.
    raw_round = meta.get("review_round", 1)
    if decomposition_required(raw_round):
        failures.append(
            f"`review_round` is {raw_round} — a spec that needs more than {MAX_REVIEW_ROUNDS} "
            "rounds is too big. Decompose it and gate the pieces; do not argue the round "
            "count down"
        )

    # Q3 — the spec reviewer must not also be the diff reviewer.
    if reviewer_independence_violated(
        str(meta.get("reviewer_session_id", "")),
        str(meta.get("diff_reviewer_session_id", "")),
    ):
        failures.append(
            "`reviewer_session_id` equals `diff_reviewer_session_id` — the session that "
            "reviewed this spec also reviewed the change. That is one agent grading its own "
            "earlier opinion; the diff needs a different reviewer"
        )
    stamp = str(meta.get("reviewed_at", "")).strip()
    if not stamp:
        failures.append("frontmatter is missing `reviewed_at`")
        return
    try:
        parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        failures.append(f"`reviewed_at` is not an ISO-8601 timestamp: {stamp}")
        return
    if parsed.tzinfo is None:
        failures.append("`reviewed_at` must carry a timezone offset")
    elif parsed > datetime.now(timezone.utc):
        failures.append("`reviewed_at` is in the future")


def check_quotes_the_spec(name: str, ref: str, body_sections: dict, spec_text: str,
                          failures: list[str]) -> None:
    """DECIDED means *the spec already answers it* — so quote the answer.

    This is the only mechanical difference between DECIDED and PRESCRIBED. Without it the two
    states have identical frontmatter and the boundary is enforced by prose alone, which means
    a reviewer's own invented decisions get filed as things the spec decided.
    """
    section = body_sections.get(slug(ref[1:]), "")
    quotes = [quote.strip() for quote in BLOCKQUOTE.findall(section)]
    if not quotes:
        failures.append(
            f"category `{name}` is DECIDED but its section quotes nothing from the spec — "
            "quote the answering sentence as a `> ` blockquote, or the state is PRESCRIBED"
        )
        return
    haystack = flatten(spec_text)
    stray = [quote for quote in quotes if flatten(quote) not in haystack]
    if len(stray) == len(quotes):
        failures.append(
            f"category `{name}` is DECIDED but no quoted line appears in the spec "
            f"(first was {stray[0][:60]!r}) — if the spec does not say it, the state is PRESCRIBED"
        )


def check_bench(meta: dict, failures: list[str]) -> None:
    """A seat that was dispatched and answered nothing is how a bench decays into theatre.

    Only applies when reviewer is `bench`. Single-reviewer artifacts are unaffected.
    """
    if str(meta.get("reviewer", "")).strip().lower() != BENCH_REVIEWER:
        return
    seated = meta.get("seated")
    if not isinstance(seated, list) or not seated:
        failures.append("reviewer is `bench` but `seated` does not list the seats that reviewed")
        return
    seated_names = {str(s).strip() for s in seated if str(s).strip()}

    categories = meta.get("categories")
    answered_by = set()
    if isinstance(categories, dict):
        for name, entry in categories.items():
            if not isinstance(entry, dict):
                continue
            who = str(entry.get("by", "")).strip()
            if not who:
                failures.append(f"category `{name}` does not say which seat answered it (`by`)")
            else:
                answered_by.add(who)
                if who not in seated_names:
                    failures.append(
                        f"category `{name}` is attributed to `{who}`, which is not in `seated`"
                    )

    # Cross-cutting seats own no category; they declare what they contributed to instead.
    contributed = meta.get("contributed") or []
    contributed_names = {str(s).strip() for s in contributed if str(s).strip()}
    for extra in sorted(contributed_names - seated_names):
        failures.append(f"`contributed` names `{extra}`, which is not in `seated`")

    silent = sorted(seated_names - answered_by - contributed_names)
    if silent:
        failures.append(
            "seats were dispatched but contributed nothing: "
            + ", ".join(f"`{s}`" for s in silent)
            + " — either the seat is broken or it should not have been seated"
        )

    # A seat naming itself in `contributed` is declaring it owns no category. Cap what such a
    # seat may hold, so breadth stays the chair's job rather than becoming a second chair's.
    # Count only substantive claims. A seat answering N/A or DEFERRED on a category is declining
    # it — the opposite of over-reach — and counting those would penalise exactly the behaviour
    # the cap is trying to encourage.
    if isinstance(categories, dict):
        held: dict = {}
        for entry in categories.values():
            if isinstance(entry, dict):
                state = str(entry.get("state", "")).strip().upper()
                who = str(entry.get("by", "")).strip()
                if who and state in {"DECIDED", "PRESCRIBED"}:
                    held[who] = held.get(who, 0) + 1
        for seat in sorted(contributed_names):
            count = held.get(seat, 0)
            if count > CROSS_CUTTING_CLAIM_CAP:
                failures.append(
                    f"`{seat}` owns no category yet holds {count} of them "
                    f"(cap {CROSS_CUTTING_CLAIM_CAP}) — keep its strongest "
                    f"{CROSS_CUTTING_CLAIM_CAP} and move the rest to cross_domain, "
                    "addressed to the seat that owns each"
                )


def check_categories(meta: dict, body: str, spec_text: str, failures: list[str]) -> None:
    categories = meta.get("categories")
    if not isinstance(categories, dict):
        failures.append("frontmatter is missing a `categories` mapping")
        return

    for extra in sorted(set(categories) - set(CATEGORIES)):
        failures.append(f"unknown category `{extra}`")
    anchors = {slug(heading) for heading in HEADING.findall(body)}
    body_sections = sections(body)
    blocking = [
        name for name, entry in categories.items()
        if isinstance(entry, dict) and entry.get("blocking") is True
    ]
    declared = str(meta.get("status", "")).strip().upper()
    expected = "BLOCKED" if blocking else "PASS"
    if declared != expected:
        failures.append(
            f"`status` is {declared or 'unset'} but {len(blocking)} categories carry "
            f"`blocking: true` — status is derived, not chosen; it must be {expected}"
        )
    if blocking:
        failures.append(
            "blocking findings must be resolved before this spec becomes code: "
            + ", ".join(f"`{name}`" for name in sorted(blocking))
        )

    for name in CATEGORIES:
        entry = categories.get(name)
        if entry is None:
            failures.append(f"category `{name}` is missing — all ten are required")
            continue
        if not isinstance(entry, dict):
            failures.append(f"category `{name}` must be a mapping with a `state`")
            continue

        state = str(entry.get("state", "")).strip().upper()
        if state not in LEGAL_STATES:
            failures.append(
                f"category `{name}` has state {state or 'nothing'}; "
                f"legal states are {sorted(LEGAL_STATES)}"
            )
            continue

        if state in STATES_NEEDING_REASON:
            reason = str(entry.get("reason", "")).strip()
            if not reason:
                failures.append(f"category `{name}` is {state} without a reason")
            elif HOLLOW_REASON.match(reason) or len(reason) < MIN_REASON_CHARS:
                failures.append(
                    f"category `{name}` is {state} with a hollow reason ({reason!r}) — "
                    "name the condition that forces it back on the table"
                )
            elif flatten(reason) in {flatten(text) for text in EXEMPLAR_REASON}:
                failures.append(
                    f"category `{name}` is {state} with a reason copied verbatim from the brief's "
                    f"own example ({reason!r}) — re-derive it against this spec"
                )
            elif state == "DEFERRED" and not reason_names_a_trigger(reason):
                failures.append(
                    f"category `{name}` is DEFERRED with a reason that names no checkable "
                    f"trigger ({reason!r}) — say what has to become true for this to come "
                    "back on the table, naming something countable, addressable or nameable "
                    '("until the pilot tenant has rows", not "post launch")'
                )
            elif state != "DEFERRED" and not reason_is_grounded(reason):
                failures.append(
                    f"category `{name}` is {state} with a reason that names nothing "
                    f"falsifiable ({reason!r}) — name the absent thing, so anyone who finds "
                    'it can reopen the question ("no request path or stored rows", not '
                    '"not applicable")'
                )
            continue

        ref = str(entry.get("ref", "")).strip()
        if not ref.startswith("#"):
            failures.append(f"category `{name}` is {state} without a `ref` anchor into the body")
        elif slug(ref[1:]) not in anchors:
            failures.append(f"category `{name}` points at `{ref}`, which is not a heading in the body")
        elif state == "DECIDED":
            check_quotes_the_spec(name, ref, body_sections, spec_text, failures)


CALIBRATION_LEDGER = Path.home() / ".claude" / "engineering-requirements-calibration.jsonl"


def state_distribution(meta: dict) -> dict[str, int]:
    """Count how many categories landed in each state for this run."""
    counts: dict[str, int] = {}
    categories = meta.get("categories") or {}
    if isinstance(categories, dict):
        for entry in categories.values():
            if isinstance(entry, dict):
                state = str(entry.get("state", "")).strip().upper()
                if state:
                    counts[state] = counts.get(state, 0) + 1
    return counts


def record_and_check_calibration(meta: dict, failures: list[str], ledger: Path | None = None) -> None:
    """Append this run's shape to the ledger and refuse a reviewer that has gone flat.

    A single artifact cannot reveal a degenerate reviewer — every individual verdict
    looks like a judgement. The estate learned this from a reviewer that returned 545 NO
    and 0 PASS across 1,635 verdicts without anyone noticing. Collapse is only visible
    across runs, so the gate has to remember.
    """
    if os.environ.get("ENGINEERING_GATE_NO_LEDGER"):
        return
    path = ledger or CALIBRATION_LEDGER
    distribution = state_distribution(meta)
    if not distribution:
        return
    fingerprint = str(meta.get("spec_sha256", "")).strip()
    history: list[dict[str, int]] = []
    seen_fingerprints: set[str] = set()
    try:
        if path.exists():
            for line in path.read_text().splitlines()[-20:]:
                line = line.strip()
                if line:
                    entry = json.loads(line)
                    if isinstance(entry.get("distribution"), dict):
                        history.append(entry["distribution"])
                        seen_fingerprints.add(str(entry.get("spec_sha256", "")))
    except (OSError, json.JSONDecodeError):
        # A damaged ledger must not silently disable the check — say so instead.
        failures.append(f"calibration ledger at {path} is unreadable — cannot verify reviewer variance")
        return

    history.append(distribution)
    if calibration_collapsed(history):
        failures.append(
            f"reviewer calibration has collapsed: the last {len(history)} runs show no "
            "variance, or not one category was ever DEFERRED or N/A. A reviewer that never "
            "says 'this does not apply here' is agreeing with itself. Re-calibrate Boris "
            f"before trusting this verdict (ledger: {path})"
        )

    # Re-validating the same artifact is not a new review. Without this, running the
    # gate twice on one spec writes two identical rows and manufactures the very
    # collapse the check exists to detect.
    if fingerprint and fingerprint[:12] in seen_fingerprints:
        return

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as handle:
            handle.write(json.dumps({
                "reviewed_at": str(meta.get("reviewed_at", "")),
                "reviewer": str(meta.get("reviewer", "")),
                "spec_sha256": str(meta.get("spec_sha256", ""))[:12],
                "distribution": distribution,
            }) + "\n")
    except OSError:
        pass  # a read-only filesystem must not block a valid spec


def validate(artifact: Path) -> None:
    if not artifact.exists():
        raise Blocked([f"no engineering.md at {artifact} — the spec has not been reviewed"])
    meta, body = split_frontmatter(artifact.read_text())

    failures: list[str] = []
    if str(meta.get("type", "")).strip() != "engineering-requirements":
        failures.append("frontmatter `type` must be engineering-requirements")
    spec_text = check_spec_binding(meta, artifact, failures)
    check_provenance(meta, failures)
    check_bench(meta, failures)
    check_categories(meta, body, spec_text, failures)
    record_and_check_calibration(meta, failures)
    if failures:
        raise Blocked(failures)


def resolve(args: argparse.Namespace) -> Path:
    if args.spec:
        return (Path(args.spec).expanduser().resolve().parent / "engineering.md")
    return Path(args.artifact).expanduser().resolve()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact", nargs="?", default="engineering.md",
                        help="path to engineering.md (default: ./engineering.md)")
    parser.add_argument("--spec", help="path to spec.md; checks its sibling engineering.md")
    args = parser.parse_args(argv)

    artifact = resolve(args)
    try:
        validate(artifact)
    except Blocked as blocked:
        print(f"ENGINEERING_GATE_BLOCKED {artifact}", file=sys.stderr)
        for failure in blocked.failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1
    print(f"ENGINEERING_GATE_PASS {artifact}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
