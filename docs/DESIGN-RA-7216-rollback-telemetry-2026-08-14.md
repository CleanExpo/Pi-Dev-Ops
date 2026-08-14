# RA-7216 gap 2 — rollback and escaped-defect telemetry: design

**Ticket:** RA-7216 · **Status:** design only, nothing implemented
**Date:** 14/08/2026 · **Prerequisites merged:** slice 1 audit (`24f7767`), slice 2 acceptance events (`d25ff6e`)

Answers the question slice 2 deferred: *what, mechanically, counts as a rollback, and how does a revert on `main` get attributed back to the session that caused it?*

---

## 1. What this unblocks

C1 currently returns `needs_data` at every ship rate. That is honest but useless — it is the metric RA-7216 names as the rollback trigger for any routing change ("roll back any route that increases critical defects"). Until a rollback signal exists, no routing proposal can be evaluated, because the thing that would veto it cannot be measured.

C1 must not come back as a single blended number. The first version failed by presenting a proxy as a measurement; blending signals of different precision into one score would repeat that in a subtler form. This design keeps three signals separate.

---

## 2. Definitions

| Term | Definition | Not this |
|---|---|---|
| **Rollback** | A change Pi-CEO shipped to a default branch is later reverted on that branch. | A revert on a feature branch; a reverted PR that never merged. |
| **Escaped defect** | A shipped change is accepted, then something downstream proves it wrong: the issue is reopened, or CI on the default branch breaks immediately after the merge. | A defect caught by the evaluator or by review before merge — that is the gate working. |
| **Time-to-rollback** | `reverted_at − merged_at`, recorded in full. | A stored `within_24h` boolean. The 24-hour threshold is a **read-time** decision, exactly as review latency is derived rather than stored. |

Rollback and escaped defect are deliberately separate. A revert is a strong, near-unambiguous signal; a reopen or a red build is weaker and noisier. Averaging them produces a number no decision can rest on.

---

## 3. Signal inventory

### Already arriving, currently discarded

| Signal | Where it arrives | What happens today |
|---|---|---|
| `push` to any branch, with `commits[].message`, `head_commit`, `before`/`after` | `routes/webhooks.py:105` (`x-github-event: push`) | `parse_github_event` (`webhook.py:30`) extracts **only** `repo_url` and `ref`. Commit messages are parsed away. |
| `pull_request` events incl. `closed` + `merged: true` + `merge_commit_sha` | same route | `parse_github_event` extracts `action` and head `ref` only. `merge_commit_sha` is discarded. |
| `workflow_run` failure on the default branch | `_handle_workflow_run` (RA-847) | Files a Linear ticket and sends Telegram. **Persists no row** — the event exists as an alert, never as data. |
| Linear terminal transition | `parse_linear_event` → `record_acceptance` (shipped in slice 2) | Stamps `accepted_at`. A **second** terminal transition is silently ignored by the `accepted_at=is.null` filter. |

### Known at ship time and thrown away

`_phase_push` (`session_phases.py:1484-1572`) computes `branch_name = f"pidev/auto-{sid_short}"`, opens a PR, and reads `pr_number` (line 1557) and `pr_url` (line 1556). `session.pr_url` is assigned (line 1561); **`pr_number` is a local variable that dies with the function.** Neither reaches `gate_checks`, and `save_session_checkpoint`'s `checkpoint` JSONB does not carry them either. `sessions.branch` is persisted, but a branch name alone cannot identify a commit on `main`.

### Absent entirely

The **merge commit SHA**. It does not exist at push time — the PR is opened, not merged — so it can only be captured later, from the PR-merged event.

---

## 4. The attribution gap is the keystone

A revert commit on `main` says *"This reverts commit `<sha>`."* To turn that into a rollback attributed to a session, `<sha>` must match something on a `gate_checks` row. **No row holds any commit SHA, PR number, or branch.** Every detector below fails on this alone, regardless of how good its pattern matching is.

This is structurally the same defect as the missing `linear_issue_id` join key that slice 2 fixed: the event carries an identifier the row cannot be looked up by. It must be closed first, and it needs two writes because the identity is only complete after the merge:

```
ship time      →  gate_checks.pr_number, gate_checks.head_branch     (known at _phase_push)
PR merged      →  gate_checks.merge_sha, gate_checks.merged_at       (matched by pr_number)
revert on main →  outcome_events row, matched by merge_sha           (the detection)
```

Each link is a webhook that already arrives at `/api/webhook` today. No polling, no new integration.

---

## 5. Detectors, with honest precision

### A. Revert commit on the default branch — *primary*

Match `head_commit.message` (and each entry in `commits[]`) against `^Revert "` plus a body line `This reverts commit ([0-9a-f]{7,40})`. Both the GitHub revert button and `git revert` emit this shape. Extract the SHA, match against `gate_checks.merge_sha`.

- **Precision: high.** The reverted SHA is stated explicitly; no inference.
- **Recall: partial.** Misses a rollback performed as a forward fix, a force-push, or a rebase that drops the commit. Those produce no revert commit and are invisible by construction.
- **Failure mode to accept:** a revert of a revert (re-landing) reads as a second rollback. Detect by checking whether the target SHA is itself a recorded revert, and record it as `re_land` rather than `revert`.

### B. Reopen after acceptance — *secondary*

Slice 2 records the **first** terminal transition and ignores later ones. A subsequent transition on an issue that already has `accepted_at` is a reopen — rework, and often an escaped defect.

Blocked on a detail worth naming: `_patch` sends `Prefer: return=minimal`, and PostgREST returns 204 whether it updated one row or none. `record_acceptance` therefore **cannot currently tell** whether its filter matched. Switching that one call to `return=representation` makes "the filter matched nothing because `accepted_at` was already set" observable, which is exactly the reopen signal — no new webhook required.

- **Precision: medium-high.** A reopen can also mean scope grew.
- **Recall:** only issues Pi-CEO shipped against.

### C. Default-branch CI failure shortly after merge — *diagnostic only*

`_handle_workflow_run` already detects this. Adding one durable row turns an alert into data.

- **Precision: low-medium.** Flaky tests and infrastructure failures are indistinguishable from real breakage without further work.
- **Use:** diagnostic context beside A, never a component of a headline score. Same status RA-7216 assigns to PR and token counts.

### D. Hotfix proximity — *rejected*

"A push to `main` within 24h touching the same files." Requires the modified-file **list**; `gate_checks.files_modified` stores only a count. It would also fire on ordinary iteration. Rejected: high false-positive rate, and it cannot change a decision correctly, which is RA-7216's own test for keeping a metric.

---

## 6. Proposed shape

### Schema — additive, idempotent, `supabase/migration.sql`

```sql
-- Attribution keys (the keystone). Written at ship time and at PR-merge time.
ALTER TABLE gate_checks ADD COLUMN IF NOT EXISTS pr_number   INTEGER;
ALTER TABLE gate_checks ADD COLUMN IF NOT EXISTS head_branch TEXT;
ALTER TABLE gate_checks ADD COLUMN IF NOT EXISTS merge_sha   TEXT;
ALTER TABLE gate_checks ADD COLUMN IF NOT EXISTS merged_at   TIMESTAMPTZ;

-- Outcome events. One row per observed post-merge event; never overwritten.
CREATE TABLE IF NOT EXISTS outcome_events (
  id          BIGSERIAL   PRIMARY KEY,
  kind        TEXT        NOT NULL,   -- revert | re_land | reopen | ci_fail_on_main
  gate_check_id BIGINT,               -- NULL when unattributable (recorded, not dropped)
  repo_name   TEXT        NOT NULL,
  merge_sha   TEXT,
  event_sha   TEXT,
  occurred_at TIMESTAMPTZ NOT NULL,
  detected_by TEXT        NOT NULL,   -- which detector fired
  raw_ref     TEXT
);
```

`gate_check_id` is nullable **on purpose**. An unattributable revert is a real event and must be counted as a known-unknown; dropping it would rebuild the survivorship bias slice 2 removed, in a new place.

### Code

1. `parse_github_event` gains commit messages and `merge_commit_sha` to its output. It currently returns only `repo_url`/`ref`/`action`.
2. The GitHub branch of the webhook route handles revert and PR-merged **before session creation** — the same ordering slice 2 used for `issue_completed`. Without it a revert push spawns a build session, which is how recursive self-modification produced 43 zombie branches (RA-1182).
3. `_log_ship_gate_check` writes `pr_number` and `head_branch`; `_phase_push` must return `pr_number` rather than dropping it.
4. `record_merge()` and `record_outcome_event()` in `supabase_log.py`, fire-and-forget per module doctrine.
5. C1 reads `outcome_events` where `kind='revert'`, attributed, against merged rows in the window — and continues to report `needs_data` until the denominator clears a sample floor, as C2 now does.

### A blind spot that must be stated, not silently accepted

`routes/webhooks.py:141` skips all webhook handling for `CleanExpo/Pi-Dev-Ops` itself (RA-1182, blocking self-modification). That guard sits **before** any new detector would run, so **Pi-CEO's own reverts would never be recorded**. Since Pi-CEO ships to its own repo constantly, that is a large hole in exactly the repo with the most data. The fix is to run detection before the self-modification skip and keep the skip for *session creation only* — recording an event is not self-modification. Worth calling out because the obvious implementation gets this wrong.

---

## 7. What this still cannot measure

Stated plainly so the baseline is not read as more complete than it is:

- **Silent defects.** A change that is wrong but never reverted, never reopened and never breaks CI is invisible. No passive signal detects it.
- **Forward fixes.** The common real-world response to a bad merge is another commit, not a revert. Detector A sees nothing.
- **Non-Pi-CEO changes.** Only work shipped through the auto-PR path carries attribution keys.

Therefore C1 should be labelled **`observed_rollback_rate`**, not "% surviving 24h". The first is what is measured; the second is a claim about everything that shipped, and it would be false for the same reason `shipped/total` was.

---

## 8. Verification plan

1. **Unit** — synthetic `push` payloads: a revert with a full SHA, a short SHA, a revert-of-revert, a `Revert "` in a non-default-branch push (must not fire), a message merely containing the word "revert" (must not fire).
2. **Attribution** — a PR-merged event stamps `merge_sha`; a later revert of that SHA produces an attributed `outcome_events` row with a correct `occurred_at − merged_at`.
3. **Unattributable path** — a revert of a SHA with no matching row still writes a row with `gate_check_id IS NULL`.
4. **Ordering** — a revert push does **not** create a build session.
5. **Mutation controls** — remove the SHA extraction; remove the pre-session ordering; remove the self-modification carve-out. Each must fail a distinct test.
6. **Backfill: none.** No history exists to reconstruct; inventing it is forbidden by the ticket's first guardrail. The rollback baseline starts at deploy.

---

## 9. Decision — unattributable reverts: **(b), decided 14/08/2026**

**How should an unattributable revert count?** It is recorded either way, but C1's denominator changes:

- (a) Exclude — measure only what can be attributed. Clean, and understates the true rate.
- **(b) Separate `unattributed` count shown beside C1, never folded in. ← CHOSEN (founder, 14/08/2026)**
- (c) Include in the denominator — treats an unknown as a Pi-CEO rollback. Rejected: that is inventing history.

### What (b) obliges the implementation to do

Recording the row is not enough — (a) and (b) both record it. The difference is entirely in what is reported, so the obligations are concrete:

1. **C1 emits two numbers, never one.** `observed_rollback_rate` over attributed reverts only, plus `unattributed_reverts` as a raw count beside it. They are never summed, averaged, or reconciled into a single score. A caller that reads only the rate is reading a partial figure by design, which is why the count sits next to it rather than in a footnote.
2. **The unattributed count is a first-class signal, not a footnote.** A rising count means attribution coverage is degrading — keys are not being written, or reverts are landing on changes Pi-CEO did not ship. That is worth acting on independently of the rate itself.
3. **Coverage is surfaced, not inferred.** Report `attributed / (attributed + unattributed)` as an explicit **attribution coverage** figure. Without it, a healthy-looking `observed_rollback_rate` computed over three attributed reverts while forty went unattributed reads as reassurance when it is the opposite.
4. **Low coverage degrades the rate to `needs_data`.** If coverage falls below a floor, `observed_rollback_rate` must report `needs_data` rather than a confident number over a small attributed slice — the same discipline as C2's sample floor. Starting threshold: coverage < 50%, or fewer than 5 attributed reverts. Both to be retuned once the baseline exists; neither is derived.

Point 4 is the one that makes (b) meaningfully different from (a) in practice. Without it, (b) is just (a) with a number printed alongside that nothing ever reads.

Everything else in this document follows from prior decisions or from the code.

---

## 10. Sequence

1. ~~Founder decision on §9~~ — **done 14/08/2026, option (b).**
2. Attribution keys (§6 schema + code 1–3). No detector yet — keys must accrue **before** detection is useful, since a revert can only match rows that already carry a `merge_sha`.
3. Detector A + the pre-session ordering + the self-modification carve-out.
4. Detector B (the one-line `Prefer` change plus a reopen event).
5. Detector C as a diagnostic row.
6. Re-point C1 as `observed_rollback_rate` + `unattributed_reverts` + attribution coverage, with the §9.4 floors.

Steps 2 and 3 are separately shippable. Nothing here changes routing, per the ticket's third guardrail.

**Implementation is not authorised by the §9 decision alone.** Per the repo's Judge Gate, building follows a separate explicit approval; §9 settled a design question, not the go-ahead.
