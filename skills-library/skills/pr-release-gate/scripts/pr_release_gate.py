#!/usr/bin/env python3
"""Exact-SHA pre-push/PR receipt and Claude PreToolUse interlock."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import importlib.util
import json
import os
import re
import shlex
import subprocess
import sys
from urllib.parse import quote
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCHEMA = 1
MAX_AGE = timedelta(hours=24)
STATE_DIR = Path.home() / ".local" / "state" / "pr-release-gate"
CI_MIRROR = Path(__file__).resolve().parent / "ci_mirror.py"
# gh pr ready is refused unless GitHub's own checks for the PR head are all in this set.
REMOTE_OK = {"SUCCESS", "SKIPPED", "NEUTRAL"}
KEY_PATH = STATE_DIR / "attestation.key"
ENGINEERING_GATE = (
    Path.home() / ".claude" / "skills" / "engineering-requirements"
    / "scripts" / "engineering_gate.py"
)
# The schema-1 coverage field. Kept because schema-1 reports still exist and
# accept_verdict.py still reads them; NOT used to admit a PASS any more, and the
# reason is the whole point of REVIEW_SCHEMA 2 below.
REQUIRED_DIMENSIONS = {
    "architecture", "correctness", "security", "tests", "error-handling",
    "duplication", "conventions",
}

# WHY A SECOND REVIEW SCHEMA (2026-08-13)
#
# Schema 1 defined PASS as an ABSENCE: "zero unresolved P0/P1". Nothing in it
# distinguished a reviewer that read the whole diff and found nothing from one
# that read a tenth of it and found nothing, and `reviewed_dimensions` — the
# field meant to carry coverage — was validated against a CONSTANT, so a
# reviewer discharged it by copying seven strings out of the schema example.
#
# Measured, on one branch (feature/spm-software-factory, 13 rounds, 0 PASS):
# five consecutive rounds declared byte-identical `reviewed_dimensions` while
# returning 3, 2, 1, 11 and 11 blocking findings. The rounds that returned 1-3
# were not cleaner heads; they were narrower reads, and the report could not
# say so. A bar that a fraction-of-the-surface read satisfies is not a bar.
#
# Schema 2 replaces the constant with two things a reviewer cannot satisfy by
# copying: a per-item checklist where every item carries the evidence that
# discharged it, and a coverage ledger checked against the real changed-file
# set computed HERE, from git, not from the report. PASS now means "every
# obligation below was answered, with evidence" AND "no unresolved P0/P1",
# instead of the second clause alone.
#
# Schema 1 is still readable for a FAIL — a drain loop in flight anywhere in
# the estate keeps working, because findings are the payload of a FAIL and they
# do not depend on this. Only a PASS, the verdict that releases code, requires
# schema 2.
REVIEW_SCHEMA = 2

# Eight obligations. Each names what DISCHARGES it, because "reviewed for X" is
# the claim schema 1 could not check. Deliberately finite: eight falsifiable
# items beat fifteen aspirational ones.
REVIEW_CHECKLIST = {
    "coverage-ledger":
        "Every file in the two-dot diff appears in `coverage`, each not-reviewed "
        "entry carrying a reason.",
    "plan-conformance":
        "The diff implements what was approved, not something adjacent to it.",
    "weakened-checks":
        "Searched for removed assertions, added skips, silenced linters, tests "
        "that assert nothing, and swallowed errors. Name the search.",
    "mutation-control":
        "Every test claiming to prevent X was DEMONSTRATED failing under a mutant "
        "reintroducing X, and the source restored byte-identical.",
    "guard-falsification":
        "For each guard or allow-list, the bad input was PLANTED AND RUN. Reading "
        "the regex does not discharge this.",
    "clean-environment-suite":
        "Suites run once, exactly as CI invokes them, under "
        "`env -i HOME=... PATH=... TERM=dumb`. Record the counts.",
    "blast-radius":
        "Direct callers of every changed function or contract were examined.",
    "outbound-actions":
        "Nothing in the diff creates an account, sends a message, publishes, "
        "purchases, or pushes.",
}
CHECKLIST_VERDICTS = {"PASS", "N/A"}
GIT_PUSH = re.compile(r"\bgit\b(?:(?![;&|]).)*?\bpush\b")
GIT_INVOCATION = re.compile(r"\bgit\b")
GH_PR_ANY = re.compile(r"\bgh\b(?:(?![;&|]).)*?\bpr\b")
GH_PR_RELEASE = re.compile(
    r"\bgh\b(?:(?![;&|]).)*?\bpr\b(?:(?![;&|]).)*?\b(?:create|ready|merge)\b"
)
NONRELEASE_ACTIONS = {"view", "list", "checks", "diff", "status", "comment", "close", "reopen", "review", "edit", "lock", "unlock"}
RELEASE_ACTIONS = {"create", "ready", "merge"}
# --- branch-deletion exemption -------------------------------------------------------------
# Refs a delete must never be waved through for, even with an explicit `--delete`. Deleting a
# trunk is not cleanup, and `HEAD` resolves to whatever is checked out.
DELETION_PROTECTED_REFS = {"main", "master", "develop", "trunk", "release", "HEAD"}
# Flags that make a `--delete` push act on refs the command never names, so the static read can
# no longer say the push publishes nothing.
DELETION_DISQUALIFYING_FLAGS = {
    "--mirror", "--all", "--tags", "--follow-tags", "--prune", "--force", "-f",
    "--force-with-lease", "--porcelain-force", "--set-upstream", "-u",
}
# Flags of `git push` that consume the FOLLOWING token as their value. While one is present no
# other token's meaning can be read by membership, because git may be treating it as an argument
# rather than as a flag: `git push -o --delete origin feature/x` publishes at rc=0 (demonstrated
# against a real remote 2026-08-09) precisely because `--delete` is the value of `--push-option`
# there, not a request to delete anything. Refused outright rather than parsed positionally --
# reproducing git's option grammar is the losing move this file keeps relearning.
#
# `--recurse-submodules` and `--signed` are here on an independent review's finding
# (2026-08-09, head 17f1f1a). They validate their value against an enum, so
# `git push --recurse-submodules --delete origin feature` aborts with "bad
# recurse-submodules argument: --delete" rather than publishing -- verified by running it
# against a real remote, remote heads unchanged. But git DID swallow `--delete` as the
# value, so the guard's read of that command was wrong and only git's own enum check stood
# between it and a waived receipt. Membership here does not depend on whether a particular
# flag happens to reject a particular value. Widening this set can only ever narrow the
# exemption, so the bar for adding a flag is "it consumes the next token", nothing more.
DELETION_VALUE_FLAGS = {
    "-o", "--push-option", "--repo", "--receive-pack", "--exec",
    "--recurse-submodules", "--signed",
}
NO_VERIFY = re.compile(r"--no-verify\b")
FORCE = re.compile(r"(?:--force(?:-with-lease)?|-f\b)")
PUSH_INTENT = re.compile(r"\bpush\b")
SHELL_SUBSTITUTION = re.compile(r"(?:\$\(|<\(|>\(|`)")
CD_COMMAND = re.compile(r"\bcd\s+(?:\"([^\"]+)\"|'([^']+)'|([^\s;&|]+))\s*(?:&&|;)")
GIT_CWD = re.compile(r"\bgit\s+-C\s+(?:\"([^\"]+)\"|'([^']+)'|([^\s;&|]+))")
GH_EXPLICIT_REPO = re.compile(
    r"\bgh\b(?:(?![;&|]).)*?(?:--repo(?:=|\s+)|-R(?:=|\s*)?)\S+"
)
GH_REPO_ASSIGN = re.compile(
    r"(?:^|[\s;&|])(?:env\s+)?GH_REPO=(?:\"[^\"]+\"|'[^']+'|[^\s;&|]+)"
)
# File-descriptor redirections (`2>&1`, `>&2`, `&>log`, `2>&-`) contain `&`, which shlex's
# punctuation_chars treats as a command separator. Left alone they split a single command into
# multiple segments and every release check below then misreads it as a compound command.
# Stripped before lexing; this can only ever remove characters, so a real `&&`/`&` separator
# survives and the gate still fails closed.
FD_REDIRECT = re.compile(r"\d*[<>]&(?:\d+-?|-)|&>>?")
GIT_TARGET_OVERRIDE = re.compile(
    r"(?:^|[\s;&|])(?:env\s+)?(?:GIT_DIR|GIT_WORK_TREE)=(?:\"[^\"]+\"|'[^']+'|[^\s;&|]+)"
    r"|\bgit\b(?:(?![;&|]).)*?--(?:git-dir|work-tree)(?:=|\s+)\S+"
)


def run_git(*args: str, cwd: Path | None = None) -> str:
    result = subprocess.run(
        ["git", *args], cwd=cwd, text=True, capture_output=True, check=False
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "git command failed")
    return result.stdout.strip()


def repo_state(cwd: Path | None = None) -> tuple[Path, str, str]:
    """Return (root, head, base) where base is the MERGE-BASE, not origin/main's tip.

    WHY THIS CHANGED. `base` was `git rev-parse origin/main`, and verify_receipt
    requires `receipt["base_sha"] == base`. So ANY merge to main invalidated EVERY
    outstanding receipt on EVERY branch on EVERY machine in the estate. Observed
    2026-08-31: a five-commit branch of estate-sync security fixes could not be
    pushed because an unrelated PR had merged to main minutes earlier. Across four
    surfaces a receipt's lifetime was however long it took someone else to merge.

    THE TIP WAS BUYING NOTHING. Every consumer of `base` already derives the merge
    base itself before diffing -- has_content_delta (line ~183), changed_files
    (~403), and the requirements check (~537) each call
    `git merge-base base head` first. So the reviewed diff is IDENTICAL whether
    `base` holds the tip or the merge base. The tip only ever affected the equality
    check in verify_receipt, i.e. it only ever caused invalidation. It added no
    review coverage in exchange.

    Storing the merge base keeps every property that matters:
      - the diff each consumer computes is bit-identical to before;
      - a REBASE still invalidates the receipt, because the merge base moves;
      - a NEW COMMIT still invalidates it, via head_sha;
      - and it stops being invalidated by other people's merges, which the reviewer
        never examined and which the tests do not exercise.

    It is also more correct in one place. has_content_delta compares
    `tree_entry(root, base, path)` against head. With the tip, a file that main and
    this branch changed IDENTICALLY compared equal, and the branch read as having no
    content delta. Against the merge base it correctly reads as changed.

    WHAT IS DELIBERATELY NOT COVERED: this does not assert the branch is current with
    main. It never did -- re-issuing after a merge re-ran the tests against the same
    worktree, not against a merged tree, so the old binding produced churn rather
    than assurance. "Is this branch behind main" is a merge-time question and belongs
    to the PR's own checks, which evaluate the real merge commit.
    """
    root = Path(run_git("rev-parse", "--show-toplevel", cwd=cwd)).resolve()
    head = run_git("rev-parse", "HEAD", cwd=root)
    # Fall back to the tip when there is no common ancestor (an orphan branch, or a
    # fresh clone whose origin/main is unrelated). Failing closed here would block a
    # push for a topology the gate has no opinion about.
    try:
        base = run_git("merge-base", "HEAD", "origin/main", cwd=root)
    except Exception:
        base = run_git("rev-parse", "origin/main", cwd=root)
    return root, head, base


def receipt_path(root: Path) -> Path:
    path = Path(run_git("rev-parse", "--git-path", "pr-release-gate.json", cwd=root))
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def clean(root: Path) -> bool:
    return not run_git("status", "--porcelain", cwd=root)


def tree_entry(root: Path, ref: str, path: str) -> str:
    return run_git("ls-tree", ref, "--", path, cwd=root)


def has_content_delta(root: Path, base: str, head: str) -> bool:
    merge_base = run_git("merge-base", base, head, cwd=root)
    changed = run_git("diff", "--name-only", merge_base, head, cwd=root).splitlines()
    return any(tree_entry(root, base, path) != tree_entry(root, head, path) for path in changed)


def is_release_command(command: str) -> bool:
    return bool(GIT_PUSH.search(command) or GH_PR_RELEASE.search(command))


# Raw-text segment split, used only by the obfuscation checks. It deliberately
# does NOT use shell_segments(): shlex chokes on the very substitution syntax we
# are trying to detect, and its lex-failure path returns [], which would read as
# "nothing to see here" on exactly the input that matters most.
RAW_SEGMENT_SPLIT = re.compile(r"(?:\|\||&&|[;&|\n\r])")
GIT_OR_GH = re.compile(r"\b(?:git|gh)\b")
# Release intent in raw text. Broader than GIT_PUSH on purpose: it fires on the
# bare word, so a push buried in a long script still trips the multiline refusal.
RELEASE_INTENT = re.compile(r"\bpush\b|\bgh\b(?:(?![;&|]).)*?\bpr\b")
# git flags that consume the following token, so the subcommand scan skips both.
GIT_VALUE_FLAGS = {"-C", "--git-dir", "--work-tree", "-c", "--namespace", "--exec-path"}


def substitution_near_git(command: str) -> bool:
    """True when shell substitution sits in the same segment as git/gh.

    Substitution is banned around release commands because it can hide the verb
    itself: `git p$(echo u)sh` defeats every token-level check in this file. The
    ban used to trigger on GIT_INVOCATION -- the bare word "git" anywhere in the
    command -- so an unrelated `$(...)` elsewhere on the line killed `git status`,
    `git log` and `git commit`. Scoping it to the segment that actually contains
    git or gh keeps the evasion blocked and lets ordinary work through.
    """
    return any(
        GIT_OR_GH.search(segment) and SHELL_SUBSTITUTION.search(segment)
        for segment in RAW_SEGMENT_SPLIT.split(command)
    )


def git_subcommand(tokens: list[str]) -> str | None:
    """The git subcommand in a segment: first non-flag token after `git`."""
    try:
        index = tokens.index("git") + 1
    except ValueError:
        return None
    while index < len(tokens) and tokens[index].startswith("-"):
        flag = tokens[index].split("=", 1)[0]
        index += 2 if flag in GIT_VALUE_FLAGS and "=" not in tokens[index] else 1
    return tokens[index] if index < len(tokens) else None


def shell_segments(command: str) -> list[list[str]]:
    try:
        lexer = shlex.shlex(FD_REDIRECT.sub(" ", command), posix=True, punctuation_chars=";&|")
        lexer.whitespace_split = True
        lexer.commenters = ""
        tokens = list(lexer)
    except ValueError:
        return []
    segments: list[list[str]] = [[]]
    for token in tokens:
        if token and set(token).issubset(set(";&|")):
            if segments[-1]:
                segments.append([])
        else:
            segments[-1].append(token)
    return [segment for segment in segments if segment]


def is_draft_undo(command: str) -> bool:
    """True only for ONE plain `gh pr ready … --undo` and nothing else.

    Review round 23 on a7c30db: a raw-string search waived `gh pr ready 54 --undo && git
    push` (a chained push rode along) and `gh pr ready 54 # --undo` (bash strips the
    comment, so the PR is marked READY). So: one segment, no substitution or newline, the
    comment cut off the way bash would, and `--undo` a real token of that segment.
    """
    if any(c in command for c in "\n\r`") or "$(" in command or is_push_invocation(command):
        return False
    segments = shell_segments(command)
    if len(segments) != 1:
        return False
    tokens = segments[0]
    tokens = tokens[:next((i for i, t in enumerate(tokens) if t.startswith("#")), len(tokens))]
    return gh_pr_action(tokens) == "ready" and "--undo" in tokens


def gh_pr_action(tokens: list[str]) -> str | None:
    value_flags = {"--repo", "-R", "--hostname"}
    try:
        gh_index = tokens.index("gh")
        pr_index = tokens.index("pr", gh_index + 1)
    except ValueError:
        return None
    index = pr_index + 1
    while index < len(tokens) and tokens[index].startswith("-"):
        flag = tokens[index].split("=", 1)[0]
        index += 2 if flag in value_flags and "=" not in tokens[index] else 1
    return tokens[index] if index < len(tokens) else None


def literal_gh_pr_actions(command: str) -> list[str | None]:
    return [action for tokens in shell_segments(command) if (action := gh_pr_action(tokens)) is not None]


def is_push_invocation(command: str) -> bool:
    """True when the command really invokes `git push`.

    `GIT_PUSH` is a cheap prefilter that also matches the word "push" inside a quoted commit
    message, which used to route ordinary `git commit` calls into the release path and block
    them. Confirm at token level. If lexing failed (empty segments) keep the regex verdict so
    an unparseable command still fails closed.
    """
    if not GIT_PUSH.search(command):
        return False
    segments = shell_segments(command)
    if not segments:
        return True
    return any(git_subcommand(tokens) == "push" for tokens in segments)


def is_branch_deletion_only(command: str) -> bool:
    """True only for `git push <remote> --delete <branch>...` forms that cannot publish.

    Deleting an already-merged branch releases no code, so demanding a release receipt for it
    is a false positive -- and the receipt binds to the CURRENT head, so cleanup after a merge
    can never satisfy it. On 2026-08-09 that blocked routine tidy-up and the deletes went
    through `gh api` instead; a guard that pushes ordinary work onto a side channel has stopped
    measuring anything.

    Recognised by POSITIVE SHAPE, not by parsing git's option grammar. Only two spellings are
    admissible -- `git push ...` and `git -C <path> push ...` -- and everything else, including
    `/usr/bin/git` and any alias, simply is not exempt. That asymmetry is deliberate: this
    function's `True` waives a receipt, so an unrecognised shape must fall through to the gate
    rather than be reasoned about. Two bypasses were demonstrated against a real remote by an
    independent review on 2026-08-09, and both came from reading tokens rather than shapes:

      `git push -o --delete origin feature/x` PUBLISHED a commit at rc=0, because git consumed
      `--delete` as the value of `--push-option` while a membership test still saw the word.

      `git push origin --delete tag v1.0` REMOVED a release tag at rc=0, because nothing here
      distinguished the tag namespace from a plain branch name.

    Force and `--no-verify` are refused earlier and unconditionally; this never sees them.
    """
    if SHELL_SUBSTITUTION.search(command):
        return False
    segments = shell_segments(command)
    if len(segments) != 1:
        return False
    tokens = segments[0]
    if not tokens or tokens[0] != "git":
        return False
    rest = tokens[1:]
    if rest[:1] == ["-C"]:
        if len(rest) < 3:
            return False
        rest = rest[2:]
    if rest[:1] != ["push"]:
        return False
    args = rest[1:]
    for token in args:
        # A value-taking flag first: while one is present, no later token's meaning can be read
        # by membership or by position, because git may be consuming it as an argument.
        if token in DELETION_VALUE_FLAGS or any(
            token.startswith(flag + "=") for flag in DELETION_VALUE_FLAGS
        ):
            return False
        # A refspec can publish (`HEAD:main`) or force (`+ref`), and these flags act on refs
        # this function never named.
        if ":" in token or token.startswith("+"):
            return False
        if token in DELETION_DISQUALIFYING_FLAGS:
            return False
        # `tag` selects the tag namespace and `refs/tags/...` names it outright. Deleting a
        # release marker is not the post-merge cleanup this exemption describes, and unlike a
        # merged branch it is not reconstructible from the remote.
        if token == "tag" or token.startswith("refs/tags/"):
            return False
        if token.rstrip("/").rsplit("/", 1)[-1] in DELETION_PROTECTED_REFS:
            return False
    if not any(token in {"--delete", "-d"} for token in args):
        return False
    # `git push --delete` with no ref names deletes nothing; the exemption describes
    # `git push <remote> --delete <branch>` and nothing shorter.
    operands = [token for token in args if not token.startswith("-")]
    return len(operands) >= 2


def release_targets(command: str, default: str | None = None) -> list[str | None]:
    current = str(Path(default or os.getcwd()).expanduser().resolve())
    segments = shell_segments(command)
    if len(segments) != 1:
        return []
    tokens = segments[0]
    if any(token in {"cd", "pushd", "popd"} or token.startswith("(") for token in tokens):
        return []
    action = gh_pr_action(tokens)
    if action in RELEASE_ACTIONS:
        return [current]
    if "git" in tokens and "push" in tokens:
        try:
            index = tokens.index("-C", tokens.index("git") + 1)
            candidate = Path(tokens[index + 1]).expanduser()
            return [str((candidate if candidate.is_absolute() else Path(current) / candidate).resolve())]
        except (ValueError, IndexError):
            return [current]
    return []


def ensure_branch_not_reused(root: Path) -> None:
    branch = run_git("symbolic-ref", "--short", "HEAD", cwd=root)
    result = subprocess.run(
        ["gh", "pr", "list", "--head", branch, "--state", "all", "--json", "number,state,mergedAt"],
        cwd=root, text=True, capture_output=True, check=False,
    )
    if result.returncode:
        raise ValueError("could not verify prior PR history for candidate branch")
    prior = json.loads(result.stdout)
    if any(item.get("state") == "CLOSED" or item.get("mergedAt") for item in prior):
        raise ValueError("branch was used by a closed, merged or superseded PR")


def parse_time(value: str, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise ValueError(f"invalid {label} timestamp") from exc
    if parsed.tzinfo is None or datetime.now(timezone.utc) - parsed > MAX_AGE:
        raise ValueError(f"{label} evidence is stale")
    return parsed


def changed_files(root: Path, base: str, head: str) -> set[str]:
    """The two-dot changed set, by the SAME definition has_content_delta uses.

    Computed here rather than read from the report: a ledger the report also
    supplies its own denominator for is the seven-dimensions bug again.
    """
    merge_base = run_git("merge-base", base, head, cwd=root)
    return {p for p in run_git("diff", "--name-only", merge_base, head,
                               cwd=root).splitlines() if p.strip()}


def check_review_checklist(review: dict) -> None:
    """Every obligation answered, with the evidence that answered it."""
    items = review.get("checklist")
    if not isinstance(items, list):
        raise ValueError(
            "schema 2 review has no `checklist` list. PASS is an enumerable "
            f"checklist, not an absence of findings; required ids: "
            f"{sorted(REVIEW_CHECKLIST)}")
    seen = {}
    for entry in items:
        if not isinstance(entry, dict):
            raise ValueError(f"checklist entry is not an object: {entry!r}")
        seen[str(entry.get("id", "")).strip()] = entry

    missing = sorted(set(REVIEW_CHECKLIST) - set(seen))
    unknown = sorted(set(seen) - set(REVIEW_CHECKLIST))
    if missing:
        raise ValueError(f"checklist omits required items: {missing}")
    if unknown:
        raise ValueError(f"checklist carries unknown items: {unknown}")

    for item_id, entry in sorted(seen.items()):
        verdict = str(entry.get("verdict", "")).strip()
        if verdict not in CHECKLIST_VERDICTS:
            raise ValueError(
                f"checklist item {item_id!r} verdict {verdict!r} is not one of "
                f"{sorted(CHECKLIST_VERDICTS)} — a FAIL here is a blocking "
                "finding, and an unanswered item is not a PASS")
        if not str(entry.get("evidence", "")).strip():
            raise ValueError(
                f"checklist item {item_id!r} has no evidence. What discharges "
                f"it: {REVIEW_CHECKLIST[item_id]}")
        if verdict == "N/A" and not str(entry.get("reason", "")).strip():
            raise ValueError(
                f"checklist item {item_id!r} is N/A without a reason")


def check_review_coverage(review: dict, changed: set[str]) -> list[str]:
    """The ledger must account for the real changed set. Returns not-reviewed paths."""
    coverage = review.get("coverage")
    if not isinstance(coverage, dict):
        raise ValueError("schema 2 review has no `coverage` object")
    reviewed = [str(p) for p in (coverage.get("reviewed") or [])]
    skipped = coverage.get("not_reviewed") or []
    if not isinstance(skipped, list):
        raise ValueError("`coverage.not_reviewed` must be a list")

    skipped_paths = []
    for entry in skipped:
        if not isinstance(entry, dict):
            raise ValueError(f"not_reviewed entry is not an object: {entry!r}")
        path = str(entry.get("path", "")).strip()
        if not path:
            raise ValueError("a not_reviewed entry has no path")
        if not str(entry.get("reason", "")).strip():
            raise ValueError(f"not_reviewed {path!r} carries no reason")
        skipped_paths.append(path)

    accounted = set(reviewed) | set(skipped_paths)
    unaccounted = sorted(changed - accounted)
    if unaccounted:
        raise ValueError(
            f"coverage ledger omits {len(unaccounted)} changed file(s): "
            f"{unaccounted[:10]}{' ...' if len(unaccounted) > 10 else ''}. "
            "A PASS must account for every file it released.")
    foreign = sorted(accounted - changed)
    if foreign:
        raise ValueError(
            f"coverage ledger names {len(foreign)} path(s) not in this diff: "
            f"{foreign[:10]}{' ...' if len(foreign) > 10 else ''}. "
            "A ledger from another head is not evidence for this one.")
    return sorted(skipped_paths)


def load_review(path: Path, primary: str, base: str, head: str, root: Path) -> dict:
    review = json.loads(path.read_text())
    if review.get("schema") != REVIEW_SCHEMA:
        raise ValueError(
            f"review schema must be {REVIEW_SCHEMA} for a PASS (got "
            f"{review.get('schema')!r}). Schema 1 defined PASS as an absence of "
            "findings and could not distinguish a full read from a narrow one; "
            "a releasing verdict now carries `checklist` and `coverage`. Schema "
            "1 remains readable for a FAIL. Shape: "
            "references/reviewer-report-schema.md")
    if review.get("implementation_agent", "").lower() != primary.lower():
        raise ValueError("review implementation_agent does not match primary")
    reviewer = str(review.get("reviewer_agent", "")).strip().lower()
    if not reviewer or reviewer == primary.lower():
        raise ValueError("reviewer must be a different independent agent")
    if not str(review.get("reviewer_session_id", "")).strip():
        raise ValueError("reviewer_session_id is required")
    if review.get("base_sha") != base or review.get("head_sha") != head:
        raise ValueError("review is stale: base/head SHA mismatch")
    if review.get("verdict") != "PASS" or review.get("blocking_findings") != []:
        raise ValueError(
            "independent review did not PASS cleanly: need verdict == \"PASS\" and "
            f"blocking_findings == [] (got verdict={review.get('verdict')!r}, "
            f"blocking_findings={'missing' if 'blocking_findings' not in review else review['blocking_findings']!r}). "
            "P2 warnings belong OUTSIDE blocking_findings, each with a ticket reference."
        )
    check_review_checklist(review)
    not_reviewed = check_review_coverage(review, changed_files(root, base, head))
    if not_reviewed:
        # Not a refusal — a PASS may legitimately skip a lockfile or a generated
        # artefact. But it is said out loud, every time, rather than living
        # silently inside a report nobody re-opens.
        print(f"PR release gate: this PASS declares {len(not_reviewed)} changed "
              f"file(s) NOT reviewed: {not_reviewed}", flush=True)
    parse_time(review.get("reviewed_at"), "review")
    return review


def load_engineering_gate():
    if not ENGINEERING_GATE.exists():
        raise ValueError(
            "repo has a tracked spec.md but the engineering gate validator is not installed"
        )
    loader = importlib.util.spec_from_file_location("engineering_gate", ENGINEERING_GATE)
    module = importlib.util.module_from_spec(loader)
    loader.loader.exec_module(module)
    return module


def check_engineering_requirements(root: Path, base: str, head: str) -> None:
    """A spec this branch wrote or edited must carry an engineering.md the Senior Engineer signed.

    Scoped to the branch diff on purpose: new specs only, no retro-fit of the existing estate.
    Inert on repos with no spec, and on branches that did not touch one.
    """
    merge_base = run_git("merge-base", base, head, cwd=root)
    changed = run_git("diff", "--name-only", merge_base, head, cwd=root).splitlines()
    specs = [path for path in changed if Path(path).name == "spec.md" and (root / path).exists()]
    if not specs:
        return
    gate = load_engineering_gate()
    for spec in specs:
        artifact = (root / spec).parent / "engineering.md"
        try:
            gate.validate(artifact)
        except gate.Blocked as blocked:
            raise ValueError(f"engineering requirements not satisfied for {spec}: {blocked}") from blocked


def key() -> bytes:
    if not KEY_PATH.exists():
        raise ValueError("attestation key is not installed")
    return KEY_PATH.read_bytes()


def canonical(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()


def sign(receipt: dict) -> str:
    return hmac.new(key(), canonical(receipt), hashlib.sha256).hexdigest()


# Variables git exports to its own hooks, every one of which redirects a `git` child at
# some OTHER repository. `git push` sets GIT_DIR, so re-running a suite from inside the
# push hook handed every git call in those tests the pushing repository instead of their
# own fixtures: two suites that had just passed came back 6/18 and 1 failure with 11
# errors, and the gate blocked a release that was in fact green. Reproduced directly —
# `GIT_DIR=... python3 <suite>` fails identically, and unset it passes.
# attest refuses every other GIT_* variable (see attest()).
# GIT_ASKPASS only names a credential-prompt program; it cannot choose the repository,
# config or objects git reads, and Claude Code shells always set it (RA-7791).
ATTEST_ALLOWED_GIT_VARS = frozenset({"GIT_EDITOR", "GIT_PAGER", "GIT_ASKPASS"})

GIT_REDIRECT_VARS = (
    "GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_COMMON_DIR", "GIT_NAMESPACE",
    "GIT_PREFIX", "GIT_QUARANTINE_PATH", "GIT_CONFIG", "GIT_CONFIG_GLOBAL",
    "GIT_CONFIG_SYSTEM", "GIT_INDEX_VERSION",
)


def clean_test_env() -> dict:
    """The ambient environment minus anything that would redirect a `git` child."""
    return {k: v for k, v in os.environ.items() if k not in GIT_REDIRECT_VARS}


def run_tests(root: Path, tests: list[dict]) -> None:
    for test in tests:
        command = str(test.get("command", "")).strip()
        if not command or test.get("exit_code") != 0:
            raise ValueError("receipt contains missing or failed tests")
        print(f"PR release gate: running {command}", flush=True)
        result = subprocess.run(command, cwd=root, shell=True, env=clean_test_env())
        if result.returncode:
            raise ValueError(f"verification failed ({result.returncode}): {command}")


# --- provisioning --------------------------------------------------------------------------
# WHY THIS EXISTS. Step 3 used to run the repository's checks against whatever environment the
# shell happened to inherit, and an inherited environment is not the one CI measures. Observed
# 2026-08-16 in Synthex: `npm run type-check` on origin/main @ f6795c99 exited 1 with 90 errors
# on this host while the SAME commit was green in GitHub CI. Nothing was wrong with the commit.
# Two GENERATED artefacts were stale, from two different generators:
#
#   89 of the 90 errors  ->  node_modules/.prisma/client, absent until `prisma generate`.
#    the last 1 error    ->  packages/brand-config/dist, absent until that package is built.
#
# The second is the instructive one. `dist/` is gitignored, the package is pulled in with a
# `file:` spec and reparse-pointed into node_modules, and the root package.json declares no
# `workspaces` -- so `npm ci` alone does NOT rebuild it and no amount of reinstalling would
# have. A gate that reads a stale artefact reports the ENVIRONMENT, not the candidate.
#
# So this is a rule, not a pair of remembered commands: install the way the repo's own CI
# installs, run the declared generators, then build every locally-linked package whose built
# output a compiler would resolve -- all discovered by parsing the repo, none of it named here.
#
# It fails CLOSED in both directions. A provisioning step that fails raises, so a red gate can
# never be dressed up as green; and the Node assert refuses rather than repairing, because
# installing or switching a runtime is not a gate's job.
NODE_VERSION_FILE = ".node-version"
NODE_MAJOR = re.compile(r"(\d+)")
DEPENDENCY_FIELDS = ("dependencies", "devDependencies", "optionalDependencies")
FILE_SPEC = "file:"
# Fields through which a package publishes something a compiler resolves. A package with a
# build script but no declared entrypoint emits nothing the checks read, so building it would
# be busywork inside a release gate.
ENTRYPOINT_FIELDS = ("main", "module", "types", "typings", "exports")
# The package manager is DECLARED by the repository, never guessed at from what happens to be on
# PATH. `(invocation, flags this gate adds to make it reproducible)`. Estate reality checked
# 2026-08-16: Synthex and CARSI are npm, RestoreAssist and Authority-Site declare
# `packageManager: pnpm@9`, so a hardcoded `npm ci` would have blocked half of it on an install
# failure that says nothing whatever about the candidate.
FROZEN_INSTALLS = {
    "npm": ("npm ci", ()),
    "pnpm": ("pnpm install", ("--frozen-lockfile",)),
}
LOCKFILE_MANAGERS = (
    ("package-lock.json", "npm"),
    ("npm-shrinkwrap.json", "npm"),
    ("pnpm-lock.yaml", "pnpm"),
    ("yarn.lock", "yarn"),
    ("bun.lockb", "bun"),
)


def read_manifest(path: Path) -> dict:
    """A `package.json` as a dict. Absent is empty; present-but-unreadable BLOCKS.

    Returning `{}` for a manifest that exists was a silent skip of exactly the kind this
    provisioning step was built to remove: a manifest that failed to parse declared no `file:`
    dependencies and no `engines`, so the gate provisioned nothing and said so cheerfully. Found
    here 2026-08-16 by a fixture whose `package.json` carried a UTF-8 BOM -- `utf-8` rejects the
    BOM, `utf-8-sig` accepts both, and either way an unreadable manifest is now a refusal.
    """
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"cannot read {path}, so its declarations cannot be provisioned: {exc}")
    if not isinstance(data, dict):
        raise ValueError(f"{path} is not a JSON object")
    return data


def running_node_major() -> int | None:
    """The major of the `node` on PATH, or None when there is no `node` to ask."""
    try:
        result = subprocess.run(["node", "--version"], text=True, capture_output=True, check=False)
    except OSError:
        return None
    match = NODE_MAJOR.search(result.stdout) if result.returncode == 0 else None
    return int(match.group(1)) if match else None


def declared_node_requirements(root: Path) -> list[tuple[str, str]]:
    """`[(source, spec)]` the repository itself declares. Nothing is inferred."""
    declared: list[tuple[str, str]] = []
    pinned = root / NODE_VERSION_FILE
    if pinned.is_file():
        # utf-8-sig: a BOM otherwise survives into the refusal message as a stray glyph.
        value = pinned.read_text(encoding="utf-8-sig", errors="replace").strip()
        if value:
            declared.append((NODE_VERSION_FILE, value))
    engines = read_manifest(root / "package.json").get("engines")
    if isinstance(engines, dict) and str(engines.get("node", "")).strip():
        declared.append(("package.json engines.node", str(engines["node"]).strip()))
    return declared


def node_requirement_met(spec: str, major: int) -> bool:
    """`>=N`/`>N` read as a floor, `||` as alternatives, every other spelling pins the major.

    Deliberately shallow -- reproducing semver range grammar is the losing move this file keeps
    relearning elsewhere, and the failure being defended against is a whole major apart. `||` is
    handled because it is not an edge case in this estate: RestoreAssist declares
    `"20.x || 22.x"`, and reading only the first alternative would have REFUSED a perfectly
    valid Node 22 host. A false refusal is cheap to notice but it stops releases.
    """
    return any(_alternative_met(part, major) for part in spec.split("||"))


def _alternative_met(spec: str, major: int) -> bool:
    match = NODE_MAJOR.search(spec)
    if not match:
        return True
    required = int(match.group(1))
    return major >= required if spec.lstrip().startswith((">=", ">")) else major == required


def node_version_problems(root: Path, major: int | None) -> list[str]:
    declared = declared_node_requirements(root)
    if not declared:
        return []
    if major is None:
        return [f"{source} requires Node {spec}, but no usable `node` is on PATH"
                for source, spec in declared]
    return [f"{source} requires Node {spec}, but this host is running Node {major}.x"
            for source, spec in declared if not node_requirement_met(spec, major)]


def assert_node_version(root: Path) -> None:
    problems = node_version_problems(root, running_node_major())
    if not problems:
        return
    raise ValueError(
        "NODE VERSION MISMATCH -- provisioning refused, NO check has run and NOTHING was "
        "skipped.\n  " + "\n  ".join(problems)
        + "\nThis gate does not install or switch Node: a runtime the gate installed is not "
        "the runtime the release was measured on. Re-run the gate on a host at the declared "
        "version (e.g. `nvm use`), then restart at step 3."
    )


def declared_package_manager(root: Path) -> tuple[str, str]:
    """`(manager, where it said so)`. The corepack field first, then the committed lockfile."""
    declared = str(read_manifest(root / "package.json").get("packageManager", "")).strip()
    if declared:
        return declared.split("@", 1)[0].lower(), "package.json packageManager"
    for lockfile, manager in LOCKFILE_MANAGERS:
        if (root / lockfile).is_file():
            return manager, lockfile
    return "", "no packageManager field and no lockfile at the repository root"


def workflow_flags(root: Path, invocation: str) -> tuple[str, ...]:
    """Flags this repository's OWN workflows pass to `invocation`.

    Read from `.github/workflows/` rather than hardcoded, because they are a property of the
    repo -- Synthex cannot install without `--legacy-peer-deps`, most repos need nothing. Most
    frequent spelling wins, ties broken lexicographically, so the answer is deterministic.
    """
    pattern = re.compile(r"\b" + r"\s+".join(map(re.escape, invocation.split())) + r"\b([^\n\r#]*)")
    counts: Counter[tuple[str, ...]] = Counter()
    for suffix in ("*.yml", "*.yaml"):
        for workflow in sorted((root / ".github" / "workflows").glob(suffix)):
            try:
                text = workflow.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for tail in pattern.findall(text):
                head = re.split(r"[;&|]", tail)[0]
                counts[tuple(token for token in head.split() if token.startswith("-"))] += 1
    if not counts:
        return ()
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]


def install_command(root: Path) -> str:
    manager, source = declared_package_manager(root)
    if not manager:
        raise ValueError(
            f"cannot provision {root}: {source}. This step will not guess one -- declare it "
            "with `packageManager`, or commit the lockfile, so the install is reproducible."
        )
    if manager not in FROZEN_INSTALLS:
        raise ValueError(
            f"cannot provision {root}: {source} declares {manager}, and this step installs "
            f"only {sorted(FROZEN_INSTALLS)} reproducibly. Teach it {manager} rather than "
            "letting checks run against an environment nobody established."
        )
    invocation, frozen = FROZEN_INSTALLS[manager]
    flags = list(frozen)
    for flag in workflow_flags(root, invocation):
        if flag not in flags:
            flags.append(flag)
    return " ".join((invocation, *flags))


def linked_package_dirs(root: Path) -> list[Path]:
    """Directories the root manifest pulls in with a `file:` spec, in declaration order."""
    manifest = read_manifest(root / "package.json")
    dirs: list[Path] = []
    for field in DEPENDENCY_FIELDS:
        section = manifest.get(field)
        if not isinstance(section, dict):
            continue
        for spec in section.values():
            if not isinstance(spec, str) or not spec.startswith(FILE_SPEC):
                continue
            target = (root / spec[len(FILE_SPEC):]).resolve()
            if target.is_dir() and target not in dirs:
                dirs.append(target)
    return dirs


def declares_entrypoint(value) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, dict):
        return any(declares_entrypoint(item) for item in value.values())
    if isinstance(value, list):
        return any(declares_entrypoint(item) for item in value)
    return False


def provision_steps(root: Path) -> list[tuple[Path, str]]:
    """Every command that must run before any check, in order. Pure -- nothing executes."""
    if not (root / "package.json").is_file():
        return []
    steps = [(root, install_command(root))]
    if (root / "prisma" / "schema.prisma").is_file():
        steps.append((root, "npx prisma generate"))
    for package in linked_package_dirs(root):
        manifest = read_manifest(package / "package.json")
        scripts = manifest.get("scripts")
        if not isinstance(scripts, dict) or not str(scripts.get("build", "")).strip():
            continue
        if not any(declares_entrypoint(manifest.get(field)) for field in ENTRYPOINT_FIELDS):
            continue
        steps.append((package, "npm run build"))
    return steps


def provision(root: Path) -> None:
    """Establish every generated artefact the checks read, before any check runs."""
    assert_node_version(root)
    steps = provision_steps(root)
    for cwd, command in steps:
        print(f"PR release gate: provisioning `{command}` in {cwd}", flush=True)
        result = subprocess.run(command, cwd=cwd, shell=True, env=clean_test_env())
        if result.returncode:
            raise ValueError(f"provisioning failed ({result.returncode}): `{command}` in {cwd}")
    print(f"PR release gate: provisioned {len(steps)} step(s) in {root}", flush=True)


def provision_root(path: str | None) -> Path:
    start = Path(path).expanduser().resolve() if path else Path(os.getcwd()).resolve()
    try:
        return Path(run_git("rev-parse", "--show-toplevel", cwd=start)).resolve()
    except Exception:
        return start


def persist_review_report(review_path: Path, head: str) -> Path:
    """Copy the reviewer's report to a stable location outside any worktree.

    The skill has the reviewer work in a disposable review worktree (step 4). Binding
    the receipt to that path directly meant routine cleanup of the worktree after
    `issue`/push silently deleted the only evidence a later `verify`/`gh pr ready` for
    that same head needed — the receipt could not tell "cleaned up" from "never
    reviewed" (RA-7534). Keyed by head SHA: a re-review of the same head is meant to
    replace it, not accumulate.
    """
    stable_dir = STATE_DIR / "reviews"
    stable_dir.mkdir(parents=True, exist_ok=True)
    stable_path = stable_dir / f"{head}.json"
    stable_path.write_bytes(review_path.read_bytes())
    stable_path.chmod(0o600)
    return stable_path


def run_ci_mirror(root: Path, head: str) -> dict:
    """Run every pull_request workflow's steps locally (ci_mirror.py) and bind the result.

    Founder, 19/09/2026: PR #782 passed this gate's recorded tests and reached him red,
    because the recorded tests were a subset of what GitHub runs. The subset was chosen by
    the session; the mirror is derived from the workflows, so it cannot be chosen smaller.
    """
    report = STATE_DIR / "ci-mirror" / f"{head}.json"
    proc = subprocess.run([sys.executable, str(CI_MIRROR), "--repo", str(root), "--json", str(report)],
                          capture_output=True, text=True)
    sys.stdout.write(proc.stdout[-4000:])
    # "A step failed" and "the mirror crashed" are different facts. Until 2026-09-23 one
    # sentence fused them and asserted the first, naming a report file that a crash never
    # wrote -- evidence pointed at, not produced. Meanwhile stderr was captured here and
    # thrown away, so the traceback that explained it was discarded. Check for the artefact
    # FIRST, so "see <path>" is only ever printed once the path is known to exist.
    if not report.exists():
        raise ValueError(
            f"ci-mirror produced NO report for {head} (exit {proc.returncode}). It did not "
            f"reach a verdict, so nothing is known about whether a GitHub check would "
            f"fail. It crashed before writing {report}:\n{proc.stderr.strip()[-1500:]}")
    data = json.loads(report.read_text())
    if data.get("verdict") == "CRASH":
        # The mirror wrote a report saying it DIED, not that a check failed. Those are
        # different facts and only one of them is about this head. Saying "a GitHub PR
        # check would fail" here is the gate asserting a verdict the mirror never reached.
        detail = "".join(r.get("detail", "") for r in data.get("results", []))
        raise ValueError(
            f"ci-mirror CRASHED before reaching a verdict on {head}. Nothing is known "
            f"about whether a GitHub check would fail. Fix the mirror, then re-run:\n"
            f"{detail.strip()[-1500:]}")
    if proc.returncode != 0:
        raise ValueError(f"ci-mirror FAILED: a GitHub PR check would fail on this head; see {report}")
    if data.get("head_sha") != head or data.get("verdict") != "PASS":
        raise ValueError(f"ci-mirror report does not show PASS for {head}")
    return {"report_path": str(report), "report_sha256": hashlib.sha256(report.read_bytes()).hexdigest(),
            "verdict": "PASS", "steps": len(data.get("results", []))}


def check_ci_mirror(receipt: dict, head: str) -> None:
    mirror = receipt.get("ci_mirror") or {}
    path = Path(str(mirror.get("report_path", "")))
    if not mirror or not path.is_file():
        raise ValueError("receipt has no ci-mirror PASS (every GitHub PR check run locally); re-issue it")
    if hashlib.sha256(path.read_bytes()).hexdigest() != mirror.get("report_sha256"):
        raise ValueError("ci-mirror report changed after the receipt was issued")
    data = json.loads(path.read_text())
    if data.get("head_sha") != head or data.get("verdict") != "PASS":
        raise ValueError("ci-mirror report is not a PASS for this head")


def remote_checks_problems(command: str, cwd: str) -> list[str]:
    """For a ready action: GitHub's own checks on the PR head must all be finished and green."""
    tokens = next((t for t in shell_segments(command) if gh_pr_action(t) == "ready"), [])
    after = tokens[tokens.index("ready") + 1:] if "ready" in tokens else []
    target = next((t for t in after if not t.startswith("-")), "")
    args = ["gh", "pr", "view", *([target] if target else []), "--json", "headRefOid,statusCheckRollup"]
    proc = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    if proc.returncode != 0:
        return [f"could not read the PR's GitHub checks: {proc.stderr.strip()[:200]}"]
    data = json.loads(proc.stdout)
    local_head = run_git("rev-parse", "HEAD", cwd=Path(cwd))
    problems = [] if data.get("headRefOid") == local_head else [
        f"PR head {str(data.get('headRefOid', ''))[:12]} is not local HEAD {local_head[:12]}"]
    rollup = data.get("statusCheckRollup") or []
    if not rollup:
        problems.append("GitHub reports no checks yet for this head; wait for them")
    for check in rollup:
        state = (check.get("conclusion") or check.get("state") or check.get("status") or "").upper()
        if state not in REMOTE_OK:
            problems.append(f"{check.get('name') or check.get('context')}: {state or 'PENDING'}")
    return problems


def _gh_api(path: str, cwd: str) -> object:
    """`gh api` from the repository, so `{owner}/{repo}` resolve to it."""
    proc = subprocess.run(["gh", "api", path], cwd=cwd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise ValueError(f"could not read GitHub ({path}): {proc.stderr.strip()[:200]}")
    return json.loads(proc.stdout)


def head_github_problems(head: str, cwd: str, api=_gh_api) -> list[str]:
    """Before a PR is opened: GitHub itself must already have run this exact commit green.

    Founder, 25/09/2026, after big red X's on skills-library PRs: from 13/09 GitHub refused
    to START every job (billing), so every PR showed red while this gate had passed it
    locally, and seven were merged untested. A local PASS says nothing about whether GitHub
    can run the checks at all, so a PR may only open once GitHub has proven the head. The
    workflows run on `push` to any branch for exactly this reason.
    """
    runs: list = []
    complete = False
    for page in range(1, 21):  # every page: a failure on page 2 must not vanish (round 24)
        body = api(f"repos/{{owner}}/{{repo}}/commits/{head}/check-runs?per_page=100&page={page}",
                   cwd) or {}
        batch = body.get("check_runs") or []
        runs += batch
        if len(runs) >= (body.get("total_count") or 0):
            complete = True
            break
        if not batch:  # GitHub stopped short of its own total: a partial list (round 25)
            break
    if not complete:
        return [f"could not read every check on {head[:12]} (GitHub stopped short of its total, "
                "or over 20 pages); refusing rather than judging a partial list"]
    if not runs:
        return [f"GitHub has run no checks on {head[:12]} yet; push the branch and wait for them"]
    problems = []
    # Only a GitHub Actions run proves GitHub ran this repo's workflows. A green from another
    # app (Cursor Bugbot, CodeRabbit) is not that proof (review round 23 on a7c30db), and
    # neither is a head where every Actions job was skipped (round 24): one must have succeeded.
    actions = [r for r in runs if (r.get("app") or {}).get("slug") == "github-actions"]
    if not actions:
        problems.append(f"no GitHub Actions run on {head[:12]}; another app's result is not "
                        "proof that this repo's workflows ran")
    for run in runs:
        name = run.get("name") or "?"
        if run.get("status") != "completed":
            problems.append(f"{name}: still {run.get('status') or 'queued'}")
            continue
        conclusion = (run.get("conclusion") or "").upper()
        if conclusion in REMOTE_OK:
            continue
        job = api(f"repos/{{owner}}/{{repo}}/actions/jobs/{run.get('id')}", cwd) or {}
        if not job.get("steps") and not job.get("runner_name"):
            problems.append(f"{name}: GitHub never started it (no runner, 0 steps). GitHub is "
                            "not running jobs for this repo (runner offline or billing); a PR "
                            "opened now would show red")
        else:
            problems.append(f"{name}: {conclusion or 'UNKNOWN'}")
    if actions and not problems and not any(
            (r.get("conclusion") or "").upper() == "SUCCESS" for r in actions):
        problems.append(f"no GitHub Actions check succeeded on {head[:12]}; skipped or neutral "
                        "alone is not proof the checks ran")
    return problems


def issue(args: argparse.Namespace) -> int:
    root, head, base = repo_state()
    if not clean(root) or not has_content_delta(root, base, head):
        raise ValueError("dirty worktree or no effective candidate content")
    ensure_branch_not_reused(root)
    check_engineering_requirements(root, base, head)
    review_path = Path(args.review_report).expanduser().resolve()
    review = load_review(review_path, args.primary_agent, base, head, root)
    review_path = persist_review_report(review_path, head)
    tests = [{"command": command, "exit_code": 0} for command in args.test]
    if not tests:
        raise ValueError("at least one repository verification command is required")
    # Before ANY exit code is bound to this head: the artefacts those commands read must be the
    # ones this commit generates, not whatever the shell inherited.
    provision(root)
    run_tests(root, tests)
    mirror = run_ci_mirror(root, head)
    current_root, current_head, current_base = repo_state()
    if current_root != root or current_head != head or current_base != base or not clean(root):
        raise ValueError("repo changed while verification was running; review is stale")

    receipt = {
        "schema": SCHEMA, "root": str(root), "head_sha": head, "base_sha": base,
        "primary_agent": args.primary_agent.lower(),
        "reviewer_agent": review["reviewer_agent"].lower(),
        "reviewer_session_id": review["reviewer_session_id"],
        "review_report_path": str(review_path),
        "review_report_sha256": hashlib.sha256(review_path.read_bytes()).hexdigest(),
        "tests": tests, "ci_mirror": mirror, "issued_at": datetime.now(timezone.utc).isoformat(),
    }
    receipt["signature"] = sign(receipt)
    target = receipt_path(root)
    target.write_text(json.dumps(receipt, indent=2) + "\n")
    target.chmod(0o600)
    return verify_receipt(root, rerun_tests=False)


# WHICH REPOSITORIES ARE EXEMPT, and how we know.
#
# The exemption covers repositories that have no release flow for a receipt to bind to
# — in practice the Obsidian notes vault, which is direct-to-main prose with no tests.
#
# It used to name `skills-library`, which is THIS repository, the one that ships this
# gate: `verify` returned 0 without checking the receipt, its HMAC, the SHA binding, the
# review report, the worktree or the tests, and printed nothing while doing it (#30).
#
# What replaced that was a classifier over git remotes, and seven rounds of independent
# review took it apart without converging — blocker counts 2, 2, (refused), 3, 3, 1, 3.
# Each round found a form the previous one had not considered: substrings matching
# `brain-10`; a bare name matching that name under any owner; the fetch url standing in
# for the push destination; only the first pushurl of a remote; only the remote named
# `origin`; a repo with no remotes qualifying vacuously; query strings; hostname case;
# owner/repo case, which GitHub folds; a read-only mirror counted as writable; and push
# options parsed as the destination. That is not a rule with bugs in it, it is the wrong
# shape — detection of a thing, rather than proof of it (#31).
#
# So the repository DECLARES itself, and the declaration must be COMMITTED. Presence at
# HEAD, not merely on disk, so it cannot be conjured to slip one push through and cannot
# arrive without appearing in a diff someone can read. There is no URL to parse, no
# remote to enumerate, no case to fold; every finding in the list above stops existing
# rather than being handled.
EXEMPT_MARKER = ".pr-release-gate-exempt"


# A declaration is an ordinary file. Anything else committed under that name is not one.
REGULAR_FILE_MODES = ("100644", "100755")


def declares_exemption(root: Path) -> bool:
    """True when `root` has COMMITTED an exemption marker FILE at HEAD.

    The tree ENTRY is read, not just the object it resolves to, because three different
    things resolve under one path name and only one of them is a declaration:

    - `cat-file -e` succeeds for any object at all, so a committed DIRECTORY called
      `.pr-release-gate-exempt`, with anything inside it, exempted the repository.
    - checking the object TYPE then still accepted a committed SYMLINK, which is mode
      120000 but type `blob` — so a link pointing anywhere counted as a declaration.

    Both from review, 2026-08-09. The mode settles it: 100644 or 100755, and a blob.

    `--no-replace-objects` because the lookup otherwise honours `refs/replace`, and a
    replacement ref could substitute a tree that carries the marker for one that does
    not — the declaration would then not be in the actual HEAD commit at all.
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "--no-replace-objects",
             "ls-tree", "HEAD", "--", EXEMPT_MARKER],
            capture_output=True, text=True,
        )
    except Exception:
        return False
    if result.returncode != 0:
        return False
    fields = result.stdout.split()
    return len(fields) >= 2 and fields[0] in REGULAR_FILE_MODES and fields[1] == "blob"


def vault_exemption(root: Path) -> bool:
    """True when `root` has declared itself exempt by committing the marker.

    ONE decision point, reached only from `verify_receipt`. An earlier form checked the
    exemption in the push hook AS WELL, and refusing it there fell through to
    `verify_receipt`, which asked again without the command and returned 0 — so the
    hook's extra check decided nothing at all (review 2026-08-09, P1). Two places
    deciding one thing is how #30 got its duplicate in the first place.

    It announces on stderr. A silent `return 0` is indistinguishable from a pass, which
    is how #30 survived: `verify` printed nothing and the empty output was read as one.

    SCOPE, stated rather than guessed at. This exempts pushes of a repository that has
    declared it has no release flow. It does NOT try to work out where a given push
    command points. A previous revision refused the exemption when the command contained
    a URL-shaped token, and review found the grammar wrong in both directions — it
    missed local paths and `file://`, and it misread an ordinary dotted refspec such as
    `release.candidate:refs/heads/x` as a repository. Growing that grammar is the same
    losing move as the remote classifier this replaced (#31), so it is gone. A declared
    repository is trusted for its own pushes; declaring one is a committed, reviewable
    act, and the repositories that matter here — this one included — declare nothing and
    are gated unconditionally.
    """
    if not declares_exemption(root):
        return False
    sys.stderr.write(
        f"PR release gate EXEMPT: {root} carries a committed {EXEMPT_MARKER}; "
        "NO receipt was verified and NO tests were re-run\n")
    return True


def verify_receipt(root: Path | None = None, rerun_tests: bool = True,
                   validated: dict | None = None) -> int:
    # The exemption is decided BEFORE `repo_state`, which resolves `origin/main` and
    # raises without it. A declared repository that has no such ref — a fresh clone, a
    # vault tracking a differently named branch — would otherwise be blocked by a
    # lookup it is exempt from needing. Caught when the hook stopped short-circuiting
    # and started routing every push through here.
    try:
        resolved = Path(run_git("rev-parse", "--show-toplevel", cwd=root)).resolve()
    except Exception:
        # A bare repository has no worktree, so `--show-toplevel` fails. It can still
        # carry a committed marker, and refusing it here would block a declared
        # repository on a lookup it is exempt from needing (review 2026-08-09, P1).
        resolved = Path(root or os.getcwd()).resolve()
    if vault_exemption(resolved):
        return 0
    root, head, base = repo_state(root)
    target = receipt_path(root)
    if not target.exists():
        raise ValueError("missing exact-SHA PR release receipt")
    receipt = json.loads(target.read_text())
    signature = receipt.pop("signature", "")
    if not signature or not hmac.compare_digest(signature, sign(receipt)):
        raise ValueError("receipt signature is missing or invalid")
    if validated is not None:
        # The caller gets the receipt this call read, so it never has to read the file
        # again: a second read is a second receipt, verified by nobody (attest review).
        validated["receipt"] = dict(receipt)
    if receipt.get("schema") != SCHEMA or receipt.get("root") != str(root):
        raise ValueError("invalid receipt schema or repository")
    if receipt.get("head_sha") != head or receipt.get("base_sha") != base:
        raise ValueError("receipt is stale for current HEAD or origin/main")
    parse_time(receipt.get("issued_at"), "receipt")
    review_path = Path(str(receipt.get("review_report_path", "")))
    if not review_path.is_absolute() or not review_path.exists():
        raise ValueError("independent review report is missing")
    actual_hash = hashlib.sha256(review_path.read_bytes()).hexdigest()
    if actual_hash != receipt.get("review_report_sha256"):
        raise ValueError("independent review report changed after receipt issue")
    load_review(review_path, receipt["primary_agent"], base, head, root)
    check_ci_mirror(receipt, head)
    check_engineering_requirements(root, base, head)
    if not clean(root) or not has_content_delta(root, base, head):
        raise ValueError("dirty worktree or empty effective content delta")
    if rerun_tests:
        run_tests(root, receipt.get("tests", []))
        if not clean(root) or run_git("rev-parse", "HEAD", cwd=root) != head:
            raise ValueError("repo changed while verification reran")
    print(f"PR_RELEASE_GATE_PASS head={head} reviewer={receipt['reviewer_agent']}")
    return 0


def log_human_override(command: str) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with (STATE_DIR / "overrides.jsonl").open("a") as handle:
        handle.write(json.dumps({
            "at": datetime.now(timezone.utc).isoformat(), "cwd": os.getcwd(),
            "command_sha256": hashlib.sha256(command.encode()).hexdigest(),
        }) + "\n")


def hook() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        sys.stderr.write("PR release gate BLOCKED: malformed hook payload\n")
        return 2
    if not isinstance(payload, dict) or not isinstance(payload.get("tool_input"), dict):
        sys.stderr.write("PR release gate BLOCKED: missing hook tool_input schema\n")
        return 2
    tool_input = payload["tool_input"]
    command = str(tool_input.get("command") or tool_input.get("cmd") or "")
    if not command.strip():
        sys.stderr.write("PR release gate BLOCKED: missing hook command\n")
        return 2
    if os.environ.get("PR_RELEASE_GATE_HUMAN_OVERRIDE") == "1" and (
        GIT_INVOCATION.search(command) or GH_PR_ANY.search(command)
    ):
        log_human_override(command)
        return 0
    if ("\n" in command or "\r" in command) and RELEASE_INTENT.search(command):
        sys.stderr.write("PR release gate BLOCKED: multiline Git/PR commands are forbidden\n")
        return 2
    if substitution_near_git(command):
        sys.stderr.write("PR release gate BLOCKED: shell substitution around Git/PR commands is forbidden\n")
        return 2
    if GIT_INVOCATION.search(command) and NO_VERIFY.search(command):
        sys.stderr.write("PR release gate BLOCKED: bypass/force flags are agent-forbidden\n")
        return 2
    if GIT_INVOCATION.search(command) and FORCE.search(command) and PUSH_INTENT.search(command):
        sys.stderr.write("PR release gate BLOCKED: bypass/force flags are agent-forbidden\n")
        return 2
    gh_actions = literal_gh_pr_actions(command) if GH_PR_ANY.search(command) else []
    if GH_PR_ANY.search(command) and (
        not gh_actions or any(action not in RELEASE_ACTIONS | NONRELEASE_ACTIONS for action in gh_actions)
    ):
        sys.stderr.write("PR release gate BLOCKED: gh pr action must be a literal recognised subcommand\n")
        return 2
    # `gh pr ready --undo` puts a PR BACK to draft. It releases nothing, so it needs no
    # receipt and no green checks (25/09/2026: the gate refused it on a red PR, the one
    # moment it was needed).
    if is_draft_undo(command):
        sys.stderr.write("PR release gate: `ready --undo` returns a PR to draft; allowed\n")
        return 0
    has_gh_release = any(action in RELEASE_ACTIONS for action in gh_actions)
    is_push = is_push_invocation(command)
    if not is_push and not has_gh_release:
        return 0
    if has_gh_release and (
        GH_EXPLICIT_REPO.search(command) or GH_REPO_ASSIGN.search(command) or os.environ.get("GH_REPO")
    ):
        sys.stderr.write("PR release gate BLOCKED: run gh PR actions from the target repo, not --repo\n")
        return 2
    if is_push and (
        GIT_TARGET_OVERRIDE.search(command) or os.environ.get("GIT_DIR") or os.environ.get("GIT_WORK_TREE")
    ):
        sys.stderr.write("PR release gate BLOCKED: Git target-directory overrides are forbidden\n")
        return 2
    # Deliberately LAST of the refusals: force, --no-verify and target-directory overrides are
    # all rejected above and unconditionally, so this can only ever waive the RECEIPT, never
    # another check. It announces, because a silent `return 0` is indistinguishable from a pass
    # -- that is exactly how #30 survived.
    if is_push and not has_gh_release and is_branch_deletion_only(command):
        sys.stderr.write(
            "PR release gate: branch-deletion push, receipt waived; no other check was skipped\n")
        return 0
    try:
        default_cwd = tool_input.get("cwd") or tool_input.get("workdir") or payload.get("cwd") or os.getcwd()
        targets = release_targets(command, str(default_cwd))
        if len(targets) != 1 or not targets[0]:
            raise ValueError(
                "release command must target exactly one explicit repository context "
                f"(parsed {len(shell_segments(command))} command segment(s) from "
                f"{command.strip()!r}). Run the release action as a single unchained command, "
                "e.g. `git -C <repo> push`."
            )
        target = Path(str(targets[0])).expanduser()
        os.chdir(target)
        status = verify_receipt()
        if status == 0 and "create" in gh_actions:
            problems = head_github_problems(run_git("rev-parse", "HEAD", cwd=target), str(target))
            if problems:
                raise ValueError("PR create refused until GitHub itself has run this exact head "
                                 "green: " + "; ".join(problems[:8]))
        if status == 0 and "ready" in gh_actions:
            problems = remote_checks_problems(command, str(target))
            if problems:
                raise ValueError("ready refused until every GitHub check on this head is green: "
                                 + "; ".join(problems[:8]))
        return status
    except Exception as exc:
        sys.stderr.write(f"PR release gate BLOCKED: {exc}\n")
        return 2


def pr_create(args) -> int:
    """RA-7106: the explicit-path release lane for PR creation (parity with the hook's
    `git -C` handling for pushes). A session whose cwd cannot be the target repo (pinned
    background jobs) invokes this instead of `gh pr create`; it is STRICTLY STRONGER
    than the hook it substitutes for: it re-verifies the full receipt chain at the
    explicit path itself and refuses before gh is ever executed. Always creates a DRAFT
    (gate step 7: draft until remote checks are green at the exact SHA)."""
    root = Path(args.repo_path).expanduser().resolve()
    if not root.is_dir():
        sys.stderr.write(f"PR release gate BLOCKED: repo path does not exist: {root}\n")
        return 2
    os.chdir(root)
    try:
        rc = verify_receipt(root, rerun_tests=False)
    except Exception as exc:
        sys.stderr.write(f"PR release gate BLOCKED: {exc}\n")
        return 2
    if rc != 0:
        return rc
    try:
        ensure_branch_not_reused(root)
        problems = head_github_problems(run_git("rev-parse", "HEAD", cwd=root), str(root))
        if problems:
            raise ValueError("PR create refused until GitHub itself has run this exact head "
                             "green: " + "; ".join(problems[:8]))
    except Exception as exc:
        sys.stderr.write(f"PR release gate BLOCKED: {exc}\n")
        return 2
    branch = run_git("symbolic-ref", "--short", "HEAD", cwd=root)
    cp = subprocess.run(
        ["gh", "pr", "create", "--draft", "--base", args.base, "--head", branch,
         "--title", args.title, "--body-file", args.body_file],
        cwd=root, text=True, capture_output=True,
    )
    sys.stdout.write(cp.stdout)
    sys.stderr.write(cp.stderr)
    return cp.returncode


RECEIPT_STATUS_CONTEXT = "nexus/release-receipt"
_ORIGIN_RE = re.compile(
    r"^(?:https://github\.com/|ssh://git@github\.com/|git@github\.com:)"
    r"([A-Za-z0-9][A-Za-z0-9-]*)/([A-Za-z0-9._-]+?)(?:\.git)?/?$")


def origin_github_repo(url: str) -> str:
    """owner/repo from a github.com origin URL; anything else is refused."""
    match = _ORIGIN_RE.match(url.strip())
    if not match or match.group(2) in {".", "..", ".git"}:
        raise ValueError(f"origin is not a github.com repository URL: {url.strip()!r}")
    return f"{match.group(1)}/{match.group(2)}"


def origin_upstream_branch(root: Path, branch: str) -> str:
    """The origin branch `branch` tracks, else `branch` itself (RA-7791).

    A worktree on local `ug-dep-1154` tracking `origin/dependabot/...` was refused as
    "remote ug-dep-1154 is absent". Read with --local like the origin URL: one file, no
    includes. Any other upstream (another remote, a local one) keeps the local name."""
    try:
        remote = run_git("config", "--local", "--get", f"branch.{branch}.remote", cwd=root)
        merge = run_git("config", "--local", "--get", f"branch.{branch}.merge", cwd=root)
    except RuntimeError:  # no upstream configured
        return branch
    if remote == "origin" and merge.startswith("refs/heads/") and merge != "refs/heads/":
        return merge[len("refs/heads/"):]
    return branch


def attest(args) -> int:
    """Publish the verified receipt to GitHub as a commit status on the exact pushed head.

    WHY (founder ruling 27/09/2026): `main` requires the `nexus/release-receipt` status,
    and branch protection enforces admins, so GitHub refuses to merge any PR whose head
    commit never passed this gate -- whichever account holds the token. The status is
    bound to one SHA, so any later commit drops it and needs a fresh receipt. Posting is
    refused unless the full receipt chain verifies here AND the remote branch head is
    exactly the receipted head: a receipt for a commit nobody pushed attests nothing."""
    root = Path(args.repo_path).expanduser().resolve()
    if not root.is_dir():
        sys.stderr.write(f"PR release gate BLOCKED: repo path does not exist: {root}\n")
        return 2
    # Every git call below must answer from --repo-path. GIT_DIR and its kin point git at
    # another repository; GIT_CONFIG_COUNT/KEY_n/VALUE_n inject config such as
    # url.*.insteadOf; GH_HOST and GH_REPO point gh elsewhere. A denylist kept missing the
    # next one, so every GIT_* is refused except three that only choose an editor, a
    # pager or a credential prompt.
    redirected = sorted(
        name for name in os.environ
        if (name.startswith("GIT_") and name not in ATTEST_ALLOWED_GIT_VARS)
        or name in ("GH_HOST", "GH_REPO")
    )
    if redirected:
        sys.stderr.write("PR release gate BLOCKED: git is redirected by "
                         f"{', '.join(redirected)}; attest reads only --repo-path\n")
        return 2
    os.chdir(root)
    try:
        # Refuse, not decide: verify_receipt returns 0 for a declared exemption, and an
        # exempt repository has no receipt this status could stand for.
        if declares_exemption(root):
            raise ValueError("this repository declares itself exempt from the gate; "
                             "there is no receipt to attest")
        validated: dict = {}
        rc = verify_receipt(root, rerun_tests=False, validated=validated)
        if rc != 0:
            return rc
        # Only the receipt verify_receipt itself read and checked may choose the SHA.
        # The file is not read again: a receipt rewritten after verification, signed or
        # not, would otherwise pick which commit gets the status.
        if "receipt" not in validated:
            raise ValueError("verification returned no receipt to attest")
        receipt = validated["receipt"]
        root, head, _ = repo_state(root)
        branch = origin_upstream_branch(root, run_git("symbolic-ref", "--short", "HEAD", cwd=root))
        receipted = receipt.get("head_sha")
        if receipted != head:
            raise ValueError(f"HEAD is {head}, but the receipt was issued for {receipted}")
        # origin as this repository's own config file records it: --local reads one file
        # with includes off, and `config --get` applies no url.*.insteadOf rewrite, which
        # `remote get-url` would. Not gh's default repo either (a fork or an override).
        repo = origin_github_repo(run_git("config", "--local", "--get", "remote.origin.url", cwd=root))
        # The pushed head is read from the same GitHub repository the status is posted to,
        # so no git transport, rewrite or proxy stands between the check and the post.
        # Every character encoded: '#' or '?' in a valid ref name would otherwise end the
        # path, and GitHub would answer for the prefix branch instead (review e8ec861b).
        # --hostname pins both calls to github.com, where origin was validated: GH_CONFIG_DIR
        # or XDG_CONFIG_HOME can otherwise make gh's default host another server (review 536c61e).
        cp = subprocess.run(["gh", "api", f"repos/{repo}/branches/{quote(branch, safe='')}", "--jq", ".commit.sha",
                             "--hostname", "github.com"],
                            cwd=root, text=True, capture_output=True)
        remote = cp.stdout.strip() if cp.returncode == 0 else ""
        if remote != receipted:
            raise ValueError(f"{repo} branch {branch} is {remote or 'absent'}, "
                             f"not receipted head {receipted}")
    except Exception as exc:
        sys.stderr.write(f"PR release gate BLOCKED: {exc}\n")
        return 2
    description = (f"PASS reviewer={receipt['reviewer_agent']} "
                   f"review={receipt['review_report_sha256'][:12]}")
    cp = subprocess.run(
        ["gh", "api", "--method", "POST", f"repos/{repo}/statuses/{receipted}",
         "-f", "state=success", "-f", f"context={RECEIPT_STATUS_CONTEXT}",
         "-f", f"description={description}", "--hostname", "github.com"],
        cwd=root, text=True, capture_output=True,
    )
    if cp.returncode != 0:
        sys.stderr.write(cp.stderr)
        return cp.returncode
    print(f"PR_RELEASE_GATE_ATTESTED repo={repo} head={head} context={RECEIPT_STATUS_CONTEXT}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="action", required=True)
    issue_parser = sub.add_parser("issue")
    issue_parser.add_argument("--primary-agent", required=True, choices=("claude", "codex"))
    issue_parser.add_argument("--review-report", required=True)
    issue_parser.add_argument("--test", action="append", default=[])
    sub.add_parser("verify")
    sub.add_parser("hook")
    provision_parser = sub.add_parser("provision")
    provision_parser.add_argument("--repo-path", default=None)
    create_parser = sub.add_parser("pr-create")
    create_parser.add_argument("--repo-path", required=True)
    create_parser.add_argument("--base", default="main")
    create_parser.add_argument("--title", required=True)
    create_parser.add_argument("--body-file", required=True)
    attest_parser = sub.add_parser("attest")
    attest_parser.add_argument("--repo-path", required=True)
    args = parser.parse_args()
    if args.action == "issue":
        return issue(args)
    if args.action == "verify":
        return verify_receipt()
    if args.action == "provision":
        provision(provision_root(args.repo_path))
        return 0
    if args.action == "pr-create":
        return pr_create(args)
    if args.action == "attest":
        return attest(args)
    return hook()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        sys.stderr.write(f"PR release gate BLOCKED: {exc}\n")
        raise SystemExit(2)
