# Review log and readiness dashboard

Upstream kept review history through its own logging binaries, which do not
exist here. The same history is a plain JSONL file per branch:

```
~/.local/state/gs/projects/<slug>/<branch>-reviews.jsonl
```

`<slug>` is the repo's top-level directory name; `<branch>` is the current branch
with `/` replaced by `-`. `/gs-plan-ceo-review`, `/gs-plan-eng-review` and
`/gs-autoplan` all append here, so each can show the others' results.

## Append one record

Build the line with `jq -nc` when a value may contain quotes; a plain `echo` is
fine for the fixed-shape records the skills specify.

```bash
SLUG=$(basename "$(git rev-parse --show-toplevel 2>/dev/null || pwd)"); BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null | tr '/' '-' || echo no-branch); GS_PROJ="$HOME/.local/state/gs/projects/$SLUG"; mkdir -p "$GS_PROJ"
echo '<one JSON object on one line>' >> "$GS_PROJ/$BRANCH-reviews.jsonl" && echo "LOGGED" || echo "NOT PERSISTED"
```

Only claim the record was saved when the command printed `LOGGED`.

## Read the history

```bash
SLUG=$(basename "$(git rev-parse --show-toplevel 2>/dev/null || pwd)"); BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null | tr '/' '-' || echo no-branch)
F="$HOME/.local/state/gs/projects/$SLUG/$BRANCH-reviews.jsonl"
[ -f "$F" ] && cat "$F" || echo "NO_REVIEW_HISTORY"
echo "---HEAD---"; git rev-parse --short HEAD 2>/dev/null
```

`NO_REVIEW_HISTORY` means no record exists at that path, not that no review ever
happened elsewhere. Say which path you read.

## Review Readiness Dashboard

Parse the history. Find the most recent entry for each skill (`plan-ceo-review`,
`plan-eng-review`, `codex-plan-review`, `autoplan-voices`). Ignore entries with
timestamps older than 7 days. For the Outside Voice row, show the most recent
`codex-plan-review` entry — this captures outside voices from both
/gs-plan-ceo-review and /gs-plan-eng-review.

**Source attribution:** If the most recent entry for a skill has a `"via"` field,
append it to the status label in parentheses, e.g. `plan-eng-review` with
`via:"autoplan"` shows as "CLEAR (PLAN via /gs-autoplan)".

Render each record using its recorded host, source, outside_provider,
outside_status and phase. Unknown model identity remains unknown.
Missing/disabled/skipped outside coverage is distinct from native completion.
Display a fresh `clean` result as CLEAR and `issues_open` as ISSUES OPEN. Show
missing, stale, disabled or unavailable results explicitly; none implies CLEAR.

```
+====================================================================+
|                    REVIEW READINESS DASHBOARD                       |
+====================================================================+
| Review          | Runs | Last Run            | Status    | Required |
|-----------------|------|---------------------|-----------|----------|
| Eng Review      |  1   | 2026-03-16 15:00    | CLEAR     | YES      |
| CEO Review      |  0   | —                   | —         | no       |
| Outside Voice   |  0   | —                   | —         | no       |
+--------------------------------------------------------------------+
| VERDICT: CLEARED — Eng Review passed                                |
+====================================================================+
```

**Review tiers:**
- **Eng Review (required by default):** The only review that gates shipping. Covers architecture, code quality, tests, performance.
- **CEO Review (optional):** Use your judgment. Recommend it for big product/business changes, new user-facing features, or scope decisions. Skip for bug fixes, refactors, infra, and cleanup.
- **Outside Voice (default-on):** Independent plan review after /gs-plan-ceo-review and /gs-plan-eng-review. Provider failure uses the native fallback and reports missing outside coverage. Never gates shipping.

**Verdict logic:**
- **CLEARED**: Eng Review has >= 1 `plan-eng-review` entry within 7 days with status "clean".
- **NOT CLEARED**: Eng Review missing, stale (>7 days), or has open issues.
- CEO and outside reviews are shown for context but never block shipping.

**Staleness detection:** These rows grade a plan file, not the repo tree; they keep
the 7-day freshness logic. For entries with a different `commit` than `---HEAD---`,
count elapsed commits: `git rev-list --count STORED_COMMIT..HEAD`. If that command
FAILS, grade UNKNOWN and treat as stale. Display: "Note: {skill} review from {date}
may be stale — {N} commits since review". If all reviews are current, do not
display staleness notes.

The design, DX, diff-review and adversarial rows of the upstream dashboard are
omitted: those gstack skills are not adopted here.
