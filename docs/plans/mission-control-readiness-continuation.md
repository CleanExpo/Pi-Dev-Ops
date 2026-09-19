# First-five continuation: close real user-journey gaps

> Integration update, 2026-09-19: the owner approved completion and delivery of the 143-file shelf onto current Main. Active branch: `feat/mission-control-readiness-integrated`, based on `2ca26817`. Earlier branch names, counts and completion statements below are historical. Current evidence is in `mission-control-readiness-verification.md`. The next five remain deferred until this delivery is verified.

Approved scope: continue the original five improvements before starting the next five. The user's required outcome is one Mission Control entry point for autonomous use of the existing ecosystem. The previous local-completion claim was too broad: passing the inspected tests did not prove the actual Build journey or supported generation path.

Reconciliation: MATCH. Same `feat/mission-control-readiness` branch, baseline `d0bd87ba`, and preserved dirty implementation. No conflicting changes or deployment. Previous test evidence remains valid for that snapshot; new regression evidence is required for the gaps below.

## Fix plan and ownership

1. Execution/subscription: bind SDK generation to the same explicitly selected and verified subscription CLI and execution environment. Preserve supported-host isolation and tool restrictions. Regressions must cover API/override denial, correct executable/environment, missing/expired subscription and unsupported isolation. Owner: readiness_cancel.
2. Spec routing: replace direct paid OpenRouter dispatch with supported shared routing. Preserve requested-versus-observed model identity, truthful unknown costs and independent panel requirements. Readiness must not equate API-key presence with authorization. Owner: readiness_policy_docs.
3. Actual Build journey: connect the Build form to the existing build lifecycle; analysis failures must stop push/PR/completion. Missing swarm/quality telemetry must remain unknown. Owner: readiness_dashboard.
4. Autonomy evidence: an empty/partial event window cannot score 100%; distinguish polling/launching from verified delivery. Surface execution blockers without model calls or blocking auth subprocesses in health requests. Owner: parent.
5. Verify affected paths together, independent review, then refresh the integrated evidence and handoff. No new paid model dependency, live work dispatch, credential edits, production deployment or policy bypass.

This is a correction within the approved delivery, subscription, execution and truthful-status work. JEV research and the next-five proposal are separate read-only recommendations; do not silently add a metered provider.

## Additional failure injection from independent review

- An incomplete spec build and failed Git command previously reached publication. Repair binds the reviewed tree, commit, push and merge receipt while preserving source ancestry.
- Model-generated import/pytest checks inherited host authority. Repair uses a deterministic Linux/WSL bubblewrap runner with no host secrets/network and bounded process cleanup; Git metadata must be immutable inside verification, and privileged host Git must not execute candidate hooks/configuration.
- Missing test directories cannot count as passing tests. Malformed board prose cannot become approval through substring matching.
- SDK usage now preserves reported estimates versus unknown values, observed model identity and fallback accounting. Unknown spend stops monetary-gated TAO continuation. Dashboard cost consumers preserve nulls.
- Test collection must not load workstation environment files; repository conftest intercepts exact live configuration paths and redirects generated test auth files.

No new dependency was installed. The existing Ubuntu WSL runtime exercised verification isolation with synthetic filesystem/network/process probes. Native SDK isolation and deployed Linux container behavior remain separate, unverified runtime requirements. Dockerfile currently lacks required bwrap/socat, so it is not a deployable autonomous runtime as configured.

## Final disposition

All local repair lanes completed; independent review PASS. Dashboard236passed plus lint/typecheck/build. Combined backend4050passed,21baseline-reproduced failures (one intermittent),11skipped,2expected failures. Runtime activation remains unverified and nothing shipped. See the final verification report and .Codex/PROGRESS.md for evidence and pickup.
