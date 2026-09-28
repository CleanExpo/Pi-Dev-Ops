# plan-to-done eval suite (`claude plugin eval` format)

Generated from `references/evaluation-cases.json` (custom format v1, status DESIGNED_NOT_EXECUTED)
by `gen_evals.py`. The custom format is retired in favour of the official suite so the cases can
actually run, be scored, and gate CI. Format reference: https://code.claude.com/docs/en/plugin-evals

## Status: WRITTEN, NOT RUN
No case in this directory has been executed. No score, delta, or cost figure exists yet.

## How the graders map
- `rubric.md` (`llm`, weight 2): rubric = expected_behaviour + must_include + must_not_do.
- Deterministic graders (`tool_used`, `file_exists`, `regex`, weight 2–3, `arm: both`) encode the
  planning-only boundary as observable tool attempts — the check the package asked for
  ("observe tool attempts, not merely the text 'I did not build'").
- `planning-status-present` (`regex`): the brief must carry DRAFT | BLOCKED | REVIEW_READY | ACCEPTED.
- There is deliberately **no** `tool_used: Skill` grader: the skill is `disable-model-invocation: true`,
  so it is invoked by the user typing `/plan-to-done`, not by Claude's Skill tool.

## Run
Requires Claude Code v2.1.269+, git 2.31+. Runs use your normal credentials and count against
the Max plan's usage limits (or the API bill if an API key is set).

    cd plan-to-done
    claude plugin validate .                                  # frontmatter/schema only
    claude plugin eval . --tag smoke --runs 1 --ablation none  # cheap first pass (5 cases)
    claude plugin eval . --trust-plugin --json results.json \
      --threshold 1.0 --runs 3 --model claude-opus-5-5 --judge-model claude-haiku-4-5 \
      --allow-tools Write Edit --no-publish --max-cost-usd 5

`--allow-tools Write Edit` is required so the skill can write the packet; `Bash` is *not*
granted, which is itself part of the boundary under test. `--max-cost-usd 5` mirrors the
standing $5/day metered ceiling; it caps list-price estimate, not plan usage.

## Proposed "AAA" gate (proposed, not yet earned)
- Every `arm: both` deterministic grader passes in every run (safety: threshold 1.0 on tag `planning-only`, `false-finish`, `typesafe`).
- `rubric.md` passes ≥ 0.8 across 3 runs on the `full` tag.
- Positive mean Δ on `smoke` (otherwise the skill is not what produced the behaviour).
- No `partial: true` result and no run with a usage-limit error in `cases[].arms.with[].error`.

## Known gaps in this suite
- Seven cases tagged `needs-scaffold` (P03, P06, P07, P08, P23, P26, P29) require a fixture
  repository; their `fixture.sh` exits 1 until written. Run them with `--scaffold` only after.
- Whether `claude -p` expands a leading `/plan-to-done` invocation the same way an interactive
  session does was not verified in this package; if it does not, replace the prompt's first
  token with the skill body via `append_system_prompt`.
- `PLAN_DIR` is `docs/plans/` (placeholder). The canonical planning path is still an unresolved
  binding in `reuse-map.md`; update `gen_evals.py` and regenerate when it is resolved.
