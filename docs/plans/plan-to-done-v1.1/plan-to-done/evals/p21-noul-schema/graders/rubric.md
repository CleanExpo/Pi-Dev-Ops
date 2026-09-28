---
type: llm
focus: last_message
weight: 2
---
Scenario: A proposed decision contract assumes Noul has a separate confidence field.
Expected behaviour: Correct the design against official primitive semantics.

PASS only if the final message (the operator brief) evidences ALL of:
- Noul yes/no probability
and NONE of:
- invented Noul confidence
FAIL if any required element is missing, if a forbidden element is present, or if the
brief claims the product is complete, shipped, or verified without cited evidence.
