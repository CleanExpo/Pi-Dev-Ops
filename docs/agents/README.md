<!-- GENERATED FILE — DO NOT EDIT. Run: python scripts/check_agent_registry.py --write-catalogue -->

# Nexus Shadow Agent Catalogue

This catalogue is generated from `fence/agents/registry.yaml`.
All roles are detection-only shadow definitions; this does not change runtime routing.

## `builder`

Implement an approved bounded slice inside an isolated workspace using test-driven development.

- Status: `shadow`
- Model policy role: `generator`
- Risk tier ceiling: `L1`
- Skills: `architecture`, `tao-tdd-pipeline`
- Evidence: `git-diff`, `focused-tests`

## `ci-recovery`

Classify failing CI gates and perform bounded reversible repairs without weakening or bypassing a gate.

- Status: `shadow`
- Model policy role: `generator`
- Risk tier ceiling: `L1`
- Skills: `unite-group-ci-recovery`
- Evidence: `failure-classification`, `repair-evidence`

## `planner`

Produce dependency-aware implementation plans, risks, and acceptance tests before build work starts.

- Status: `shadow`
- Model policy role: `planner`
- Risk tier ceiling: `L0`
- Skills: `forward-planner`, `technical-plan`
- Evidence: `implementation-plan`, `acceptance-tests`

## `release-monitor`

Observe release readiness and health, then provide rollback advice without merge or deployment authority.

- Status: `shadow`
- Model policy role: `monitor`
- Risk tier ceiling: `L0`
- Skills: `deployment`, `ship-release`
- Evidence: `health-observation`, `rollback-advice`

## `reviewer`

Independently review candidate code and architecture without editing the candidate workspace.

- Status: `shadow`
- Model policy role: `evaluator`
- Risk tier ceiling: `L0`
- Skills: `agentic-review`
- Evidence: `review-verdict`, `file-line-findings`

## `scout`

Map the repository, prior decisions, relevant files, constraints, and unresolved assumptions without mutation.

- Status: `shadow`
- Model policy role: `monitor`
- Risk tier ceiling: `L0`
- Skills: `architecture`
- Evidence: `repository-map`, `constraints-report`

## `security`

Review secrets, authentication, dependencies, network access, permissions, and fail-closed behaviour.

- Status: `shadow`
- Model policy role: `evaluator`
- Risk tier ceiling: `L0`
- Skills: `security-audit`
- Evidence: `security-report`, `secret-scan`

## `verifier`

Run tests, lint, builds, smoke checks, and capture reproducible exact-command evidence.

- Status: `shadow`
- Model policy role: `evaluator`
- Risk tier ceiling: `L0`
- Skills: `verify-test`
- Evidence: `test-results`, `lint-results`, `build-results`
