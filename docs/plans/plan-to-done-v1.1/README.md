# Pi-Dev-Ops / Mission Control: Planning and Writing Skill

**Package:** plan-to-done, design candidate v1.0.
**Date:** 28 September 2026.
**Boundary:** planning and writing only. No product implementation, worker dispatch or activation.

## What changed after the operator's correction

The output is not a build orchestrator and not a thin command that immediately hands work to
a builder. It is a dedicated skill for researching an existing project and writing the
complete, evidence-backed delivery specification. It checks the whole project's completion
boundary, not only the requirements that happened to be named in the latest prompt.

The permission split is deliberate: read relevant project evidence; write the actual planning
packet in the authorised output area; do not edit product code, existing active skills,
governance, CI, accounts or deployment state. Planning acceptance and build authority remain
separate. The TypeSafe skill supports integration design; live Jev use is disabled here.

## Package contents

- [Core skill](plan-to-done/SKILL.md): the single user-facing planning-and-writing entry.
- `plan-to-done/references/`: discovery, coverage, writing, delivery, TypeSafe, reuse,
  review, adoption, worked example and research provenance.
- [Evaluation cases](plan-to-done/references/evaluation-cases.json): 30 specified pressure cases, not executed model trials.
- [Design review](DESIGN-REVIEW.md): corrections, remaining qualifications and adoption boundary.
- `VALIDATION-REPORT.json`: measured local structural checks only.
- `MANIFEST.sha256`: content hashes for transport verification, not signed approvals.

## The intended output of the skill

A written packet covering the accepted intent, verified baseline, whole-project gaps,
requirements, engineering decisions, dependency-ordered build packages, acceptance cases,
release/recovery/operations plan, decision records and a precise handoff. Existing canonical
project documents are reused. The packet distinguishes planning completion, feature completion
and production outcome verification.

## Library fit

The proposed canonical destination is CleanExpo/skills-library. Keep the candidate quarantined
until independent evaluation and explicit promotion. After promotion, use the repository's
actual catalogue and routing rules. The package has not been committed, pushed, installed,
registered or synced to any host. Its existence is not proof that any runtime control works.

Read the core file for its procedure and references. The adoption sequence is in
[the integration reference](plan-to-done/references/integration-and-portability.md).
No installer or execution script is included.
