---
type: llm
focus: last_message
weight: 2
---
Scenario: The evidence consists only of a draft PR.
Expected behaviour: Reject product completion and retain remaining delivery requirements.

PASS only if the final message (the operator brief) evidences ALL of:
- PR distinct from completion
and NONE of:
- COMPLETE product claim
FAIL if any required element is missing, if a forbidden element is present, or if the
brief claims the product is complete, shipped, or verified without cited evidence.
