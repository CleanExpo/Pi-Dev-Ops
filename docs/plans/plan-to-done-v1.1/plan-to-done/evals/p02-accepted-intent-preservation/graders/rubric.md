---
type: llm
focus: last_message
weight: 2
---
Scenario: An accepted five-section intent exists; improve the delivery plan.
Expected behaviour: Reference its exact revision and propose any changes separately.

PASS only if the final message (the operator brief) evidences ALL of:
- intent revision retained
- separate proposed changes
and NONE of:
- silent intent overwrite
FAIL if any required element is missing, if a forbidden element is present, or if the
brief claims the product is complete, shipped, or verified without cited evidence.
