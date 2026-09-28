# TypeSafe and Jev: planning-and-writing boundary

## Roles

The upstream typesafe-ai skill guides a generative agent in designing TypeSafe questions,
interfaces and evaluations. Jev is a runtime decision model, not the author of the project
specification. Claude, Codex or another authorised generative writer writes the plan.
This planning skill makes no live TypeSafe calls, including observation-only calls.

Inspect the pinned upstream source and refresh relevant official documentation when designing
an integration. Pin and review dependencies before adoption; do not auto-install the vendor's
plugin, import an entire repository, update every agent, or create credentials.

The inspected upstream skill reference is typesafe-ai/skills at commit
65a39f393687675ce170e6094757de20370365b9, path skills/typesafe-ai/SKILL.md.
This identifies reviewed guidance, not an installed dependency or the Jev model version.
No upstream source text or installer is vendored in this package.

## Suitable advisory decisions to specify

| Decision | Proposed use | Required boundary |
|---|---|---|
| Intent fidelity | Flag probable ambiguity, changed meaning or missing constraints | A generative reviewer resolves meaning; owner acceptance remains separate |
| Skill relevance | Rank eligible planning/review skills from a host-generated shortlist | Mandatory skills cannot be suppressed; retain no-match |
| Evidence relevance | Flag mismatched claims or potentially relevant source excerpts | Code checks IDs, timestamps and hashes; no probability becomes proof |
| Requirement compatibility | Flag possible contradiction or missing coverage | Independent review and explicit decisions settle the result |
| Test relevance | Suggest additional regression scenarios | Never remove mandatory tests |
| Future runtime triage | Suggest bounded next actions in a separately authorised integration | No authority, release or completion decision delegated to Jev |

Use deterministic lookup for known IDs, exact arithmetic, dates, permissions and budgets.
Do not add a model call where existing code can reliably answer the question.

## Decision contract fields to write

Define contract ID and revision; purpose; input fields and provenance; minimum evidence;
state freshness; data-egress classification; required redaction; permitted candidates;
question wording; primitive; output schema; uncertainty handling; fallback; resource limit;
evaluation dataset; acceptance criteria; policy boundary; result retention and owner.
These are internal design fields, not claims about vendor API parameter names.

For each decision, write one coherent question and the exact meaning of each possible answer.
Use Choice for mutually exclusive alternatives, Noul for a yes/no probability and Score for
an ordered degree. Multiple simultaneously applicable labels need separate suitable questions,
not a forced single winner. For Choice and Score, distinguish confidence from the underlying
probabilities. Do not invent a separate Noul confidence field.

Include NO_MATCH or abstention when appropriate. Candidate completeness is testable: omitted
valid candidates must be detected rather than blaming the model for failing to select them.
A harmless ranking among several acceptable alternatives need not block on low concentration.
Risk thresholds require calibration on relevant labelled examples, not a copied constant.

## Runtime design pattern to document, not execute

Relevant state → deterministic candidate eligibility → egress filter → bounded Jev evaluation
→ recorded result → deterministic policy/action guard → existing executor → independent outcome check.

The guard rechecks state freshness, task version, ownership, candidate existence, authority,
resource limits and cancellation after the response arrives. An old result may not authorise
a newly changed state. Invalid or missing output blocks that decision-dependent action, while
a pre-approved non-Jev fallback or unrelated work may proceed. It does not bypass any gate.

## Evaluation and activation plan

1. Write deterministic fixtures and a baseline using existing routing or rules.
2. Define failure cases: missing state, contradictory sources, unavailable candidates,
   injection, invalid output, service timeout, stale decision, review disagreement and drift.
3. Specify labelled replay with multiple trials and separate development/held-out examples.
4. Compare task-relevant error rates, abstention, missed mandatory skills, context loaded,
   latency and total cost. Report denominators and uncertainty; no demo statistic becomes a promise.
5. Obtain explicit data-egress, provider and spend permission before any future live evaluation.
6. After independent evaluation, propose bounded activation and rollback through existing controls.

Offline design, offline fixture checks, live shadow calls and live action use are distinct modes.
Shadow means no action is applied; it does not mean no data leaves the system or no money is spent.

## No-model fallback in the current plan

Use the existing skill selector, deterministic routing and permitted generative review. Record
Jev as DISABLED or NOT_EVALUATED rather than claiming its recommendations were used. A missing
optional Jev integration must not prevent writing a complete product plan.
