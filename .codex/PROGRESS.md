# Mission Control readiness integration

User authorization: complete the 143 changed/new files before the next five updates.

Active checkout: `D:/pi-wt-readiness-integrated`.
Branch: `feat/mission-control-readiness-integrated`.
Base: `2ca2681719b4e475e33f6a09e67c6d0ab1bf1144`.
Original shelf: `D:/Pi-Dev-Ops`, preserved read-only; verified recovery bundle remains there.

The old branch is hundreds of commits behind Main. Changes are reconciled by behavior onto a fresh checkout, preserving current recovery/leases, planner admission, Model Fabric/Margot, Control/LiveWall, and health liveness.

Completed Windows fix PR #783 is already on Main. Original readiness paths are accounted in `.harness/readiness-integration-ledger.json`; four are delivered by that PR. All143 original paths are accounted:138integrated,4alreadydelivered,1superseded by Main's checkpoint helper. The tracked ledger is docs/plans/mission-control-readiness-files.json.

Current phase: draft PR candidate and exact-commit CI verification. Provider, SDK, documentation/runtime and dashboard lanes have focused passing evidence. Parent health/autonomy/spec delivery suite: 64 passed. Dashboard503tests/build/types/lint passed after complete phase-schema validation; independent review PASS. Required CI admission108passed/1skip and independent review PASS. Recovered/manual-task ownership and Git cancellation corrections passed focused tests and independent review. Full Linux regression and exact-commit CI remain active. These are local results, not deployed-runtime evidence.

Pending: final lane reports, complete ledger, static/security checks, independent review, exact-candidate CI, PR delivery and Main verification. Explicit approval of Docker's required bubblewrap/socat packages is pending; no packages installed or added without that approval.

Do not restart from the old shelf or cherry-pick its eighteen historical commits. Do not reset/remove source worktrees or claim production autonomous readiness from local tests.
