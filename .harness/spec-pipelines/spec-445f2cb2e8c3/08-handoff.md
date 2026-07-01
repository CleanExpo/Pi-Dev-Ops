# Session Handoff — Machine Spec Pipeline
**Pipeline:** `spec-445f2cb2e8c3`
**Status:** BLOCKED
**Reason:** Three evidence rows are PARTIAL because the implementation does not yet exist in the repo (forward claims on code to be written), the prebuild_judge.py internals are not fully visible to verify the >0 scoring guarantee, and the bare-type-name detection rule has an unresolved edge-case ambiguity. Score cannot reach 100 until implementation is present, py_compile verified, and the detection rule is precisely specified.

## Proposal
Add a pre-flight proposal validator and structured schema enforcement to the Pi-Dev-Ops spec pipeline to eliminate null/template-token submissions reaching the prebuild judge. Problem: The ceo_board_liaison.py pipeline emitted an unsubstituted template token ('str') as proposal text in Round 1, causing a 0/100 judge score across all seven evaluation dimensions. This is a systemic gap: the judge correctly detected the failure but had no upstream guard to prevent it. Design decisions reusing existing repo structure: (1) Extend the existing Pydantic proposal model in app/server/models.py with seven required fields (problem_statement, evidence_refs, design_decisions, data_flows, ux_behaviour, acceptance_criteria, implementation_scope); (2) Add validate_proposal_text() to app/server/spec_pipeline/ceo_board_liaison.py — raises ValueError on bare type names, angle-bracket placeholders, or empty strings before the judge is invoked; (3) Update app/server/spec_pipeline/prebuild_judge.py to structurally map each of its seven scoring dimensions to the corresponding required schema field, eliminating 'no content to evaluate' gaps. Data flows and auth: all processing is internal to the spec pipeline; no external API calls, no user PII, no new auth surface introduced. UX behaviour: pipeline operators (machine board agents) receive an immediate, descriptive error at submission time if a proposal is malformed, rather than a 0/100 score with opaque gaps. Acceptance criteria: (a) A proposal containing the bare string 'str' is rejected with ValueError before reaching the judge; (b) A proposal with all seven fields populated scores > 0 on every judge dimension; (c) python -m py_compile passes on all modified files; (d) New test file tests/test_prebuild_judge_schema.py covers both cases. Implementation scope: ~3 files modified (models.py, ceo_board_liaison.py, prebuild_judge.py), 1 new test file, estimated 80-120 lines net addition. Low risk, high leverage, fully reversible.

## Artifacts
`.harness/spec-pipelines/spec-445f2cb2e8c3/`

## Pick up here
Review artifacts and re-run with fixes.

Generated: 2026-07-01T11:38:52.482415+00:00