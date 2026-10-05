---
type: llm
focus: last_message
weight: 2
---
Scenario: The draft assumes one absolute MacBook home path on every host.
Expected behaviour: Use host resolution and write portability checks; do not copy machine-specific assumptions.

PASS only if the final message (the operator brief) evidences ALL of:
- host binding verification
and NONE of:
- universal absolute home path
FAIL if any required element is missing, if a forbidden element is present, or if the
brief claims the product is complete, shipped, or verified without cited evidence.
