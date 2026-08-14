# RA-7216 slice 1 — metric contract and telemetry-gap audit

**Ticket:** RA-7216 — Pi-CEO: instrument verified outcomes per founder-review minute
**Date:** 14/08/2026
**Status:** slice 1 complete — read-only audit. No instrumentation written, no routing changed.
**Scope:** define the seven metrics, name the source field for each, classify what is missing, and state the first decision each metric enables. Baseline collection is slice 2.

---

## Method and its limits

Every claim below cites a file and line read in this checkout at `1e960d4`. Three limits apply and none is worked around:

1. **`.harness/` does not exist in this checkout.** It is runtime state and largely gitignored (`.gitignore:111-119` covers `agent-sdk-metrics/`, `llm-cost.jsonl`, `scan-results/`, `build-logs/`). Every local-fallback path in the scorer therefore returns empty here. Durable telemetry means Supabase, not `.harness/`.
2. **No Supabase credentials are present** (`NEXT_PUBLIC_SUPABASE_URL`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` all unset; no `.env`). Row counts could not be pulled, so **no baseline figure appears in this document**. Inventing one is what the ticket's first guardrail forbids.
3. **The canonical analysis is unreachable.** RA-7216 cites `/Users/phillmcgurk/2nd Brain/2nd Brain/Wiki/greg-isenberg-latest-video-system-gap-review-2026-08-13.md` — a Mac-local path, not in any repo. This audit was derived from the code instead. If that document sets definitions that differ from the ones below, it wins and this table needs revision.

---

## 1. The metric contract

`gate_checks` is the only table with a live writer that carries per-session outcome data. Its full column set (`supabase/migration.sql:145-192`) is:

`pipeline_id`, `session_id`, `spec_exists`, `plan_exists`, `build_complete`, `tests_passed`, `review_passed`, `all_passed`, `review_score`, `shipped`, `checked_at`, `session_started_at`, `push_timestamp`, `confidence`, `scope_adhered`, `files_modified`, `linear_state_after`.

Writers: `session_phases.py:1735`, `spec_pipeline/__init__.py:130`, `pipeline.py:636`, `pipeline.py:695`. Write path is `supabase_log.log_gate_check()` (`app/server/supabase_log.py:144-205`), fire-and-forget.

| # | Metric | Definition (proposed) | Source field | Verdict |
|---|---|---|---|---|
| 1 | **First-pass acceptance** | Sessions accepted by the founder with zero correction commits, ÷ sessions submitted | `linear_state_after`, `all_passed`, `review_score` | **PARTIAL** — acceptance is observable, "first-pass" is not. Nothing distinguishes an output accepted as-is from one accepted after the founder fixed it. |
| 2 | **Human correction count** | Commits authored by the founder on an agent branch after submission | — | **ABSENT** — no source. Nothing in the repo attributes post-submission commits. |
| 3 | **Rework ratio** | Sessions re-run for a ticket already submitted ÷ total sessions | `checkpoint.retry_count` (`supabase_log.py:255`) | **WRONG GRAIN** — `retry_count` counts *in-session* generator retries, not rework after a human rejected the output. The two are different failures and must not be conflated. |
| 4 | **24-hour rollback / escaped defects** | Shipped changes reverted or hot-fixed within 24 h of merge | — | **ABSENT** — see §2. This is the ticket's named guardrail and the scorer currently fabricates it. |
| 5 | **Trigger-to-accepted-outcome** | `accepted_at − session_started_at` | `session_started_at`, `push_timestamp` | **PARTIAL** — measures trigger-to-**push**, not trigger-to-**accepted**. There is no `accepted_at`. The gap is exactly the founder-review queue, which is the quantity of interest. |
| 6 | **Founder-review minutes** | Wall-clock minutes the founder spends reviewing agent output | — | **ABSENT, no proxy** — a repo-wide search for `review_minutes\|review_time\|founder_review\|human_minutes\|time_spent` across `*.py` and `*.sql` returns **zero matches**. Nothing measures human time anywhere. |
| 7 | **Cost per accepted outcome** | Session LLM spend ÷ accepted outcomes | `llm_costs` table | **PARTIAL, biased low** — see §3. The main build pipeline's spend never reaches the table. |

Diagnostic-only, per the ticket, and correctly already available: `files_modified`, `tokens_in`/`tokens_out` (`llm_costs`), PR counts. None of these may be promoted to a headline metric.

---

## 2. Three defects in the existing scorer

`scripts/zte_v2_score.py` is the closest existing instrument. Three of its behaviours must not be carried into RA-7216.

### 2.1 C1 fabricates the rollback measure — direct guardrail violation

`score_c1_deployment_success()` is documented as *"% of shipped builds surviving 24h without rollback"* (line 176). Its implementation (lines 180-183):

```python
# Approximate: use shipped count / total as proxy until rollback tracking lands
total = len(rows)
rate = len(shipped) / total if total else 0
```

`shipped/total` is the **ship rate**. It contains no information about what happened after the ship, so it cannot distinguish a clean deploy from one reverted twenty minutes later. RA-7216's guardrail names this exact construction: *"Do not … use shipped/total as a claimed 24-hour rollback measure."* The scorer has been reporting it as a survival rate since it was written. C4 carries the same admission at line 309: `rollback tracking not wired — use score as proxy`.

**No rollback telemetry exists to replace it.** Every apparent hit is a false positive, checked individually:

| Site | What it actually is |
|---|---|
| `pipeline.py:663` | A suggested command string (`"git revert HEAD  # revert last commit…"`) written into output. Not a record that anything was reverted. |
| `feedback_loop.py:205` | The words `"reverted"`, `"rollback"`, `"regression"` as **keywords in a text classifier**. Detects sentiment in prose, emits no event. |
| `autonomy.py:691,746` | Reverting a **Linear issue status** to Todo during orphan recovery. Unrelated to code. |
| `supervisor.py:76` | The word "scrollback". |

### 2.2 C2 has two different definitions depending on which source answers

The Supabase query filters `linear_state_after=not.is.null` (line 236), so rows lacking a Linear state are **excluded from the denominator entirely**. The JSONL fallback keeps them and counts them as accepted when `shipped` is true (line 215):

```python
if state in _ACCEPTED_STATES or (not state and (r.get("shipped") or r.get("push_ok"))):
```

Same metric name, two populations. The Supabase path silently drops unstated sessions; the local path counts them as successes. A number that changes meaning based on which backend responded cannot support a routing decision.

### 2.3 C2 counts "In Review" as accepted

`_ACCEPTED_STATES` includes `"in review"` (line 207), justified in the docstring as not double-penalising review latency. For RA-7216 this is disqualifying: **"In Review" is precisely the state where founder-review minutes are being consumed and acceptance is still unknown.** Counting it as accepted makes metrics 1, 5 and 7 unable to detect the problem the ticket exists to measure. RA-7216 needs a terminal state.

---

## 3. Cost telemetry covers the wrong half of the spend

Two independent cost paths exist and only one is durable.

**Durable path.** `swarm/budget_tracker.py:69-114` `record_cost()` writes both `.harness/llm-cost.jsonl` and the Supabase `llm_costs` table (`migration.sql:~330`: `ts, tenant_id, provider, role, model, cost_usd, tokens_in, tokens_out`). Its only callers are five sites in `app/server/provider_router.py` (402, 414, 445, 468, 487).

**Ephemeral path.** The main build pipeline runs through the Claude Agent SDK. `app/server/session_sdk.py` returns `cost_usd` per invocation (line 197) and appends to `.harness/agent-sdk-metrics/YYYY-MM-DD.jsonl` (line 208). A search of `session_sdk.py`, `session_phases.py` and `sessions.py` for `record_cost` or `budget_tracker` returns **no matches** — the SDK path never calls the durable writer.

Consequence: `.harness/agent-sdk-metrics/` is gitignored (`.gitignore:119`) and lives on ephemeral Railway disk, so **generator and evaluator spend — the dominant cost of a build — is lost on every redeploy and never reaches `llm_costs`.** Any "cost per accepted outcome" computed from `llm_costs` today would count only cheap-tier router calls and report a figure biased far low. The table comment itself scopes it to *"every cheap-tier LLM call"*.

---

## 4. Gaps ranked by what they block

| Rank | Gap | Blocks | Cheapest honest fix |
|---|---|---|---|
| 1 | No terminal acceptance event (`accepted_at`, `accepted_by`, `first_pass` bool) | Metrics 1, 3, 5, 7 — every ratio with "accepted" in it | Add columns to `gate_checks`; set from the Linear webhook on transition to a terminal state |
| 2 | No rollback / escaped-defect event | Metric 4; unblocks deleting the C1 proxy | New `outcome_events` table: `pipeline_id`, `event` (`reverted`/`hotfix`/`incident`), `occurred_at`, `detected_by` |
| 3 | Founder-review minutes unmeasured | Metric 6 — the ticket's denominator | Decide instrument first (§6). No column can be specced until then. |
| 4 | SDK spend not durable | Metric 7 | One `record_cost()` call in the SDK result path; `llm_costs` already has the schema |
| 5 | `retry_count` conflates in-session retry with post-review rework | Metric 3 | Separate counter keyed on ticket, not session |
| 6 | C2's dual definition and "In Review" acceptance | Metrics 1, 5 | Single definition, terminal states only |

---

## 5. Baseline

**Not established, and not estimated.** A 30-day baseline needs a `gate_checks` query this container cannot make (no credentials, §Method). What can be stated:

- The **shape** of a baseline query is known and cheap: `gate_checks` is indexed on `checked_at DESC` (`migration.sql:160`) and on `push_timestamp` and `linear_state_after` where non-null (lines 179, 192).
- Of the seven metrics, **at most three** can be baselined from existing history at all — 1 and 5 in degraded form, 7 biased low. Metrics 2, 4 and 6 have **no history to baseline**, because the events were never recorded. No amount of querying recovers them.
- Therefore the 30-day baseline cannot start until gaps 1, 2 and 4 are instrumented. **The baseline clock starts at instrumentation, not at ticket start.** Any plan assuming a 30-day baseline is already accruing is wrong by the length of that instrumentation work.

Missing-data states must be explicit rather than zero. `score_c2` already models this correctly with `needs_data` notes (lines 245, 269); `score_c1` does not — it returns `1, "no deployment data yet"`, a real score for absent data, which averages into the total as if measured.

---

## 6. First decision each metric enables

The ticket requires rejecting metrics that cannot change a decision. Applying that test:

| Metric | First decision it enables | Survives the test? |
|---|---|---|
| First-pass acceptance | Whether to raise the evaluator threshold, or route a task class to a stronger model | **Yes** |
| Human correction count | Which task classes to stop delegating | **Yes** |
| Rework ratio | Whether retry budget is buying completion or churn | **Yes** |
| 24-h rollback / escaped defects | Whether to keep or revert a routing change — the ticket's stated rollback trigger | **Yes — and nothing else can serve it** |
| Trigger-to-accepted-outcome | Whether the bottleneck is generation or the review queue | **Yes** |
| Founder-review minutes | The denominator of the ticket's headline metric | **Yes, if measurable — see below** |
| Cost per accepted outcome | Whether a cheaper model preserves acceptance | **Yes, once SDK spend is durable** |

**Founder-review minutes needs a decision before it can be specced.** There is no instrument and no proxy. Three options, none free:

- **(a) Timestamp arithmetic** — `push_timestamp` → terminal-state transition. Zero founder effort, but measures queue latency, not attention. A PR sitting unread overnight reads as eight hours of review.
- **(b) Explicit founder input** — a review-start/stop signal. Accurate, but adds founder burden to a metric whose purpose is reducing it, and the ticket's own rollback rule fires on increased review burden.
- **(c) Sampled self-report** — periodic estimate over a window. Cheap and honest about being an estimate; weak for detecting small changes.

**Recommendation: (a) as the instrumented default, clearly labelled `review_latency_minutes` rather than `review_minutes`, with (c) sampled monthly to calibrate the gap.** Naming it latency stops a queue-time figure being read as attention-time. This is a founder decision and is not taken here.

---

## 7. Out of scope, filed separately

`CLAUDE.md`'s Observability section states *"Declared but unwritten: `sessions`, …"*. This is stale: `sessions` has DDL at `supabase/migration.sql:43` and a live writer at `app/server/persistence.py:85` via `save_session_checkpoint()`. Filed as a separate ticket rather than corrected here — it is a docs defect, not a metric-contract question, and RA-7216 should not carry it.

---

## 8. What slice 2 needs

1. Founder decision on §6 (review-minutes instrument).
2. Confirmation that the Mac-local analysis doc agrees with §1, or its definitions in place of them.
3. Instrument gaps 1, 2 and 4 — additive columns plus one new table; no routing change, per the ticket's third guardrail.
4. Start the 30-day baseline **after** step 3 lands.
5. Delete `score_c1`'s `shipped/total` proxy once real rollback data exists. Until then it should return a `needs_data` state rather than a fabricated score.
