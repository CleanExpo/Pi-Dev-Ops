---
name: resume-from-handoff
description: Resume work from a session handoff. Reads the latest handoff, verifies current repo state against it, reconciles any drift, then continues the work from the documented pickup point without re-deriving old context. Verification is read-only and mandatory before any work resumes.
argument-hint: "[optional: path to a handoff file, pasted handoff, branch, or PR]"
disable-model-invocation: true
allowed-tools: Read, Grep, Glob, LS, Bash, Edit, Write
---

# /resume-from-handoff — Resume From a Session Handoff

Pick up work where a previous session left off, using a `session-handoff` report as the
source of truth. This is the read-side companion to `/session-handoff`.

**Hard rule — verify before you resume.** Phases 1–3 are read-only. Do not edit, commit,
push, deploy, run migrations, or run any mutating command until Phase 2 verification is
complete and the Phase 3 reconciliation is reported. If the repo has drifted materially
from the handoff, STOP and surface it before resuming.

## Input

The handoff to resume from:

```text
$ARGUMENTS
```

`$ARGUMENTS` may be: a path to a handoff file, pasted handoff text, or a branch / PR
reference. If empty, take the **newest handoff found by step 0a** across every handoff home,
and its paired **latest `.handoff-logs/handoff-<ts>.log`** when one exists; fall back to the
current conversation context. If none can be found, ask the user to provide the handoff and stop.

## Step 0 — Is the handoff still true? (read-only, before Phase 1)

On 07/11/2026 one resume run stopped 8 times and none came from product code: the newest
handoff sat in a folder this skill did not read, its "do not redo" review and receipt had
expired, founder-only steps had waited for days, and the release machine's GitHub link had
decayed. Step 0 checks those before any work. Report each result in the Phase 3 report.

**0a. Search every handoff home and take the newest.** A handoff in a git worktree is often
written outside the repo, because a tracked file would change the head a receipt is bound to.

| Home | Written when |
|---|---|
| `docs/session-handoffs/` | the repo folder may change |
| `.session-handoff/` | older sessions |
| `%APPDATA%/Claude/side-session-notes/<session>/` (`AppData/Roaming/Claude/side-session-notes/`) | side sessions, and any worktree whose head must not move |

Compare by the time written inside the file, then by file time. Name the file you chose and
the homes you searched; "no handoff found" is true only for the homes listed.

**0b. Expire old release evidence.** The release gate refuses a review or receipt older than
`MAX_AGE` (24 h, `skills/pr-release-gate/scripts/pr_release_gate.py`), measured from its own
`reviewed_at` / `issued_at`. For every "do not redo" item that is release evidence (review,
receipt, CI mirror run, publish): read its `valid until` time (session-handoff writes it), or
compute it as issued time + 24 h. If that time is past, mark the item **EXPIRED** and move it
out of "do not redo" into "redo first". Never skip an EXPIRED step because the handoff said so.

**0c. Ask GitHub before re-checking by hand.** For every PR or branch the handoff names, run
`gh pr view <n> --json state,mergedAt,closedAt,headRefOid` first. A PR already MERGED or CLOSED
by someone else ends that thread: report it, and do not re-verify or re-release it.

**0d. Probe the release machine.** On the machine that will push or publish (WSL on the PC):

```bash
for i in 1 2 3 4 5 6 7 8 9 10; do timeout 30 gh api rate_limit -q .resources.core.remaining >/dev/null 2>&1 && echo ok || echo FAIL; done | sort | uniq -c
time getent hosts api.github.com     # one name lookup; macOS: time dscacheutil -q host -a name api.github.com
```

Fewer than 10 of 10 OK, or a lookup over 2 s, is a machine fault: report it at the start,
before any release step, with the known fix (restart Tailscale on the PC for slow lookups;
restart WSL when `gh` drops connections). A restart that needs Phill becomes a founder card (0e).

**0e. List founder cards, oldest first.** Founder-only steps live on the source-of-truth board
(`jobs.json` on the Mini, the file `sot_hook.py board` / `show` reads). List the open ones:

```bash
ssh mini 'python3 -c "import json;J=json.load(open(\"/Volumes/Mini Mini 2T Storage/ops/jobs.json\"))[\"jobs\"];[print(j.get(\"created\",\"?\"),j[\"id\"],j.get(\"ask\") or j.get(\"title\")) for j in sorted(J,key=lambda j:str(j.get(\"created\",\"\"))) if str(j.get(\"owner\",\"\")).startswith(\"Phill\") and j.get(\"status\") in (\"todo\",\"open\",\"blocked\")]"'
```

When this session has a step refused for an agent (a permission or auto-mode denial, or a
step only Phill may take: credentials, merge, money, production), do not leave it in a
handoff line. Add it to that board as a card, under the claim protocol in
`skills/source-of-truth/SKILL.md` (take `jobs.json.lock`, back up first): `id`, `title`,
`status: "todo"`, `owner: "Phill (<why it is his>)"`, `tags: ["founder"]`, `ask` (one plain
sentence), `command` (the exact command), `file` (a link to the script or note), `created`
(ISO time), `source` (this session id). No new tool: `sot_hook.py show <id>` prints it.

## Phase 1 — Load the handoff (read-only)

Parse the handoff and extract:

- Summary of what was done
- Starting point
- Decisions locked + what shipped (branch, commits, files)
- Key files and their claimed status
- Running state
- Verification commands
- Deferred + open questions
- Pick up here (start-here steps, do-not-redo list, first command to run)
- Risk notes

If the input is not a recognisable handoff, say so and stop.

Also list `~/.local/state/gs/projects/<repo>/` (`<repo>` = the repo's top-level directory name).
Autonomous runs write their stage outputs there: design docs, plans, review reports and test
plans (`shipyard/references/autonomous-run-contract.md` §3). The newest file per stage is where
an interrupted run left off. Treat it as a lead to verify in Phase 2, not as fact.

## Phase 2 — Verify repo state against the handoff (read-only)

Confirm the repo actually matches what the handoff claims. Use read-only inspection:

```bash
git branch --show-current
git status --short
git log --oneline -n 12
git diff --stat
```

Check, claim by claim:

- **Branch** — is the handoff's branch present and checked out (or available)?
- **Commits** — do the claimed shipped commits exist? (`git cat-file -t <sha>`, `git log`)
- **Files** — do the "what shipped" / "key files" exist with the claimed status?
- **Working tree** — is it clean/dirty as the handoff's running state implies?
- **Open PR/issue** — still open/merged as stated? (`gh pr view` if available)

**Re-run the gate.** If `scripts/handoff-loop.sh` exists, run it — it is the same
definition-of-done gate `/session-handoff` ran on the way out, so the tree is proven green
on the way back in too. Compare its verdict against the log the handoff cited:

```bash
scripts/handoff-loop.sh            # exit 0 = READY to resume; non-zero = fix the named gate first
```

A non-zero exit is a **CANNOT RESUME** condition until the failing gate is fixed. Otherwise
re-run the handoff's own **verification commands** only if safe and read-only. Report
pass/fail honestly — never fake a result. Mark anything you could not check as `NOT CHECKED`.

## Phase 3 — Reconciliation report

Produce this before doing any work:

### Resume Reconciliation

- **Verdict:** MATCH / MINOR DRIFT / MATERIAL DRIFT / CANNOT RESUME
- **State vs handoff:** what matches, what changed since the handoff (new commits, moved branch, dirty tree, merged PR, deleted files)
- **Still-valid pickup instructions:** which "start here" steps still apply
- **Now-invalid / changed steps:** steps the drift has obsoleted, with why
- **Blockers:** anything that prevents a clean resume

Stop conditions (do NOT resume — surface and ask):

- The handoff's branch or claimed commits are missing
- The working tree has conflicting uncommitted changes
- The PR was already merged/closed in a way that obsoletes the work
- The "first command to run" would now be destructive or wrong

## Phase 4 — Resume the work

Only after Phase 3 reports MATCH or MINOR DRIFT (and you have stated your plan):

1. Skip everything in the handoff's **Do not redo** list.
2. Follow the **Start here** steps, adjusted for any minor drift noted in Phase 3.
3. Run the handoff's **First command to run** (or the corrected equivalent).
4. Respect the repo's normal gates — e.g. run `/judge` before building anything new that
   was not already approved in the handoff; honour `CLAUDE.md` / `AGENTS.md` boundaries.

Keep the user informed: state what you are resuming, what you are skipping, and why.

## Output

End with a short status:

- What was resumed
- First action taken
- Next checkpoint

`Resume complete (or paused). Next safe action: <one sentence>.`
