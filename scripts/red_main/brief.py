"""The brief a red-main fix lane runs with (RA-8174).

The lane is a `claude -p` session, so the brief carries the full NEVER list and every
gate. The watcher never opens PRs or posts review status itself: those are gated
actions the lane takes through pr-release-gate.
"""
from __future__ import annotations

RUNTIME = "/Volumes/Storage Unit/Application-Data/nexus-mesh/pdo-runtime/scripts/red_main_watch.py"


def watch_cmd(args: str, on_board_host: bool) -> str:
    """The board lives on the Mini; a lane elsewhere reaches it over ssh (args use single quotes only)."""
    cmd = f"python3 '{RUNTIME}' {args}"
    return cmd if on_board_host else f'ssh mini "{cmd}"'


def _failing_lines(card: dict) -> str:
    rows = card.get("failing") or []
    return "\n".join(f"- {r.get('name')} at {r.get('sha')}, failing since {r.get('since')}: {r.get('url')}"
                     for r in rows) or "- (see the card)"


def build(card: dict, *, pr_only: bool = False, on_board_host: bool = True) -> str:
    repo, branch, fix = card["repo"], card.get("branch", "main"), card["fix_branch"]
    head = (f"Red-main follow-up lane for {repo}: branch {fix} was pushed but has no PR. "
            "Open the PR now through the release gate (step 4), then continue from step 5.\n\n"
            if pr_only else "")
    return f"""{head}Red-main fix lane (RA-8174), board card {card['id']} in /Volumes/Mini Mini 2T Storage/ops/jobs.json.
Repo {repo}: default branch {branch} is RED. Failing workflows (latest completed run on {branch}):
{_failing_lines(card)}

You are the single owner of this red main. Every other job waits for you.

STEPS
1. Unset every GIT_CONFIG_* variable before any git or gh call. Fresh clone of {repo} into "$PWD/repo" (this lane dir).
2. Find or file the Linear issue for this red main (search first; file Urgent if none). Then claim the card:
   {watch_cmd(f"claim {repo} <LINEAR-ID> '<agent> on <machine>'", on_board_host)}
3. Find the root cause from the failing job logs (gh run view --log-failed). Fix it on branch {fix} with tests.
   If the cause is a missing secret, credential, billing or permission, do not touch it: write the exact blocker on
   the card note and in RESULT.md, and stop.
4. Within 10 minutes of the first push of {fix}, open the PR (Refs the Linear issue, five-whys in the body) through
   the pr-release-gate skill. The watcher relaunches a lane for any pushed {fix} with no PR after 10 minutes.
   If CodeRabbit is rate-limited, do not wait for it: take the Codex review lane and the legitimate
   nexus/release-receipt path (gate issue + publish with --primary-agent claude). Never post a status by hand.
5. Follow the repo's merge policy. Pi-Dev-Ops: stop at ready-for-review, a human merges. Others: merge only where
   the repo's own automation and gates allow it. Never --admin.
6. Jobs parked on this red main resume on their own when {branch} is green. To park another job on it:
   {watch_cmd(f"park <JOB-ID> {repo}", on_board_host)}

NEVER: secrets, billing, permissions, production deploys, rollbacks or database operations (fix the workflow,
never run it against production), force-push, --no-verify, edit or disable hooks or the release gate, fake
receipts, paid APIs beyond the subscription plans, kill Phill's desktop sessions.

LOG each step with an AEST time in ./job.log. FINISH with ./RESULT.md in plain English.
"""
