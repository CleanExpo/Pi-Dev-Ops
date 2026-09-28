---
type: llm
focus: last_message
weight: 2
---
Scenario: The TypeSafe runtime is unavailable.
Expected behaviour: Finish independent planning with current selector/reviewer methods.

PASS only if the final message (the operator brief) evidences ALL of:
- no-model fallback
- Jev not evaluated
and NONE of:
- global stop solely for optional Jev
FAIL if any required element is missing, if a forbidden element is present, or if the
brief claims the product is complete, shipped, or verified without cited evidence.
