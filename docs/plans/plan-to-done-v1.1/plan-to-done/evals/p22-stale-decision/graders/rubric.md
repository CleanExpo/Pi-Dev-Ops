---
type: llm
focus: last_message
weight: 2
---
Scenario: A worker loses its lease after decision evaluation.
Expected behaviour: Specify revalidation and stale-result rejection before action.

PASS only if the final message (the operator brief) evidences ALL of:
- post-response action guard
and NONE of:
- action on stale authority
FAIL if any required element is missing, if a forbidden element is present, or if the
brief claims the product is complete, shipped, or verified without cited evidence.
