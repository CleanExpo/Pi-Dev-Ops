---
name: github-actions-quota-guard
description: Use before pushing a branch or opening/updating a PR on a GitHub Free PRIVATE repo, and whenever Actions jobs fail to start with "recent account payments have failed or your spending limit needs to be increased" or private-repo CI dies mid-month. Makes a pushed PR arrive already green (run the CI locally first, rebase clean), diagnoses free-tier Actions-minute exhaustion (NOT a real payment failure), stops futile reruns, and trims workflow minute-bloat.
---

# github-actions-quota-guard — green on arrival, lean on minutes

Hosted CI should **confirm** a green branch, never **discover** a red one. On a GitHub Free
**private** repo you get **2000 Actions minutes/month**; Windows bills **2×**, macOS **10×**.
Burn that up and every job dies in ~3s with *"the job was not started because recent account
payments have failed or your spending limit needs to be increased"* — a misleading message that
fires even with **no card on file**. This skill shifts verification left so you spend near-zero
minutes, and keeps workflows from torching the quota.

Human-merge-only and the review-binds-to-final-commit law are **not** owned here — they stay with
`pr-release-gate`. This skill gets the branch green and lean up to the push; that skill governs merge.

## When to invoke
Before any `git push` / `gh pr create` / `gh pr ready` on a private repo, or the moment you see
the quota-exhaustion annotation. Run the four steps in order; skip step 4 unless you saw the block.

## 1. Rebase clean — kill conflicts before they reach the PR
Fetch the base branch and confirm the branch merges without conflict.
- `git fetch origin <base>` then `git rebase origin/<base>` (or `git merge --no-commit --no-ff` as a dry probe, then abort).
- If conflicts: resolve them locally now; never push a branch that will show `CONFLICTING`.
- **Completion criterion:** branch is on top of latest `origin/<base>` with zero conflict markers.

## 2. Replay the CI locally — green before the push, not after
The workflow is the spec. Extract what each job actually runs and run it on your machine:
- List the commands: `grep -rEA2 'run:|runs-on:' .github/workflows/`.
- Run each `run:` step whose runner you can serve locally (Linux/macOS jobs, Node, lint, build, test).
- A job whose runner you **cannot** serve locally (e.g. `windows-latest` PowerShell on a Mac) is the
  one exception — note it as "unverified locally, covered by hosted run" rather than claiming green.
- Any failure → fix it and re-run **before** pushing. Ground the green claim in the actual output
  (see `proof-discipline`), not in "it should pass".
- **Completion criterion:** every locally-servable job passes locally, with the run output shown;
  each unservable job is explicitly named as such.

## 3. Trim the minute-bloat — stop the quota being torched
Run the audit and apply the fixes so future pushes cost little:
- `bash scripts/audit-workflows.sh <repo-dir>` — flags 2×/10× runners, double-run triggers,
  missing `concurrency`, absent `paths` filters, timer crons, matrix fan-out.
- Apply the safe conservation set to each workflow: add
  `concurrency: {group: ${{ github.workflow }}-${{ github.ref }}, cancel-in-progress: true}`;
  scope `push`/`pull_request` with `branches:` and `paths:`; drop or **gate** Windows/macOS jobs
  behind `if:`/path filters when a Linux job already covers the logic.
- **Completion criterion:** the audit re-run reports every workflow `clean`, or each remaining
  flag has a written justification.

## 4. Quota already exhausted — recognise it, don't fight it
If jobs die in ~3s with the payments/spending-limit annotation, the free monthly quota is spent.
Do **not** `gh run rerun` — every retry fails identically and wastes cycles. The levers, cheapest first:
1. **Wait for the monthly reset** — quota refills on the account's billing-cycle date. $0.
2. **Make the repo public** — public repos get unlimited free hosted minutes. $0, instant. But a
   **founder security call** for control-plane repos; scan history for secrets first.
3. **Self-hosted runner** — free minutes on your own machine; retarget `runs-on` to a self-hosted
   label. Needs a machine online (Windows job needs a Windows host).
4. **Raise spending limit / add card** — costs money; last resort, escalate as a spend decision.
- **Completion criterion:** the block is named as quota-exhaustion (not a payment failure), the
  chosen lever is stated, and no further blind reruns are issued.

## Verify the fix landed
After remediation, one clean push should show the workflow running to real completion (non-zero
duration, real logs) — or, if pre-reset, a documented lever chosen. A branch that is rebased,
locally-green, and lean is the deliverable this skill guarantees.
