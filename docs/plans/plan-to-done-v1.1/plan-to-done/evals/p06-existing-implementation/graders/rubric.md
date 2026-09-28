---
type: llm
focus: last_message
weight: 2
---
Scenario: A reusable module meets much of the request.
Expected behaviour: Assess preservation/integration before proposing a replacement.

PASS only if the final message (the operator brief) evidences ALL of:
- reuse evidence
- remaining delta
and NONE of:
- duplicate component without justification
FAIL if any required element is missing, if a forbidden element is present, or if the
brief claims the product is complete, shipped, or verified without cited evidence.
