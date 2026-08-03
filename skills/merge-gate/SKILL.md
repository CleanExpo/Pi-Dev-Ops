---
name: merge-gate
description: Use before opening any PR, pushing to a shared branch, or merging in this estate — where automation force-readies draft PRs and squash-merges them on green within minutes, so opening a PR is authorising its merge. Fires when about to run gh pr create / gh pr ready / gh pr merge, or push to a deploy-on-push branch.
allowed-tools: Read, Grep, Glob, Bash
---

# merge-gate — opening a PR here *is* merging it

The estate runs an autonomous **auto-merge** (an automation acting as the `CleanExpo`
account) that **force-readies draft PRs and squash-merges them on green, within minutes of
open**. `--draft` does **not** hold it; the "explicit merge authority" gate does **not** stop
it. So the only control point you actually own is **before the PR opens**. This skill moves the
full quality bar to that point and turns a hazard into a safe fast-ship — *when* the standard is
met first.

Verified 2026-07-10: draft PRs #545 and #546 were both flipped to ready by `CleanExpo` and
merged on green; #545 (spec-only) merged in the gap **between** opening the draft and pushing the
code, shipping a half-PR and stranding the implementation. Full worked example + the exact
detection/recovery commands are in [`references/playbook.md`](references/playbook.md) — read it
before you diagnose a premature or truncated merge.

## The Iron Law

```
NO PR OPENS UNTIL THE BRANCH IS COMPLETE AND GREEN.
```

Treat every `gh pr create` as `gh pr merge`. If the branch is not the whole, verified change at
the moment you open it, assume it ships exactly as-is.

## Enforce LEFT — the pre-open gate (MANDATORY)

Make a todo per item. **Every one must be true before `gh pr create`** (or before any push to a
deploy-on-push branch):

1. **Whole** — every commit of the change is pushed; nothing staged, stashed, or uncommitted
   belongs in it. `git status` clean, `git stash list` empty (see [[hermes-agent-autogit-hazard]]),
   `git log origin/<branch>` shows the *complete* change. *Never open, then push more.*
2. **Green on the exact pushed tip** — the repo's definition-of-done gates pass locally on the
   commit you are about to open: type-check, lint, tests, build, **and every project guard**
   (CARSI: `check:iicrc-terminology`, `check:designations`, `check:cec`). Paste real output; a
   subagent's "green" is unconfirmed until you re-ran it.
3. **Dark-by-default** — any behaviour change ships behind a flag defaulting **off**; DDL /
   destructive / prod-affecting changes are founder-gated or excluded. The test: *if this
   auto-merges in 90 seconds, is it harmless?* If not, it is not ready to open.
4. **Atomic** — spec + implementation land together unless a spec-only merge is intended.
   Do not open a branch that a mid-push merge could truncate.
5. **Standards clean** — brand/licence rules hold ([[no-coach8-in-branding]], AU-English,
   [[carsi-designations-not-iicrc]], [[carsi-cec-requires-iicrc-approval]]); no secrets; no
   unrelated files.
6. **Authority reconciled** — because open ≈ merge, settle merge authority *before* opening.
   If the auto-merge will fire regardless, tell the founder plainly and rely on #3 (flag-off) as
   the safety net — never on the draft flag or the authority gate holding.

**Completion criterion:** all six true, output pasted → push the final tip → `gh pr create`.
Any one false → do not open; fix first.

## After the merge — never trust it

The merge is not the finish line; verification is. Confirm on `origin/main` that the **full
intended tree** landed (not a truncated subset — #545's failure mode), the flag default is still
**off**, and you know which deploy the merge triggered (CARSI `main = prod` on DO deploy-on-push).
Commands in [`references/playbook.md`](references/playbook.md).

## When it goes wrong

Premature or truncated merge, stranded implementation, orphaned autostash → the recovery recipe
(fresh branch off the moved `origin/main`, `git checkout <old-branch> -- <files>`, new PR;
GitHub diffs trees so an already-squashed prefix shows no dup) is in
[`references/playbook.md`](references/playbook.md). To stop the automation for sustained work,
see the pause options there.

## Connection

- **nexus** — this skill is the ship-safety clause of nexus **G7 (Deliver)**: any run step that
  opens a PR, pushes to a shared/deploy branch, or merges passes merge-gate first.
- **Hands off, does not duplicate** — the *idea→ship lifecycle* stays with `ship-chain` /
  `ship-it` / `ship-release`; the *definition-of-done gate run* stays with `session-handoff`.
  merge-gate owns only the **git-merge boundary** and the auto-merge threat around it.
- **Memory** — [[hermes-agent-autogit-hazard]] (the automation's full behaviour),
  [[agent-pr-merge-needs-explicit-authority]], [[merge-race-fixforward-window]],
  [[stacked-pr-train-merge-order-hazard]], [[carsi-preserve-sha-use-tag]].
