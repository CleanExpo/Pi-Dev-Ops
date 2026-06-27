# Judge Approval Policy

Judge is a pre-build gate.

## Decisions

- **REJECT**: Do not build.
- **REDUCE SCOPE**: Proposal is too large, vague, risky, or unsupported.
- **APPROVE EXPERIMENT**: Build only a small reversible proof.
- **APPROVE BUILD**: Build may proceed after user confirmation.

## Score thresholds

- 0–69: reject
- 70–84: reduce scope or experiment
- 85–100: build may proceed

## Hard blocks

Judge must block approval if:

- First-source evidence is missing
- The problem is unclear
- Existing capability has not been checked
- Security/privacy risk is unreviewed
- There is no test plan
- The build is too broad to reverse safely
