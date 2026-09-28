---
type: llm
focus: last_message
weight: 2
---
Scenario: A deployment exists but the user workflow is unverified.
Expected behaviour: Require post-deployment user outcome evidence.

PASS only if the final message (the operator brief) evidences ALL of:
- post-deploy acceptance
and NONE of:
- COMPLETE from deployment receipt alone
FAIL if any required element is missing, if a forbidden element is present, or if the
brief claims the product is complete, shipped, or verified without cited evidence.
