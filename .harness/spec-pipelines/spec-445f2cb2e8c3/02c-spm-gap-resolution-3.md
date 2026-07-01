# AMENDMENT PACKET — Pre-Flight Proposal Validator & Schema Enforcement
## Round 3 Gap Closure | Pi-Dev-Ops Spec Pipeline

---

## 1. REFINED_PROPOSAL

Add a pre-flight proposal validator and structured schema enforcement to the Pi-Dev-Ops spec pipeline to eliminate null/template-token submissions reaching the prebuild judge. The problem is confirmed: `ceo_board_liaison.py` emitted an unsubstituted template token (`'str'`) as proposal text in Round 1, producing a 0/100 judge score across all seven evaluation dimensions because no upstream guard existed. The solution has three precise components. First, extend the Pydantic proposal model in `app/server/models.py` by declaring seven fields (`problem_statement`, `evidence_refs`, `design_decisions`, `data_flows`, `ux_behaviour`, `acceptance_criteria`, `implementation_scope`) as `Optional[str] = None` — preserving backward compatibility with all existing callers while making the fields addressable by name. Second, add `validate_proposal_text()` to `app/server/spec_pipeline/ceo_board_liaison.py`, enforcing three canonical rejection patterns as module-level constants: `BARE_TYPE_RE = re.compile(r'^(str|int|float|bool|list|dict|tuple|None)$', re.IGNORECASE)`, `PLACEHOLDER_RE = re.compile(r'<[^>]+>')`, and `EMPTY_RE = re.compile(r'^\s*$')`; the function raises `ValueError` naming the offending field before the judge is ever invoked, and is the sole enforcement point so rollback requires reverting only this call. Third, update `app/server/spec_pipeline/prebuild_judge.py` to structurally map each of its seven scoring dimensions to the corresponding named schema field, eliminating the "no content to evaluate" gap that caused dimension scores of zero. Test coverage is delivered in `tests/test_prebuild_judge_schema.py` using a two-tier fixture strategy: Tier 1 unit tests mock `prebuild_judge.score()` and run in CI, proving `validate_proposal_text()` raises `ValueError` on bad input and passes on good input; Tier 2 integration tests marked `@pytest.mark.integration` invoke the live judge with a fully-populated proposal and assert all seven dimension scores exceed zero, running on-demand only, following the pattern established in `tests/test_debate_runner.py`. All processing remains internal to the spec pipeline; no external API calls, no user PII, no new auth surface. Acceptance criteria: (a) a proposal whose any field contains the bare string `'str'` is rejected with `ValueError` naming that field before the judge is invoked; (b) a proposal with all seven fields populated with substantive text scores > 0 on every judge dimension in the Tier 2 integration run; (c) `python -m py_compile` passes on all four modified/created files; (d) Tier 1 unit tests pass in CI without network access. Estimated scope: three files modified, one test file created, 80–120 lines net addition, fully reversible by reverting the `validate_proposal_text()` call site.

---

## 2. GAP_ANSWERS

**Gap 1 — Acceptance criteria (a) and (b) are forward claims; implementation does not yet exist.**

The proposal is approved to build. The amendment packet does not re-litigate approval; it specifies the exact implementation contract so the judge can mark both criteria SUPPORTED at first smoke-test. Criterion (a) will be proven by Tier 1 unit test `test_bare_type_rejected` in `tests/test_prebuild_judge_schema.py`, which passes `problem_statement='str'` to `validate_proposal_text()` and asserts `ValueError` is raised with the string `'problem_statement'` in the message — no judge invocation required, no network dependency, runs in CI. Criterion (b) will be proven by Tier 2 integration test `test_full_proposal_scores_nonzero`, marked `@pytest.mark.integration`, which constructs a `ProposalModel` with all seven fields populated with substantive text, calls the live `prebuild_judge.score()`, and asserts every value in the returned dimension dict is greater than zero. The judge can mark (a) SUPPORTED when the Tier 1 CI run is green; the judge can mark (b) SUPPORTED when the Tier 2 integration run is green and its output is attached to the PR.

**Gap 2 — Exact regex patterns for 'bare type names' and 'angle-bracket placeholders' were unspecified.**

Three canonical patterns are now fixed as module-level constants in `ceo_board_liaison.py`:

```python
# Canonical rejection patterns — documented here, not inline, to survive code review
BARE_TYPE_RE  = re.compile(r'^(str|int|float|bool|list|dict|tuple|None)$', re.IGNORECASE)
PLACEHOLDER_RE = re.compile(r'<[^>]+>')
EMPTY_RE       = re.compile(r'^\s*$')
```

Semantic boundary: `BARE_TYPE_RE` uses full-field anchors (`^...$`) so a field whose *entire value* is `str` fails, but a field containing the word "str" mid-sentence (e.g., "The system will str-etch capacity…") passes. `PLACEHOLDER_RE` matches any angle-bracket token anywhere in the field value. `EMPTY_RE` catches whitespace-only strings that would pass a naive `if field:` check. These three patterns are exhaustive for the failure modes observed; adding a new pattern requires a one-line constant addition and a corresponding unit test — the extension path is explicit.

**Gap 3 — No rollback procedure for new Pydantic required fields breaking existing callers.**

The rollback strategy is architectural, not procedural. All seven fields are declared `Optional[str] = None` in the Pydantic model, making the model change strictly non-breaking: existing callers that pass partial objects continue to construct valid `ProposalModel` instances and receive no `ValidationError`. Enforcement of non-None, non-empty, and non-placeholder values lives exclusively in `validate_proposal_text()` in `ceo_board_liaison.py`, which is called at one call site before judge invocation. Rollback procedure: comment out or remove the single `validate_proposal_text(proposal)` call in `ceo_board_liaison.py`. The model change in `models.py` requires no rollback because `Optional[str] = None` fields are additive. Legacy callers that do pass partial objects will receive a `ValueError` with the named field (e.g., `"Field 'problem_statement' is empty or missing"`) rather than a silent `ValidationError` — this is intentional: the error is informative, not swallowed. Migration path for any caller that needs to pass partial objects legitimately: pass the fields it has and omit the rest; the model accepts `None`; only the liaison layer enforces completeness.

**Gap 4 — Test fixture strategy (mock vs. live judge) was unspecified; brittleness risk.**

Two-tier fixture strategy, mirroring `tests/test_debate_runner.py`:

- **Tier 1 — Unit (CI-safe, no network):** `pytest` fixture creates a `ProposalModel` directly. `prebuild_judge.score()` is patched with `unittest.mock.patch` to return a fixed dict `{"problem_statement": 10, "evidence_refs": 10, ...}`. Tests in this tier prove: (i) `validate_proposal_text()` raises `ValueError` on each rejection pattern independently; (ii) `validate_proposal_text()` does not raise on a fully-populated valid proposal; (iii) the `ValueError` message contains the offending field name. These tests have zero external dependencies and are deterministic.

- **Tier 2 — Integration (on-demand, network-required):** Marked `@pytest.mark.integration` and excluded from the default CI `pytest` invocation via `pytest.ini` addopts or `conftest.py` marker filter. A fully-populated `ProposalModel` is constructed with substantive text in all seven fields. The live `prebuild_judge.score()` is invoked. The test asserts `all(score > 0 for score in result.values())`. This tier runs manually before PR merge and its output log is attached as PR evidence. The integration marker pattern is already present in the repo; this test follows it exactly.

---

## 3. SCOPE_LOCK

### Files In Scope

| File | Change Type | Change Summary |
|---|---|---|
| `app/server/models.py` | Modify | Add seven `Optional[str] = None` fields to `ProposalModel` (or equivalent proposal Pydantic class) |
| `app/server/spec_pipeline/ceo_board_liaison.py` | Modify | Add three module-level regex constants; add `validate_proposal_text(proposal: ProposalModel) -> None` function; add one call site before judge invocation |
| `app/server/spec_pipeline/prebuild_judge.py` | Modify | Map each of seven scoring dimensions to the corresponding named `ProposalModel` field; eliminate string-literal field access that produces "no content to evaluate" |
| `tests/test_prebuild_judge_schema.py` | Create | Tier 1 unit tests (CI) + Tier 2 integration tests (`@pytest.mark.integration`) as specified in Gap 4 |

**Total: 3 files modified, 1 file created. Estimated 80–120 lines net addition.**

### Explicit Non-Goals

- **No changes to any file outside the four listed above.** `AGENTS.md`, `CLAUDE.md`, `conftest.py`, `pytest.ini`, and all other pipeline modules are out of scope for this amendment.
- **No new external API surface.** The validator is internal to the spec pipeline. No new HTTP endpoints, no new auth tokens, no new environment variables.
- **No changes to judge scoring weights or rubric logic** beyond the structural field mapping. The judge's scoring algorithm is not modified; only its input-to-dimension mapping is made explicit.
- **No enforcement of proposal *quality*.** The validator rejects structurally malformed proposals (empty, placeholder, bare type name). It does not evaluate whether the content is substantively good — that remains the judge's responsibility.
- **No migration of existing stored proposals.** Historical proposal records in any database or log are not touched. The validator applies only to new submissions at the liaison layer.
- **No changes to the Tier 2 integration test infrastructure** (CI configuration, `pytest.ini` marker registration). If marker registration is absent, the Tier 2 test file includes a `conftest.py` marker definition scoped to the `tests/` directory only — this is the one permitted exception, and it touches no existing file.

---

## 4. VERIFICATION

### How Each Gap Answer Is Proven

**Gap 1 — Forward claims (a) and (b) become SUPPORTED:**

| Criterion | Verification Method | Pass Condition | Environment |
|---|---|---|---|
| (a) `'str'` rejected before judge | `pytest tests/test_prebuild_judge_schema.py::test_bare_type_rejected` | `ValueError` raised; message contains `'problem_statement'`; mock confirms judge `.score()` never called | CI — no network |
| (b) Full proposal scores > 0 on all dimensions | `pytest tests/test_prebuild_judge_schema.py::test_full_proposal_scores_nonzero -m integration` | All seven dimension values in returned dict > 0 | On-demand; output log attached to PR |
| (c) py_compile passes | `python -m py_compile app/server/models.py app/server/spec_pipeline/ceo_board_liaison.py app/server/spec_pipeline/prebuild_judge.py tests/test_prebuild_judge_schema.py` | Exit code 0, no output | CI — pre-commit step |
| (d) Tier 1 passes in CI | `pytest tests/test_prebuild_judge_schema.py -m "not integration"` | All unit tests green, 0 network calls | CI |

**Gap 2 — Regex patterns are canonical and unambiguous:**

Verification is static: the three constants `BARE_TYPE_RE`, `PLACEHOLDER_RE`, `EMPTY_RE` appear verbatim as module-level assignments in `ceo_board_liaison.py`. Code review confirms their presence. Unit tests provide dynamic proof:

- `test_bare_type_rejected`: parametrized over `['str', 'int', 'float', 'bool', 'list', 'dict', 'tuple', 'None', 'STR', 'INT']` — each raises `ValueError`.
- `test_bare_type_passes_in_prose`: field value `"The system will accept str input from operators"` — does **not** raise `ValueError` (whole-field anchor semantics confirmed).
- `test_placeholder_rejected`: field value `"<insert_problem_here>"` — raises `ValueError`.
- `test_empty_rejected`: field value `"   "` — raises `ValueError`.

**Gap 3 — Rollback procedure is proven non-breaking:**

Two verification steps:

1. **Static:** `grep -n "Optional\[str\]" app/server/models.py` returns seven lines, one per field. Confirms no `required` field was introduced.
2. **Dynamic:** Unit test `test_legacy_caller_partial_object` constructs a `ProposalModel` with only two of the seven new fields populated (the rest `None`) and asserts no `ValidationError` is raised at model construction time. This proves the model layer is non-breaking. A second assertion confirms that passing this partial object to `validate_proposal_text()` raises `ValueError` naming the first missing field — proving enforcement lives only at the liaison layer.

**Gap 4 — Test fixture strategy is unambiguous and non-brittle:**

Verification is structural: `tests/test_prebuild_judge_schema.py` is reviewed for:

1. Presence of `@pytest.mark.integration` decorator on all Tier 2 tests and absence of that decorator on all Tier 1 tests.
2. Presence of `unittest.mock.patch('app.server.spec_pipeline.prebuild_judge.score')` (or equivalent import path) in all Tier 1 tests — confirmed by `grep`.
3. CI run log shows Tier 1 tests execute and pass with `--co` (collect-only) confirming no integration tests are collected in the default run.
4. Manual integration run log (attached to PR) shows Tier 2 test collected, executed, and passed with live judge output printed.

---

## GOAL_COMMAND

```
GOAL_COMMAND: /goal All four judge gaps are closed and marked SUPPORTED: (a) pytest tests/test_prebuild_judge_schema.py -m "not integration" passes green in CI with zero network calls, proving validate_proposal_text() raises ValueError on bare-type and placeholder inputs; (b) pytest tests/test_prebuild_judge_schema.py -m integration passes on-demand with live judge output showing all seven dimension scores > 0 for a fully-populated ProposalModel; (c) python -m py_compile exits 0 on all four in-scope files; (d) grep confirms BARE_TYPE_RE, PLACEHOLDER_RE, and EMPTY_RE are present as module-level constants in ceo_board_liaison.py; (e) grep confirms all seven new ProposalModel fields are declared Optional[str] = None; (f) no existing test suite regression — full pytest run excluding integration markers exits 0.
```