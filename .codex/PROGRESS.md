# Mission Control readiness integration

User scope: complete the original 143 changed/new files before the next five updates.

The original shelf is delivered: [PR #784](https://github.com/CleanExpo/Pi-Dev-Ops/pull/784) merged as `bb23e877`. All 143 files were reconciled; the old source shelf and 890 legacy artifacts were preserved in verified local archives. The next five remain deferred while post-merge readiness findings are closed.

Current continuation: `fix/readiness-parent-failure-cleanup`, based on Main `9e4df735` (automated wiki successor to the merge). Repairs close unexpected parent exits leaving child builds alive and backend smoke revision admission missing authentication. Existing worker cancellation and smoke helpers are reused; exact-SHA admission and public health privacy are preserved. Combined Linux verification passed 6,561 tests (20 skipped, two expected failures), golden evaluations passed 129 (one skipped), safe FastAPI import and independent review passed. Read the continuation PR's exact-commit checks and delivery state before calling these repairs shipped.

- Integration branch: `feat/mission-control-readiness-integrated`, based on Main `2ca26817`.
- Original paths: 138 integrated, four already delivered by #783, one superseded by Main's checkpoint helper.
- Full Linux suite: 6,551 passed, 20 skipped, two expected failures.
- Dashboard: 503 tests plus build/typecheck/lint passed.
- Golden evaluations: 129 passed, one skipped. All reviewed implementation slices passed independent review.
- The tracked per-file ledger is `docs/plans/mission-control-readiness-files.json`; detailed evidence is in `docs/plans/mission-control-readiness-verification.md`.

The original shelf at `D:/Pi-Dev-Ops` has a verified recovery bundle and durable `refs/backups/readiness-delivered-pr784` recovery ref. Do not merge its eighteen historical commits or resume those archived files as new work. Current Main recovery/leases, planner admission, routing/Model Fabric/Margot, Control/LiveWall and health liveness have been preserved in the integration.

Activation remains separate: Docker's extra bubblewrap/socat packages await explicit dependency approval; Main's 14-check policy is prepared and independently reviewed but not applied; supported-host generation and distinct verified reviewers require real operational evidence. Native Windows generation is explicitly blocked. No live provider/billing claims follow from tests.
