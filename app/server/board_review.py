"""board_review.py — the SHA-bound push gate (Unit 2).

WHY THIS EXISTS. PR #741 merged to main carrying two P1 defects that an independent
review had already found. The review's FAIL verdict existed only inside a CLI session:
it never reached the PR, and the merge went ahead off 16 green CI checks. The lesson is
not "post the verdict somewhere visible" — a commit status cannot block a merge on a
repo whose plan tier has no branch protection, so visibility alone changes nothing.

So the gate is placed where it can actually refuse: in `_phase_push`, before the push
happens. `_phase_adversary` writes the receipt; `_phase_push` reads it and refuses
unless the receipt binds to the exact commit about to be pushed.

THE BINDING IS THE POINT. A receipt that says "reviewed" without saying WHAT was
reviewed is worthless — it would keep passing while the code moved underneath it. So
the receipt carries `head_sha`, and the gate compares it against the live HEAD. Amend a
commit after a review and the SHA changes, so the receipt stops matching and the gate
refuses again. That case is not theoretical; it is the ordinary shape of "one more small
fix before pushing".

FAIL CLOSED. Missing, unreadable, unparseable, wrong-shaped or stale receipt all return
REFUSE. Absence is never a pass (rules/truth-hacking.md, Law 3). The only path that
returns allow is an explicit, matched, approving receipt.
"""
from __future__ import annotations

import datetime
import json
import logging
from pathlib import Path
from typing import Any, Awaitable, Callable, NamedTuple

# `run_cmd(workspace, *argv, timeout=...) -> (rc, stdout, stderr)`. Passed in rather
# than imported so this module stays free of session_phases, which imports it.
RunCmd = Callable[..., Awaitable[tuple[int, str, str]]]

log = logging.getLogger("pi-ceo.board_review")

# Inside `.git/`, deliberately, and NOT in the working tree. The receipt is build
# metadata about a sha, not source. In the tree it did two kinds of damage: `git
# status` reported it, so the push phase's "nothing changed since the review" check
# saw the gate's own artefact as an unreviewed change; and `git add -A` would sweep
# it into the target repo's next commit. `git status` never reports `.git/`, and
# nothing can commit from there. Same reasoning as `.git/pr-release-gate.json`.
RECEIPT_RELPATH = Path(".git") / "pi-ceo-board-review.json"

# Verdicts that permit a push. Anything else — BLOCK, UNKNOWN, a typo, a verdict
# string this module has never heard of — refuses, because an unrecognised verdict
# is an unproven one.
_ALLOWING_VERDICTS = frozenset({"APPROVE", "APPROVE_WITH_NOTES", "SKIP_NO_DIFF", "SKIP_DOCS_ONLY"})


class GateResult(NamedTuple):
    allowed: bool
    reason: str


def receipt_path(workspace: str | Path) -> Path:
    return Path(workspace) / RECEIPT_RELPATH


def write_receipt(
    workspace: str | Path,
    head_sha: str,
    verdict: str,
    session_id: str = "",
) -> Path | None:
    """Record a board-review verdict bound to `head_sha`. Returns the path, or None.

    Never raises: a receipt-write failure must not crash the build. It simply means
    no receipt exists, and the gate refuses — which is the safe direction.
    """
    path = receipt_path(workspace)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "head_sha": head_sha,
            "verdict": verdict,
            "session_id": session_id,
            "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        }
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(path)
        return path
    except OSError as exc:
        log.warning("board-review receipt write failed: %s", exc)
        return None


def _load(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def check(workspace: str | Path, head_sha: str) -> GateResult:
    """May the commit at `head_sha` be pushed? Deny is the default."""
    if not head_sha:
        return GateResult(False, "HEAD sha is unknown, so no receipt can be matched to it")

    path = receipt_path(workspace)
    if not path.exists():
        return GateResult(
            False,
            f"no board-review receipt at {RECEIPT_RELPATH} — the review has not run for this build",
        )

    data = _load(path)
    if data is None:
        return GateResult(False, f"board-review receipt at {RECEIPT_RELPATH} is unreadable or not a JSON object")

    receipt_sha = str(data.get("head_sha") or "")
    verdict = str(data.get("verdict") or "").upper()

    if not receipt_sha:
        return GateResult(False, "board-review receipt carries no head_sha, so it binds to nothing")

    if receipt_sha != head_sha:
        return GateResult(
            False,
            f"board-review receipt binds to {receipt_sha[:12]} but HEAD is {head_sha[:12]} — "
            "the code changed after it was reviewed",
        )

    if verdict not in _ALLOWING_VERDICTS:
        return GateResult(False, f"board-review verdict is {verdict or 'EMPTY'}, which does not permit a push")

    return GateResult(True, f"board-review {verdict} bound to {head_sha[:12]}")


# git's well-known empty-tree object. A workspace with no commits has no HEAD to diff
# against; diffing this shows the whole tree as added, which is what a first commit is.
EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"


async def _tree_dirty(workspace: str, run_cmd: RunCmd) -> bool:
    """True when the working tree holds content the reviewer never saw.

    An unreadable status counts as dirty. Absence is never a pass.
    """
    try:
        rc, out, _ = await run_cmd(workspace, "git", "status", "--porcelain")
    except Exception as exc:  # noqa: BLE001
        log.warning("board-review could not read status: %s", exc)
        return True
    return rc != 0 or bool(out.strip())


async def commit_build_output(workspace: str, run_cmd: RunCmd) -> str:
    """Commit what the build produced; return the sha the build started from.

    THE UNIT 2 P0 LIVED IN THE ORDER OF THESE TWO STEPS. This commit used to happen
    at the top of `_phase_push`, which is AFTER the adversary phase wrote the receipt.
    The commit moved HEAD, so the receipt bound to the pre-commit sha and the gate
    compared the post-commit one. They can never match when a session produced work —
    so the gate refused every real build and passed only the ones with nothing to
    commit. Committing before the review means one sha covers both.

    It also closes a second hole: `git diff HEAD` does not show untracked files, so a
    build made entirely of NEW files reviewed as "no diff" and was skipped. Staging
    first puts those files inside the reviewed range.
    """
    rc, base, _ = await run_cmd(workspace, "git", "rev-parse", "HEAD", timeout=10)
    base = base.strip() if rc == 0 and base.strip() else EMPTY_TREE
    if await _tree_dirty(workspace, run_cmd):
        await run_cmd(workspace, "git", "add", "-A")
        await run_cmd(workspace, "git", "commit", "-m", "feat: Pi CEO build")
    return base


async def review_diff(workspace: str, run_cmd: RunCmd) -> tuple[str, str, int]:
    """Commit the build, then return (diff, --stat, diff_rc) over the range it added.

    `diff_rc` is the exit code of the `git diff` invocation, never conflated with
    `--stat`'s. A caller MUST check it before reading an empty `diff` as "no diff
    exists" — a failed `git diff` also produces empty stdout, and treating the two
    the same is a fail-open bypass of the whole review gate (Law 3: absence is
    never a pass, rules/truth-hacking.md).
    """
    base = await commit_build_output(workspace, run_cmd)
    diff_rc, diff_out, _ = await run_cmd(workspace, "git", "diff", base, "HEAD", "--")
    _, stat_out, _ = await run_cmd(workspace, "git", "diff", "--stat", base, "HEAD")
    return diff_out, stat_out, diff_rc


async def _head(workspace: str, run_cmd: RunCmd) -> str:
    try:
        _, out, _ = await run_cmd(workspace, "git", "rev-parse", "HEAD", timeout=10)
        return out.strip()
    except Exception as exc:  # noqa: BLE001
        log.warning("board-review could not read HEAD: %s", exc)
        return ""


async def check_head(workspace: str, run_cmd: RunCmd) -> GateResult:
    """Resolve HEAD and gate on it. An unreadable HEAD refuses."""
    return check(workspace, await _head(workspace, run_cmd))


async def allows_push(session, run_cmd: RunCmd, em) -> bool:
    """The whole gate as one call: resolve HEAD, check, report the verdict.

    Kept here rather than inlined in `_phase_push` so the push phase grows by one
    line, not ten — the repo's size ratchet is a real constraint and a gate is not
    a licence to fatten a 2000-line module.
    """
    if await _tree_dirty(session.workspace, run_cmd):
        em(session, "error",
           "  PUSH REFUSED — changes appeared after the review, so they are unreviewed")
        return False
    gate = await check_head(session.workspace, run_cmd)
    em(session, "error" if not gate.allowed else "system",
       f"  PUSH REFUSED — {gate.reason}" if not gate.allowed else f"  Board-review gate: {gate.reason}")
    return gate.allowed


async def write_for_head(
    workspace: str, run_cmd: RunCmd, verdict: str, session_id: str = "",
) -> str:
    """Bind `verdict` to the workspace's current HEAD. Returns the sha, or "".

    Never raises: a failed write leaves no receipt, and no receipt refuses the
    push. That is the safe direction to fail in.
    """
    head_sha = await _head(workspace, run_cmd)
    if not head_sha:
        return ""
    write_receipt(workspace, head_sha, verdict, session_id=session_id)
    return head_sha
