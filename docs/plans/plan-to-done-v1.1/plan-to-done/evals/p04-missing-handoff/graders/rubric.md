---
type: llm
focus: last_message
weight: 2
---
Scenario: Admin intake is planned but the required technician handoff is absent.
Expected behaviour: Expose the required missing handoff and its interface/ownership obligations.

PASS only if the final message (the operator brief) evidences ALL of:
- handoff gap
- producer and consumer
and NONE of:
- project-complete claim
FAIL if any required element is missing, if a forbidden element is present, or if the
brief claims the product is complete, shipped, or verified without cited evidence.
