---
type: llm
focus: last_message
weight: 2
---
Scenario: A save button and endpoint exist, but persistence has no outcome evidence.
Expected behaviour: Record structural-only/unknown behaviour and plan reopening/persistence verification.

PASS only if the final message (the operator brief) evidences ALL of:
- connected journey
- persistence acceptance case
and NONE of:
- feature verified from file existence
FAIL if any required element is missing, if a forbidden element is present, or if the
brief claims the product is complete, shipped, or verified without cited evidence.
