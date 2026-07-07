# evals/ — the Prove-It Gate (RA-7014)

Golden-dataset evals for estate agents/skills. The empirical ship gate that makes
agentic shipping *trustworthy*: an agent change ships only if it still passes a
versioned golden dataset. Spec: brain-1 vault `Wiki/capability-library-2026-07-08.md`
§5 and `Sketches/08-prove-it-gate.md`.

## Status: slice 1 — NON-BLOCKING

- **What runs now:** deterministic, code-checkable golden assertions (no LLM judge).
  Pilot target is `provider_router` (Cap 1's surface) because it's in-repo and its
  routing is deterministic.
- **Where:** top-level `evals/` (kept out of the blocking `pytest tests/` run on
  purpose). CI: `.github/workflows/prove_it_evals.yml`, `continue-on-error: true`.
- **Run locally:** `TAO_CHEAP_PROVIDER=openrouter uv run pytest evals -q`

## Roadmap (later slices, each its own PR)

2. Binary LLM-as-judge + calibration harness (30–50 expert-labeled cases; gate on
   <20% judge↔expert disagreement) for a non-deterministic agent.
3. Flip to a **blocking** tao-loop termination gate (remove `continue-on-error`).
4. Online eval on sampled prod traces (Langfuse self-host) → trace becomes a new case.
5. `eval-healer` self-healing optimizer with anti-gaming guardrails (SHA-256 read-only
   eval script + dataset, 5-revert restore, humans-only edit datasets).

## Adding a golden dataset

Drop `evals/golden/<target>.yaml` (input→expected, incl. tool-chain expectations) +
`evals/test_<target>_golden.py`. Keep expectations **code-checkable** where possible;
reserve the LLM judge for genuinely subjective checks, and always calibrate it first.
