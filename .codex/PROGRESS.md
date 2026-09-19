# Mission Control readiness integration

User scope: complete the original 143 changed/new files before the next five updates.

Implementation and local verification are complete. Delivery is tracked by [PR #784](https://github.com/CleanExpo/Pi-Dev-Ops/pull/784); read its current state and exact-commit checks before declaring shipping or starting the next five.

- Integration branch: `feat/mission-control-readiness-integrated`, based on Main `2ca26817`.
- Original paths: 138 integrated, four already delivered by #783, one superseded by Main's checkpoint helper.
- Full Linux suite: 6,551 passed, 20 skipped, two expected failures.
- Dashboard: 503 tests plus build/typecheck/lint passed.
- Golden evaluations: 129 passed, one skipped. All reviewed implementation slices passed independent review.
- The tracked per-file ledger is `docs/plans/mission-control-readiness-files.json`; detailed evidence is in `docs/plans/mission-control-readiness-verification.md`.

The original shelf at `D:/Pi-Dev-Ops` has a verified recovery bundle. Do not merge its eighteen historical commits or resume those old dirty files as new work. Current Main recovery/leases, planner admission, routing/Model Fabric/Margot, Control/LiveWall and health liveness have been preserved in the integration.

Activation remains separate: Docker's extra bubblewrap/socat packages await explicit dependency approval; supported-host generation and distinct verified reviewers require real operational evidence. Native Windows generation is explicitly blocked. No live provider/billing claims follow from tests.
