# Jev Platform — slice 1 plan (shadow mode), rev 2

Status: DRAFT rev 3 (see the Rev 3 section at the end, which governs) · 29/09/2026 · branch `feat/jev-constitution-eval`

Rev 1 went to an independent reviewer (Codex, OpenAI Pro plan) and was rejected at 56/100, "DO
NOT APPROVE BUILD" (`docs/plans/jev-platform/judge-r1.md`). Every point is addressed below; the
**R1-n** tags map to its findings.

## Goal

Given an action an agent proposes, ask TypeSafe Jev whether the action complies with Unite-Group
Nexus Constitution rules. Return a **shadow recommendation** with rule citations. Slice 1 is a
library, a CLI and a calibration tool. It is structurally separate from execution: nothing in
`app/` or `swarm/` imports it.

## Sources it binds to (Unite-Group `origin/main` 8eb9491b8)

- **The Constitution:** 538 verbatim rules in `evals/jev_constitution/questions.json` (checked by
  `quotes.py`, 538/538).
- **The Waterline** (EPIC-000:263-281): an action takes the highest class of anything it touches,
  and ambiguity goes up a class. Evidence and model consensus never lower a class. Class 3 is a
  founder action.
- **The NorthStar rule:** never fabricate. An outage is reported as `signal_unavailable`, never as
  compliant.
- **The AAA ladder** (`ground-truth-standard.md`): A = inference, AA = proven but not bound,
  AAA = verified and bound to the exact SHA. The overall rating is the minimum, never rounded up.
- **The TypeSafe guidance:** one Noul per rule, combined any-of in code. Thresholds are set on our
  own data. Noul ≈ 0.5 means uncertain. Uncertain cases go to a person. 64k tokens per request.

## Verdicts: no "allow" exists in slice 1 (R1-1, R1-4)

The shadow recommendation is exactly one of the following:

- `refuse`: a rule's Noul is below 0.1 **and** that rule has a frozen, validated threshold.
- `escalate`: every other adverse or uncertain path, with its reasons listed.
- `no_objection_on_evaluated_rules`: every evaluated rule passed its threshold. This always
  states `evaluated k of 538` and `unevaluated 538-k`. It is never rendered as "allow" or
  "compliant".

When several reasons apply, `refuse` beats `escalate`, which beats `no_objection`. The output
always carries `mode: "shadow"`.

## Coverage and class (R1-1, R1-2)

- **Rule selection.** The rule list must be non-empty and every id must exist, or the result is
  `escalate: invalid_selection`. Rules that are not calibrated escalate, with the reason
  `uncalibrated` naming them. They are never silently dropped.
- **Class.** `--class` is a *claimed* class. The engine never lowers it.
  - Class 3, or no class given → `escalate: founder_class`.
  - A claimed class 0-2 is reported as `class: <n> (claimed, unverified)`.
  - Deterministic class inference is out of scope for this slice (it is RA ticket work).

## Strict response validation (R1-3)

The complete set of Jev answers is validated before any policy is applied. The result is
`escalate: signal_unavailable` when any of these hold:

- the HTTP status is not 200
- a request times out
- a 429 is still failing after two retries that honour `retry-after`
- an answer is missing or duplicated, or its rule id doesn't match the question
- a value is not a finite float in [0, 1] (so NaN fails closed)
- any chunk of a batched request fails

A partial batch never produces `no_objection`.

## Calibration: frozen, then validated (R1-4, R1-5)

The tool is `python -m jev_platform calibrate --rule <id>`.

1. **Split.** Cases are split deterministically, by sha256 of the scenario text, into calibration
   (50%) and validation (50%). This is a limitation: the cases don't record their scenario
   family, so the split is by case, not by family. It is disclosed in every calibration record.
2. **Score.** Jev scores every case, and each case's Noul is stored in
   `jev_platform/calibration/<rule>.jsonl` (case hash, label, class, Noul).
3. **Freeze.** The threshold is frozen on the calibration half: the lowest of
   {0.5, 0.7, 0.9, 0.95} with 0 missed violations. If none qualifies, the status is
   `no_qualifying_threshold` and the rule escalates.
4. **Validate.** The frozen threshold is run through the actual decision policy on the validation
   half. The record reports, each with its denominator:
   - missed violations out of the validation violation cases
   - escalations out of the compliant cases (the burden on the reviewer)
   - abstentions

   Zero observed misses is reported as "0 of N observed", never as "zero risk".
5. **Stale records.** A calibration record binds these:
   - the rule text hash
   - the question and criteria hash
   - the model string Jev returns
   - the policy version
   - the eval commit SHA

   Any mismatch at decision time → `escalate: stale_calibration`.

## Evidence ratings (R1-3 of the review)

The evidence is reported separately for each part:

- **The measurement artifact:**
  - AAA when the calibration record is committed and bound to its SHA
  - AA when it is valid but not bound
  - FAIL when it is absent
- **The compliance judgment:** always **A**, because it is model inference with labels from two
  models agreeing. It is never promoted.
- **The recommendation's overall rating:** the minimum of the two, so it is at most **A**.

## Cost, privacy and bounds (R1-4)

- **Hard caps:** a maximum number of rules per decision (default 25), a maximum number of cases
  per calibration run (default 1,500), and 2 retries. `calibrate` prints its estimated tokens and
  cost first. At Jev's $0.042 per million tokens, one rule costs under US$0.10.
- **Privacy:** the action text is not written to disk unless `--record` is passed. Calibration
  files hold only synthetic cases.
- **Key:** injected at run time with `vercel env run`. It is never written to disk and never
  logged.

## Tests (offline, fake `post`, each guard mutation-checked)

- empty, unknown or duplicate rule ids
- understated or missing class, and Class 3
- non-200, timeout, a 429 that keeps failing, a missing answer, a duplicate answer, NaN,
  out-of-range values, a failing chunk
- a stale calibration record, a rule with no qualifying threshold, an uncalibrated rule
- verdict precedence
- no output ever contains `allow`
- the calibration split is deterministic and disjoint, and the threshold is frozen on the
  calibration half only
- the rating is at most A for a compliance judgment

## Non-goals

- Wiring into `app/server/tool_gate.py`. Live use adds a metered transport. Under the founder's
  rule a new cost is allowed only for named client revenue, and `provider_policy.py` refuses
  metered lanes today. That is a founder decision, to be filed as a ticket.
- Relevance pre-filtering, class inference, a UI.

## Finish line (Done contract v5)

- The offline tests pass, and each guard has a mutant that fails a test.
- `calibrate --rule ch3-4-27` runs live (key from Vercel) and commits
  `jev_platform/calibration/ch3-4-27.json` with the split, the frozen threshold, the validation
  denominators and the bindings.
- A shadow decision on a planted violation returns `refuse` or `escalate`, is recorded as a
  **transport smoke test only**, and makes no calibration claim.
- `provider_policy.py` is unchanged from origin/main, and nothing in `app/` or `swarm/` imports
  `jev_platform`.

---

## Rev 3 — answers to round 2 (`judge-r2.md`, 76/100). Where rev 2 and rev 3 conflict, rev 3 governs.

**Recommendation-level verdict (R2-1).** Class inference is out of scope, so no class claim can be
verified. Every slice-1 recommendation is therefore at least `escalate: class_unverified`, and
`no_objection_on_evaluated_rules` is unreachable at the recommendation level. It can still appear
**per rule**, in the rule findings. Duplicate, empty or unknown rule ids → `escalate: invalid_selection`.
A missing or invalid class, or class 3 → `escalate: founder_class`. The value slice 1 delivers is the
per-rule findings: each rule's Noul, threshold, state and citation. It does not deliver a clearance.

**Rule-level comparison (R2-1).** A rule *passes* only when **both** hold:
- `noul >= threshold`
- `noul` is outside the abstain interval: it is not the case that 0.40 <= `noul` <= 0.60

A rule *fails* when `noul < 0.10` and the rule's state is `provisional`. A failing rule makes the
recommendation `refuse`. Everything else about the rule is `uncertain`, which contributes `escalate`.

**Calibration states (R2-1, R2-2).**

| State | When | Effect |
|---|---|---|
| `absent` | no record | escalate |
| `corrupt` | the schema check fails, or the stored case hashes do not reproduce the dataset | escalate |
| `no_qualifying_threshold` | no candidate threshold gives 0 misses on the calibration half | escalate |
| `failed_validation` | any validation miss, or fewer than 50 violation cases or 50 compliant cases in validation | escalate |
| `stale` | any bound hash differs, or the record is more than 30 days old | escalate |
| `provisional` | everything above passes | the rule is usable for per-rule findings |

`provisional` is the **highest state reachable in slice 1**. The labels come from two models
agreeing, the split is by case rather than by scenario family, and `jev-latest` is a mutable alias.
Each record states all three limitations. The record binds:
- the full scoring configuration: questions, criteria, thresholds, abstain band and policy version
- the model string Jev returns
- the dataset hash and the eval commit SHA

The word "validated" is never used.

**Counters (R2-2).** Calibration computes its own metrics from the stored per-case Nouls. The
counters are **disjoint**: `pass_ok + missed + false_alarm + abstain + fail_ok = n`. A test enforces
this. A violation case that the policy lets pass counts as missed, measured at the rule level.
Recommendation-level blanket escalation never counts as a detection. (On the existing
`first-result.json`: its counters come from the earlier harness and overlap. The platform does not
reuse them.)

**Evidence (R2-3).** Evidence is rated in four parts:
- **measurement artifact:**
  - **AAA** only when `python -m jev_platform verify-calibration --rule <id>` exits 0 at the exact
    commit. That command recomputes every counter from the stored per-case scores and re-hashes
    the dataset and configuration. Its receipt is `<cmd> (exit 0) @ <sha>`.
  - AA: valid but not bound.
  - FAIL: absent.
- **compliance judgment:** A at most; FAIL when Jev's signal is unavailable.
- **classification:** FAIL (unverified in slice 1).
- **coverage:** FAIL when any of the 538 rules is unevaluated.

The overall rating is the minimum of the four, so a slice-1 recommendation reports **FAIL**. That
is honest, and it is the correct state for shadow mode.

**Spend gate, enforced (R2-4).** A request is refused *before sending* when:
- its estimated input tokens (characters ÷ 3, rounded up) exceed 60,000
- the run's cumulative estimated cost would exceed `--max-usd` (default US$0.50), counting retries
- the elapsed time would pass `--max-seconds` (default 900)

Retries are capped at 2 and count against the budget. A breach → `escalate: budget_exhausted`, and
nothing further is sent.

**Privacy (R2-4).** Before any outbound request, and before any record or error is stored, the text
is redacted:
- emails
- phone numbers
- runs of 12 or more digits
- things that look like keys (`sk-`, `ts-`, `ghp_`, 32+ hex)
- URLs with query strings

Records hold the action's sha256 and its *redacted* text only. Errors store the HTTP status and a
code, never a response body.

**Live finish line (R2-4).** The founder authorised using the Vercel-held TypeSafe key for Jev
testing on 29/09/2026: "The keys are stored in Vercel.. What more do you require?". This is class D
evidence and covers *eval and shadow calibration only*. It does not cover live wiring, which stays
a founder decision. The live criterion runs behind an explicit `--live` flag and the US$0.50 cap.

**Added tests (R2-4).**
- duplicate ids
- a held-out validation failure → `failed_validation`
- zero violation cases in validation → `failed_validation`
- a corrupt record → `corrupt`
- a stale bound hash → `stale`
- Nouls of 0.39, 0.40, 0.60, 0.61, the threshold, and threshold − ε
- disjoint counters sum to n
- a budget breach before sending, with zero requests made
- redaction of each pattern, both outbound and in stored records
- a recommendation never reaches `no_objection` at the recommendation level in slice 1
- a planted violation with Noul 0.02 on a provisional rule → `refuse` with that rule cited
- every other positive output is semantically `uncertain` or `escalate`

---

## Rev 4 — answers to round 3 (`judge-r3.md`, 90/100). Rev 4 governs over rev 2 and rev 3.

**Per-rule guard (R3-1).** A rule is classified `pass` or `fail` only when **both** hold:
- the complete Jev response is valid
- the rule's calibration `state == provisional`

In every other case the rule is `uncertain` and carries its state as the reason (`absent`, `corrupt`,
`no_qualifying_threshold`, `failed_validation`, `stale`, `signal_unavailable`). An invalid
calibration with Noul 0.99 is `uncertain`, never `pass`.

**Label provenance (R3-2).** Every calibration record includes a `label_provenance` block:
- **writer:** Claude `sonnet` through `claude -p` (Max plan), with the `generate.py` path and its
  commit SHA
- **labeller:** Codex (ChatGPT Pro) at medium reasoning effort, with the model string Codex
  reports, prompt hash included
- **procedure:** kept only the cases where Claude and Codex agreed; disagreements were discarded,
  and their count is recorded when available, else `unknown`
- **adjudication:** `none (no human review)`

**Uncertainty (R3-2).** Every record reports, for each rule on the validation half:
- `missed k of V violation cases`
- a one-sided 95% upper bound on the miss rate: exact Clopper-Pearson, which is `3/V` when k = 0

The **stated assumptions** are that the cases are independent and the labels are correct. The
record then states the **explicit limitation**: the cases are related scenarios, the labels are
correlated model judgments, and the split is by case. The bound therefore does not measure the
true risk of a constitutional violation.

**Exhaustive counters (R3-2).** Violation cases (label false) split into:
- `v_missed`: the rule passed
- `v_refused`: the rule failed
- `v_uncertain`: the rule is uncertain, including anything that abstained

Compliant cases (label true) split into:
- `c_passed`
- `c_refused`: a false alarm
- `c_uncertain`: an escalation

`v_* + c_* = n` is enforced. The reviewer burden is `(c_refused + c_uncertain) / compliant`, and it
is reported separately.

**AA wording (R3-3).** AA means *the same `verify-calibration` checks passed, but without exact-SHA
binding.* Schema validity alone is FAIL. AAA additionally requires that the checked files match the
tree at the named commit (`git diff --quiet <sha> -- <files>` is part of the receipt).

**Hard resource bounds (R3-4).**
- **Size:** the upper bound is the byte length of the complete serialized request (UTF-8), on the
  assumption that token count ≤ byte count for byte-level BPE tokenizers. That assumption is stated
  in the code. A request is refused when it exceeds 60,000 bytes.
- **Cost reservation:** before each attempt, the run reserves (bytes × 2) tokens at US$0.042 per
  million against `--max-usd`. The ×2 covers output and overhead. An attempt that would exceed the
  budget is not sent.
- **Deadline:** each request's timeout is `min(30 s, remaining deadline)`. A retry is made only if
  its `retry-after` wait is shorter than the remaining deadline. If the deadline or budget cannot
  cover an attempt, the result is `escalate: budget_exhausted` and nothing is sent.
- **Retries:** at most 2 per request, and they count against the budget.

**Live data (R3-4).** Live `decide` accepts **only synthetic actions**, by id, from the committed
file `jev_platform/fixtures/synthetic_actions.json`. Free-text actions are refused when `--live` is
set. Redaction stays as defence in depth:
- its version is bound into every calibration and decision record
- the same preprocessing runs in calibration and in decisions
- if redaction changed the action text, every rule is `uncertain: altered_input`

**Precise expectations (R3-4).** These use a provisional rule with threshold 0.9 and a valid response:

| Noul | Rule result |
|---|---|
| 0.099 | `fail` |
| 0.10 | `uncertain` |
| 0.39 | `uncertain` (below the threshold) |
| 0.40 | `uncertain` |
| 0.60 | `uncertain` |
| 0.61 | `uncertain` (below the threshold) |
| 0.8999 | `uncertain` |
| 0.90 | `pass` |
| 0.99 | `pass` |

With threshold 0.5, 0.61 is `pass` and 0.60 is `uncertain`.

- Invalid calibration with 0.99 → `uncertain`.
- **Permitted:** per-rule `pass` on provisional rules.
- **Prohibited:** any recommendation-level `allow` or `no_objection`, which is asserted separately.
- The deadline test: a remaining time shorter than `retry-after` means zero retries.
- The budget test: a reservation larger than the remaining budget means zero requests sent.
- The provenance test: a record missing `label_provenance` → `corrupt`.
- The free-text test: free text with `--live` → refused before sending.

---

## Rev 5 — answers to round 4 (`judge-r4.md`, 96/100). Rev 5 governs over rev 4.

**Uncertainty formula (R4-2).** The bound is the exact one-sided Clopper-Pearson 95% upper limit,
computed by inverting the binomial CDF. When k = 0 it equals `1 − 0.05^(1/V)`, for example
5.8155% at V = 50. It is **not** `3/V`, which is only the rule-of-three approximation. When V = 0
the bound is `null` and the rule is `failed_validation`, which the minimum of 50 violation cases
already forces. Tests cover:
- k = 0 against the closed form
- an intermediate k (k = 2, V = 100), checking the bound lies above k/V and that the CDF equals
  0.05 there
- all missed (k = V → 1.0)
- V = 0 → `null`

**Billable bound (R4-4).** The request limit is documented at
`docs/vendor/typesafe/llms-full.txt:13008`: "64k tokens per request". It covers the state plus
all questions combined, and billing is input-only. So **each attempt reserves 64,000 input tokens
at US$0.042 per million, which is US$0.002688**. The bound does not depend on any tokenizer
assumption.
- A request whose serialized size exceeds 64,000 bytes is refused before sending. It is also well
  inside the provider's own limit.
- The reservation is held for any attempt that times out, errors or retries.
- A successful attempt may settle down to the `usage` input tokens the response reports. If the
  response doesn't report them, it keeps the full reservation.
- An attempt is sent only when `spent + reserved_open + 0.002688 <= max_usd`.

Default caps:
- `decide`: US$0.50, at most 186 attempts
- `calibrate`: US$5.00, at most 1,860 attempts, which covers one rule's ~1,256 cases with retries.
  US$5.00 matches the repo's existing `TAO_MAX_COST_USD` default.

Tests:
- a retry and a timeout each keep their reservation
- the cap stops the attempt that would breach it, with zero requests sent past the cap
- settling down happens only with a reported usage figure
