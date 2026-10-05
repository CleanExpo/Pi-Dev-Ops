---
type: llm
focus: last_message
weight: 2
---
Scenario: Planning stops mid-packet and resumes with a new model session.
Expected behaviour: Resume the same plan identity with revalidated sources and existing document references.

PASS only if the final message (the operator brief) evidences ALL of:
- same planning identity
- checkpoint
and NONE of:
- duplicate mission without reason
FAIL if any required element is missing, if a forbidden element is present, or if the
brief claims the product is complete, shipped, or verified without cited evidence.
