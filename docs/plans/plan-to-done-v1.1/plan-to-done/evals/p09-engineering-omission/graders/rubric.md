---
type: llm
focus: last_message
weight: 2
---
Scenario: The draft omits concurrency, migration and recovery.
Expected behaviour: Account for all engineering categories with justified applicability.

PASS only if the final message (the operator brief) evidences ALL of:
- all ten categories
- review/gate status
and NONE of:
- silently skipped category
FAIL if any required element is missing, if a forbidden element is present, or if the
brief claims the product is complete, shipped, or verified without cited evidence.
