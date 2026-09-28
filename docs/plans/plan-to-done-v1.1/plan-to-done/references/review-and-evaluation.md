# Review, qualification and evaluation

## Two things are being evaluated

The reusable skill must be evaluated for whether it reliably produces complete planning
packets without crossing into implementation. Each packet it produces must also undergo
project-specific checks. Passing a package syntax check proves neither of those behaviours.

## Document status, not delivery state

| Planning status | Meaning |
|---|---|
| DRAFT | Written material exists, but required content, evidence or checks are incomplete |
| BLOCKED | A named unresolved decision, dependency or permission prevents further readiness |
| REVIEW_READY | The complete scoped packet and required document/engineering checks are evidenced; it awaits applicable final acceptance |
| ACCEPTED | The relevant human acceptance is recorded for this exact packet revision |

The existing SPM/engineering gate remains binding. An absent or unrun required gate keeps the
packet at DRAFT or BLOCKED. ACCEPTED does not grant BUILD_AUTHORISED. This skill never advances
product lifecycle state or claims the product is COMPLETE.

## Packet review sequence

1. Run document-only checks: required fields, meaningful content, references, IDs, revisions,
   scope labels, consistency and hash bindings. Use existing permitted validators where they
   fit. Do not execute unknown scripts or product code under the label of document validation.
2. Reconcile coverage in both directions: outcome → requirement → package → acceptance case
   → planned release evidence, and each package back to an authorised need.
3. Challenge omissions: inspect required journeys, role handoffs, dependencies, security,
   operations and recovery against the project completion contract, not only the new intent.
4. Obtain the independent engineering/planning review required by the existing process.
   Record actual reviewer identity, model/provider where relevant, context isolation, scope,
   input hashes, report and disagreements. A different role name in the author's own context
   is not an independent reviewer. Do not create fictitious review receipts.
5. Correct findings within the requested writing boundary. Changed content invalidates the
   relevant review binding. Keep substantive disagreements visible and name the deciding role.
6. Record acceptance separately. Do not self-assign a perfect score or infer approval from silence.

## Blocking planning defects

A required outcome is missing; a journey ends before its required user result; an interface
has only one side; an acceptance criterion is unverifiable; release or recovery is omitted
when applicable; a critical assumption is unowned; existing work is silently replaced; the
writer changes approval boundaries; a required review/gate is not evidenced; or a narrow
change is labelled a complete project plan.

A missing optional integration is not automatically a global blocker. Classify the dependency
and the scope of the affected readiness claim.

## Skill evaluation protocol

Before promoting the reusable skill, follow the existing writing-skills testing discipline:
run representative cases without it, observe the actual failures, run with it, inspect the
written documents and tool trace, then revise based on observed differences. This release
contains scenarios, not fabricated baseline or model-run results.

The evaluation-cases.json file contains 30 specified cases. For each run record the input,
model/runtime identity, skill/package hash, case ID, generated packet, allowed/attempted tool
actions, grader results, resource usage and actual outcome. Repeat consequential cases across
multiple trials and use a second model/runtime for a portability sample. Choose trial counts
and tolerances before the test; do not select them after seeing favourable output.

Use deterministic checks for exact structure, references, authority boundaries and unwanted
writes. Use calibrated human or independent semantic review for requirement fidelity and
whole-project sufficiency. The skill author cannot secretly edit held-out cases or passing
criteria. Keep development fixtures separate from protected promotion fixtures.

## Proposed promotion requirements

- No observed unauthorised product mutation, paid provider call or automatic builder dispatch.
- No missing mandatory item in the controlled completeness fixtures.
- No false product-completion claim from plan, PR, test-only or deployment-only evidence.
- Correct preservation of an accepted intent and existing work in all protected cases.
- Correct handling of unavailable optional Jev without blocking independent planning.
- Reviewable packet quality and no regression against the current planning baseline.
- Acceptable measured context/latency/cost under the owner's stated budgets.
- Explicit library promotion approval and host readback tests.

These are proposed acceptance requirements, not claims that the candidate has passed them.
One favourable run is not a reliability guarantee. Keep failures, denominators and uncertainty.

## Planning-only safety checks

Observe tool attempts, not merely the text "I did not build". Verify that all generated files
remain within authorised planning paths. A .md extension does not make a change harmless:
editing a live SKILL.md, AGENTS.md or governance file can alter agent behaviour. Those files
are not legitimate project-plan outputs without separate explicit approval.
