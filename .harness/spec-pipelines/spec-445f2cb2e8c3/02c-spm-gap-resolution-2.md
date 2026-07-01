# AMENDMENT PACKET — Pi-Dev-Ops Prebuild Judge Hardening
**Round 2 | Gap Closure Before Build**

---

## 1. REFINED_PROPOSAL

Add a pre-flight proposal validator and structured schema enforcement to the Pi-Dev-Ops spec pipeline to eliminate null and unsubstituted-template submissions from reaching the prebuild judge. The problem is concrete and repo-evidenced: in Round 1, `ceo_board_liaison.py` emitted the bare Python type annotation `str` as proposal text — a template substitution failure — causing a 0/100 judge score across all seven evaluation dimensions; the judge correctly detected the failure but no upstream guard existed to prevent it. The fix reuses existing repo structure without introducing new dependencies: (1) add `validate_proposal_text()` to `app/server/spec_pipeline/ceo_board_liaison.py` that raises `ValueError` on unsubstituted tokens (bare type names, angle-bracket placeholders, empty strings, strings under 20 characters) before judge invocation; (2) extend the existing Pydantic proposal model in `app/server/models.py` with seven required fields — `problem_statement: str` (min 50 chars), `evidence_refs: list[str]` (min 1 item), `design_decisions: str` (must reference an `app/`, `tests/`, or `skills/` path), `data_flows: str`, `ux_behaviour: str`, `acceptance_criteria: list[str]` (min 2 items), `implementation_scope: str` — each field mapping 1-to-1 to a judge scoring dimension, making "no content to evaluate" gaps structurally impossible; (3) update `prebuild_judge.py` to read each dimension from its corresponding schema field rather than free-text parsing; (4) add `tests/test_prebuild_judge_schema.py` covering null-token rejection and all-fields-present scoring; all changes staged to `/tmp/pi-ceo-workspaces/prebuild-judge-hardening/` with no push until instructed, zero external API cost delta, estimated 4 files changed, under 200 lines net, low risk.

---

## 2. GAP_ANSWERS

**Gap 1 — No proposal text was provided; the `str` placeholder was never replaced with actual content.**
Root cause is a template substitution failure in `ceo_board_liaison.py`: the pipeline passed the Python type annotation `str` literally instead of interpolating real content. Fix: add `validate_proposal_text(text: str) -> None` as the first call inside the proposal-submission path in `app/server/spec_pipeline/ceo_board_liaison.py`. The function raises `ValueError` with a descriptive message if the input matches any of: bare Python built-in type names (`str`, `int`, `bool`, `list`, `dict`), angle-bracket tokens (`<.*?>`), empty string, or length < 20 characters. This guard fires before the proposal object is constructed, before the judge is invoked, and before any schema validation runs. The fix is evidenced by `app/server/spec_pipeline/ceo_board_liaison.py` existing in the repo as confirmed by STORM evidence.

**Gap 2 — Cannot evaluate `first_source_evidence`: no claims exist to check against repo context.**
Add required field `evidence_refs: list[str]` with a Pydantic `min_length=1` constraint to the proposal schema in `app/server/models.py`. Each item must be a non-empty string referencing a repo path, file name, or STORM evidence row identifier. The prebuild judge's `first_source_evidence` scoring dimension is updated to read directly from `proposal.evidence_refs` rather than attempting free-text extraction. A proposal with zero evidence references fails Pydantic validation and never reaches the judge, making the gap structurally impossible to reproduce.

**Gap 3 — Cannot evaluate `clear_problem`: no problem statement present.**
Add required field `problem_statement: str` with a Pydantic `min_length=50` validator to the proposal schema. The judge's `clear_problem` dimension is updated to score against `proposal.problem_statement` directly. Strings under 50 characters fail schema validation with a clear error message (`"problem_statement must be at least 50 characters"`). This enforces that submitters articulate a real problem rather than a label.

**Gap 4 — Cannot evaluate `reuse_existing`: no design decisions described.**
Add required field `design_decisions: str` to the proposal schema with a custom Pydantic validator that checks the string contains at least one substring matching the regex `(app/|tests/|skills/)` — confirming the decision references an existing repo path. The judge's `reuse_existing` dimension reads from `proposal.design_decisions`. Proposals that describe only net-new components without referencing existing structure fail validation before reaching the judge.

**Gap 5 — Cannot evaluate `security_privacy`: no data flows or auth decisions described.**
Add required field `data_flows: str` to the proposal schema. For internal-only pipeline changes (as this proposal is), the acceptable value is an explicit statement such as `"No external data flow; all processing is intra-process with no auth surface changes"` — the field cannot be empty or omitted. The judge's `security_privacy` dimension scores presence and specificity of the `data_flows` field. An empty string fails Pydantic `min_length=10` validation.

**Gap 6 — Cannot evaluate `ux_clarity`: no user-facing behaviour described.**
Add required field `ux_behaviour: str` to the proposal schema. For machine-board / pipeline proposals, "user" is defined as the pipeline operator or calling agent. The field must describe an observable output change — e.g., what error message appears on bad input, what the successful output looks like. The judge's `ux_clarity` dimension reads from `proposal.ux_behaviour`. Minimum length 20 characters enforced by Pydantic.

**Gap 7 — Cannot evaluate `testability`: no acceptance criteria or test strategy described.**
Add required field `acceptance_criteria: list[str]` with `min_length=2` (at least two criteria) to the proposal schema. The judge's `testability` dimension reads from `proposal.acceptance_criteria`. Additionally, the new test file `tests/test_prebuild_judge_schema.py` is explicitly named in `implementation_scope`, making the test strategy concrete and repo-traceable rather than aspirational.

**Gap 8 — Cannot evaluate `cost_simplicity`: no implementation scope described.**
Add required field `implementation_scope: str` to the proposal schema. The field must contain an effort estimate covering: files changed (count), estimated net line delta, and a risk level token (`LOW`, `MEDIUM`, or `HIGH`). A Pydantic validator checks for presence of at least one digit (line/file count) and one of the three risk tokens. The judge's `cost_simplicity` dimension reads from `proposal.implementation_scope`. The Revenue board gate also reads this field for budget validation.

---

## 3. SCOPE_LOCK

### Files / Modules IN SCOPE

| File | Change Type | Description |
|------|-------------|-------------|
| `app/server/spec_pipeline/ceo_board_liaison.py` | Modify | Add `validate_proposal_text()` guard function and call it at proposal submission entry point |
| `app/server/models.py` | Modify | Extend existing Pydantic proposal model with 7 required fields and their validators |
| `app/server/spec_pipeline/prebuild_judge.py` | Modify | Update each of 7 scoring dimensions to read from corresponding schema field instead of free-text parsing |
| `tests/test_prebuild_judge_schema.py` | Create | New test file: null-token rejection tests + all-fields-present scoring tests |

**Total: 4 files. Estimated net delta: ≤ 200 lines. Risk: LOW.**

### Explicit Non-Goals

- **Do not** rewrite or restructure the full 19-section spec pipeline
- **Do not** modify any file outside `app/server/spec_pipeline/`, `app/server/models.py`, and `tests/`
- **Do not** change judge scoring weights, thresholds, or pass/fail cutoffs
- **Do not** add any new external dependencies (no new `pip install` entries)
- **Do not** modify `skills/`, `app/client/`, or any frontend code
- **Do not** push to remote; all output staged to `/tmp/pi-ceo-workspaces/prebuild-judge-hardening/` only
- **Do not** alter the STORM evidence ingestion pipeline
- **Do not** address any Round 1 gaps beyond the eight listed above

---

## 4. VERIFICATION

### How Each Gap Answer Is Proven

**Gap 1 — `validate_proposal_text()` guard**
- *CI path:* `python -m py_compile app/server/spec_pipeline/ceo_board_liaison.py` passes (smoke test).
- *Manual path:* Call `validate_proposal_text("str")` in a Python REPL → confirm `ValueError` raised. Call `validate_proposal_text("<placeholder>")` → confirm `ValueError`. Call with a valid 50-char string → confirm no exception.
- *Test coverage:* `tests/test_prebuild_judge_schema.py::test_null_token_rejection` parametrized over `["str", "int", "<placeholder>", "", "short"]`.

**Gap 2 — `evidence_refs` field**
- *CI path:* `python -m pytest tests/test_prebuild_judge_schema.py::test_evidence_refs_required` — asserts `ValidationError` when field is absent or empty list.
- *Manual path:* Instantiate proposal model without `evidence_refs` → confirm Pydantic raises `ValidationError` with field name in error message.

**Gap 3 — `problem_statement` field**
- *CI path:* `pytest tests/test_prebuild_judge_schema.py::test_problem_statement_min_length` — asserts `ValidationError` for strings under 50 chars.
- *Manual path:* Instantiate model with `problem_statement="too short"` → confirm `ValidationError`. Instantiate with 50+ char string → confirm success.

**Gap 4 — `design_decisions` field with repo-path validator**
- *CI path:* `pytest tests/test_prebuild_judge_schema.py::test_design_decisions_requires_repo_path` — asserts `ValidationError` when no `app/`, `tests/`, or `skills/` substring present.
- *Manual path:* Instantiate with `design_decisions="We will build something new"` → confirm `ValidationError`. Instantiate with `design_decisions="Extends app/server/models.py"` → confirm success.

**Gap 5 — `data_flows` field**
- *CI path:* `pytest tests/test_prebuild_judge_schema.py::test_data_flows_required` — asserts `ValidationError` on empty string.
- *Manual path:* Instantiate with `data_flows=""` → confirm `ValidationError`. Instantiate with explicit no-external-flow statement → confirm success.

**Gap 6 — `ux_behaviour` field**
- *CI path:* `pytest tests/test_prebuild_judge_schema.py::test_ux_behaviour_required` — asserts `ValidationError` on missing or too-short field.
- *Manual path:* Instantiate without field → confirm `ValidationError`. Instantiate with 20+ char observable-output description → confirm success.

**Gap 7 — `acceptance_criteria` field**
- *CI path:* `pytest tests/test_prebuild_judge_schema.py::test_acceptance_criteria_min_two_items` — asserts `ValidationError` for lists with 0 or 1 items.
- *Manual path:* Instantiate with `acceptance_criteria=["only one"]` → confirm `ValidationError`. Instantiate with two items → confirm success.

**Gap 8 — `implementation_scope` field**
- *CI path:* `pytest tests/test_prebuild_judge_schema.py::test_implementation_scope_has_risk_token` — asserts `ValidationError` when none of `LOW`, `MEDIUM`, `HIGH` present.
- *Manual path:* Instantiate with `implementation_scope="some changes"` → confirm `ValidationError`. Instantiate with `"4 files, ~200 lines, LOW risk"` → confirm success.

**End-to-end integration check:**
- *Manual path:* Construct a fully valid proposal object with all 8 fields populated correctly → instantiate model without error → pass to `prebuild_judge.py` → confirm judge returns a score > 0 on all seven dimensions → confirm no "no content to evaluate" strings appear in judge output.
- *Staged diff check:* `diff -r /tmp/pi-ceo-workspaces/prebuild-judge-hardening/ app/server/spec_pipeline/` confirms only the four in-scope files are modified.

---

## 5. GOAL_COMMAND

```
GOAL_COMMAND: /goal prebuild_judge.py scores > 0 on all seven dimensions for any proposal that passes Pydantic schema validation, AND raises ValueError before judge invocation for any proposal containing unsubstituted template tokens, verified by pytest tests/test_prebuild_judge_schema.py (all tests green) and python -m py_compile passing on all four modified files, with zero files outside the four-file scope lock modified.
```