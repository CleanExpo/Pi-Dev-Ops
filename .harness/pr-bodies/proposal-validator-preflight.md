## Summary

- Add pre-flight `validate_proposal_text()` to block template garbage (`str`, `<placeholders>`) before the spec pipeline judge runs — fixes the Round 1 0/100 failure from unsubstituted liaison JSON tokens.
- Introduce `MachineSpecProposalBody` (7-field Pydantic schema) in `app/server/models.py` plus `proposal_validator.py` with structured markdown parsing and judge prompt enrichment.
- Wire validation at pipeline entry, CEO-board liaison refinement, SPM liaison loop fallback, and `prebuild_judge._build_prompt`.

## Test plan

- [x] `python -m py_compile` on modified Python
- [x] `pytest tests/test_proposal_validator.py tests/test_*spec* tests/test_*liaison* tests/test_*judge* tests/test_*board*` — all green
- [ ] `python scripts/run_spec_pipeline.py --proposal "str" --dry-run` → blocked at validator
- [ ] Live dry-run with real proposal when `OPENROUTER_API_KEY` set

## Manual verification path

1. POST `/api/spec-pipeline/run` with proposal `str` → pipeline `blocked`, reason mentions bare type token.
2. POST with valid proposal ≥10 chars → passes validator stage, proceeds to STORM/judge.
