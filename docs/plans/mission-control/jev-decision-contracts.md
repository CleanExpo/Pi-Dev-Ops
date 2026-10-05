# Jev decision contracts for the Mission Control test suite

**Status:** DESIGNED. Activation state: **BLOCKED-EXTERNAL** — this cloud environment's network
policy refuses `api.typesafe.ai` (proxy `CONNECT tunnel failed, response 403`, 28 Sept 2026), and
no always-on runner holds the key yet. The key exists as `TYPESAFE_API_KEY` in the `pi-dev-ops`
Vercel project (all environments; name read, value not decrypted).

**Authority for egress:** Phill asked on 28 Sept 2026 to "use Typesafe_Jev … to perform the 1000s
of tests throughout the entire Mission Control". That covers sending Mission Control test output to
TypeSafe. It does not cover secrets, credentials or customer records — the redaction step below
removes those before any call.

Jev facts used here are from the vendor pages re-fetched on 28 Sept 2026
([routing-verification-2026-09-28.json](../idea-to-live/routing-verification-2026-09-28.json)):
`POST https://api.typesafe.ai/v1/systemone`, `Authorization: Bearer $TYPESAFE_API_KEY`, model
`jev-latest` (= `jev-1.13.0`), $0.042 per million **input** tokens, output free, 64k tokens per
request and 32k for `state` + the longest question, 1,200 requests/min, primitives Choice, Score,
Noul. The exact request body shape was not fetched; the first live call starts with `GET /v1/models`
and one hand-checked request before any batch.

## Where Jev sits — and does not

```
browser run → deterministic assertions (decide pass/fail, decide the grade)
            → text snapshot → redact → Jev (advisory label) → triage queue
```

Jev **never** changes a pass/fail, a grade, a merge or a deploy
([typesafe-planning.md](../plan-to-done-v1.1/plan-to-done/references/typesafe-planning.md):
"No authority, release or completion decision delegated to Jev"). Its value is volume: it reads
every snapshot from every run and flags the ones a human or Claude should look at, which no one
will do by hand across hundreds of journeys a night.

## Shared contract fields

| Field | Value |
|---|---|
| State | Visible page text (`innerText`) + list of network calls (method, path, status) for one journey; ≤ 24k tokens after truncation, leaving headroom under the 32k rule |
| Redaction | Before egress: drop cookies/headers entirely; mask anything matching the repo's secret patterns (`scripts/secrets_check.py`), emails, bearer tokens, `sk-`/`ghp_`/`AKIA` shapes; replace Linear/GitHub identifiers with stable hashes |
| Freshness | A label is valid only for the run ID and deployed SHA it was computed on |
| Fallback | Missing, invalid or low-confidence output → label `NOT_EVALUATED`; the run's grade is unaffected |
| Retention | JSONL alongside the run receipt: run ID, SHA, surface, contract, model ID returned, probabilities, confidence |
| Budget | **No daily cap** — founder decision 28 Sept 2026 ("lift the cap on JEV … while we are using the system heavy"). Spend is still recorded per UTC day in the ledger and printed after every run; `JEV_DAILY_CAP_USD` (or `--daily-cap`) reinstates a stop without a code change |
| Mode | Shadow first: labels recorded, nobody acts on them, for 7 nightly runs; then compared against human/Claude review of the same snapshots before labels drive the triage order |

## J1 — What did the user actually see? (Choice)

Question: "Given this page's visible text and its network calls, which best describes what a
signed-in user sees?" Options: `REAL_DATA`, `EXPLICIT_EMPTY_STATE`, `ERROR_SHOWN`,
`STUCK_LOADING`, `AUTH_WALL`, `NO_MATCH`.

Use: flag disagreements with the deterministic check 1 (e.g. assertions passed, Jev says
`ERROR_SHOWN`) → triage queue. Catches tests that assert the wrong element.

Evaluation: 60 hand-labelled snapshots (3 per surface) from the first run, split 40/20
development/held-out; report accuracy and abstention on held-out before shadow labels are trusted.

## J2 — Why did this fail? (Choice)

Question: "Given this failing check's assertion message, page text and network calls, what is the
most likely cause?" Options: `PRODUCT_BUG`, `TEST_BUG`, `ENVIRONMENT` (deploy/credentials/network),
`TIMING`, `NO_MATCH`.

Use: orders the repair queue (product bugs first). Never marks anything flaky or skipped — the
repo rule "flake is not a root cause" stands; `TIMING` still requires a fix.

## J3 — Does the label match what happened? (Noul)

Statement: "The control labelled «{label}» caused exactly the effect its label describes, and no
other effect, given these network calls: {calls}." One call per write action per run.

Use: pre-screen for MC control check 12 (label honesty, [aaa-rating.md](aaa-rating.md)). The deterministic assertion decides; J3 only
flags candidates where the probability is < 0.5.

## J4 — Where is coverage thinnest? (Score, 1–5)

Question per surface: "How well do these assertions cover this page's visible features?" State:
page text + the list of assertion descriptions for that surface.

Use: weekly ranking of which surfaces need more checks. Advisory input to the plan only.

## Volume and cost (arithmetic, not measurement)

A nightly run of ≈200 journeys × J1 + failures × J2 + 7 × J3 ≈ 220–600 calls. At a typical
8k-token state: 600 × 8,000 = 4.8M input tokens × $0.042/M ≈ **$0.20 per night**. Scaling to
"thousands" (5,000 calls/day at 8k) ≈ $1.68/day. The cap is lifted (see Budget), so volume is limited only by the rate limit. Rate limit (1,200/min) is not
a constraint at these volumes.

## Where it runs

1. **GitHub Actions nightly** (the always-on option under CLAUDE.md's "Railway + Vercel + GitHub
   Actions only"). Needs `TYPESAFE_API_KEY` added as a GitHub Actions secret — a secret only Phill
   can paste. GitHub-hosted runners have open egress.
2. **This cloud session**, once `api.typesafe.ai` is added to the environment's allowed domains —
   useful for the first hand-checked calls and the 60-snapshot evaluation set.

## Relationship to existing code

`app/server/provider_policy.py` refuses metered providers for *model dispatch*
(`tests/test_subscription_policy.py`). This evaluator is a test tool outside that path; it does not
route any build or planning work to Jev and does not require changing that policy. If Jev is later
proposed for runtime routing (mission-control-jev-next-five.md item 3), that is a separate change
with its own policy test.

## Fit with NEXUS-RELEASE-HARNESS v1.0 (adoption decision O5)

The portfolio packet treats Jev as optional advisory infrastructure behind an admission, with
application states `PROPOSE(candidate_id)` / `ABSTAIN` layered over the provider's typed answer.
These contracts already sit inside that boundary; the mapping is:

| Contract answer | Adapter state |
|---|---|
| A Choice option other than `NO_MATCH`, with the provider's confidence at or above the threshold set by the held-out evaluation | `PROPOSE(option)` |
| `NO_MATCH`, confidence below threshold, invalid output, vendor error, or no evaluation yet | `ABSTAIN` |
| J3 Noul probability | `PROPOSE(flag)` only when < 0.5 and above threshold; otherwise `ABSTAIN` |
| J4 Score (1–5) | `PROPOSE(surface)` for the lowest-scored surfaces in the weekly ranking, only once the held-out evaluation shows the scores track human judgement; otherwise `ABSTAIN`. A score is never a coverage measurement |

`scripts/jev_triage.py` today records the raw typed answer (status `OK`), or `NOT_EVALUATED` on a vendor error or missing answer, or `BUDGET_STOP` when a cap is set. The PROPOSE/ABSTAIN mapping and the confidence threshold are applied by the triage step that reads those labels. That step is not built yet, and its threshold comes from the held-out evaluation.

**Admission record for Mission Control test triage:**
- **Money:** founder decision, 28 Sept 2026, lifting the daily cap; confirmed 29 Sept 2026 as the
  recorded budget ("no cap stands, record it as the budget decision"). No daily cap; every call's cost
  is ledgered. Overrides the $5/day routing ceiling for Jev only.
- **Data egress:** founder request, 28 Sept 2026, to use Jev over Mission Control tests. Redaction is enforced before any call.
- **Still required before labels steer anything:** the 60-snapshot held-out evaluation (J1 above) and a reachable runner (RA-7832).

**What Jev never does:** count as either of the two independent audit reviewers, change a receipt, or set a grade. The deterministic route stays the default: `--dry-run`, and every label reads `NOT_EVALUATED` while Jev is off.
