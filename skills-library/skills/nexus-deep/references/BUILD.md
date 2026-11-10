# NEXUS DEEP build and rollout

**Phase 1 (this branch):** introduce discoverable skill, docs, offline proposal CLI, regression tests and catalog route. No hooks installed or services activated. Do not confuse a passing local test with live enforcement.

## PR sequence
1. **PR1 Adapter:** existing repository collision audit; skill + exact routing + command candidate + docs + offline tests. Preserve existing dirty changes.
2. **PR2 Trusted control:** review the existing Done mutation-hook installation and missing wiring; add idempotent installer only if necessary. Test unsupported tool surfaces, signed objective+SHA receipts, replay/forgery, dependency-bloat regressions, hook failures and bypasses. Require a trusted CI source.
3. **PR3 Independent senior council:** route to a minimal useful set of engineering lenses, then model capability tournament. Separate each reviewer from builder context; use existing JEV/adversary implementation, not copies.
4. **PR4 Mission Control:** persist task/evidence/blocker/approval status with actual observed task IDs, cost and model source; include read-only inspectability.
5. **PR5 Canary and scale:** one low-risk project; observe → warn → enforce following owner approval, rollback drill and two benchmark cycles.

## Fleet
Mac Mini external SSD is canonical work storage only **after** health check; GitHub is versioned source. MacBook is the operator and emergency isolated branch location; PC runs independent tests and Playwright where useful. Do not copy every repository onto every internal disk.

## Accept/reject
- No duplicate orchestration state.
- Existing skill discovery works without loading hundreds of skill bodies.
- Attacks against receipt signatures, stale data, changed HEAD, unauthorized actions and failed reviewers return BLOCKED/UNPROVEN.
- No deployment/merge/spend/delete without authenticated approval.
- UI changes show reproducible browser runs, not screenshots invented by a model.
- Cost, code size, tests, latency and rework improve against locked baselines.
- Before promotion, `donectl doctor` reports hooked enforcement on each target surface.

## Rollback
Disable just the new adapter/installer using reviewed revert and native configuration; preserve evidence. Never revert unrelated user changes.
