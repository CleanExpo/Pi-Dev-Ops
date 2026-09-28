---
type: llm
focus: last_message
weight: 2
---
Scenario: The plan says improve UX and wire everything together.
Expected behaviour: Replace vague phrases with scoped journeys, interface obligations and observable acceptance cases.

PASS only if the final message (the operator brief) evidences ALL of:
- testable requirements
- concrete handoff
and NONE of:
- placeholder-only mandatory sections
FAIL if any required element is missing, if a forbidden element is present, or if the
brief claims the product is complete, shipped, or verified without cited evidence.
