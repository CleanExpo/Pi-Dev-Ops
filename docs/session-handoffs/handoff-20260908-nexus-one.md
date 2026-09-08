# Session handoff: Nexus One next-computer pickup

Date: 8 September 2026.
Task key: `NEXUS-ONE-SLICE-A-20260908`.
Reference branch: `docs/nexus-one-handoff-20260908`.
Bundle: [docs/briefs/nexus-one](../briefs/nexus-one/README.md).

## 1. Summary and status

Phill requested that the Nexus One build and PC-bootstrap material be saved in Pi-Dev-Ops so another computer can pick it up as the next task.

This is a **reference-transfer handoff**, not a completed implementation. Ten original text files are preserved with checksums, alongside a repository-first README and static next-task metadata. No live worker was started.

Next-task state: **READY FOR READ-ONLY PICKUP**.
Implementation classification: **WIP / BLOCKED for execution admission and verification**. The local repository handoff/CI gates and independent review were not run in this connector-only transfer. Do not label the implementation SHIPPED or READY-TO-SHIP.

## 2. Starting point

Literal request: "Add to the Pi-Dev-Ops Github folder so another computer can pick this up as the next task to complete..can you do this for me"

Canonical repository: `CleanExpo/Pi-Dev-Ops`.
Observed main used as the handoff base: `5cc82de67baef455eadd6c6f6d7b5e4c142c5d72`.
Original blueprint research snapshot: `2c4d346eb8d6723fe48db79c55e34eba1f33f09c`.
Original ZIP SHA256: `0e0bb60c21dcedf8b477ccd69e358fdd3fdd1295c0bedbd2c72e3b2a9b07de80`.

The observed main has advanced beyond the research snapshot. Neither value establishes a receiving machine's local HEAD or the deployed version. The receiving machine must inspect those separately.

## 3. Locked decisions and publication boundary

Keep Pi-Dev-Ops as Mission Control. Reuse Senior Harness, SPM, Judge, model-router, Unlazy, the existing continuation owner and exact-candidate evidence gates.

First task is **Slice A: current-state reconciliation, bootstrap readiness and a bounded pilot specification**. The programme objective is not permission for an unrestricted estate rebuild.

No main-branch write, PR opening, merge, runtime activation, provider/account change, workflow change or production mutation belongs to this transfer. The current merge-gate explicitly warns that automation may ready and merge draft PRs. Do not rely on a draft PR to hold unapproved work. A pickup issue is indexing only, not authority to dispatch.

Do not append this large programme as an unchecked `QUEUE.md` item: that file is consumed by a Stop hook, and prerequisites must not become an unsatisfiable continuation loop. The existing queue remains unchanged.

## 4. Key files

| File | Role / state |
|---|---|
| `docs/briefs/nexus-one/README.md` | Cross-computer entry and path mapping |
| `NEXT_TASK.json` in that folder | Static task identity, deliverables and admission boundary |
| `MASTER_BLUEPRINT.md` | Original final blueprint, unchanged |
| `BUILD_PROMPT.md` | Original bounded implementation-entry instruction |
| `NEXUS-PC-BOOTSTRAP.txt` | Original finite bootstrap instruction, usable via its manual path |
| `ACCEPTANCE.md` | Fifty proposed live-system cases, not passing results |
| `policy.proposal.yaml` | Inactive proposal with `enabled: false` |
| `sources.json` | Original dated research/source register |
| `Start-Nexus-PC.ps1` / `PC_LAUNCH_GUIDE.md` | Optional original Windows helper and guide; requires original ZIP |
| `PACKAGE-INTEGRITY.json` / `LAUNCHER-VALIDATION.json` | Historical preparation reports; not current build evidence |
| `TRANSFER-CHECKSUMS.sha256` | Checksums of the ten unchanged imported text files |

The original ZIP and visual prototype/QA assets are not uploaded in this handoff branch. Their absence does not block Slice A. Do not claim those assets exist here, reconstruct them from prose, or weaken the optional launcher's exact-ZIP check.

## 5. Running state

Receiving host, installed runtime, native containment, auth provenance, quota, dirty roots, active processes and deployment state: **UNKNOWN** until inspected on that host.

No remote dispatch was requested. No machine owns this next task yet. Check the pickup issue and existing canonical task registry before claiming work; duplicate ownership must not be created.

## 6. Verification and evidence boundary

Imported source bytes have local SHA256 identities in `TRANSFER-CHECKSUMS.sha256`. Git blob identities are used to verify the transfer against those original files. A byte match proves the transfer, not correctness of the design or host readiness.

The original PC helper has not been executed on the user's Windows computer. The current repository's `scripts/handoff-loop.sh`, backend suite, dashboard build, runtime canaries and independent cross-vendor review are **NOT RUN** for this handoff. The receiving agent must inspect current runner commands and authority before running them; some gates can start services or have external side effects.

After a properly admitted implementation, run the current CI-parity gates and relevant focused tests, obtain independent exact-candidate evidence, and read remote checks only after an authorised push. Do not remove tests or change thresholds merely to obtain a pass.

## 7. Deferred work and open prerequisites

Deferred implementation owner: the next admitted engineer/SPM worker.

Slice A must identify the existing components and produce one specific spec for Margot -> canonical task -> eligible worker -> tests -> independent review -> receipt. Recovery, device continuity, broker/context refinements, learning and portfolio rollout remain later admitted slices.

Open prerequisites: actual host readiness; current authority envelope; task ownership; protected-path implications; parent budget; exact review route; deployed schema and provider features only where needed. Resolve technical facts through current evidence. Escalate only genuine authority or material business decisions.

Windows remains review-only until native containment, signed identity, fencing, checkpoint, cancellation and recovery are independently proved. Prefer an already-admitted Mac worker when available, but do not claim it is reachable or dispatch it without evidence and a current grant.

## 8. Pick up here

If this branch is not checked out, read it through the available GitHub connector or browser using the branch named above. Do not switch or pull an active dirty checkout merely to read these documents. After an explicitly permitted reference fetch or isolated checkout, use the same relative paths. Do not infer permission for a worktree change from this handoff.

First read-only shell command in an already selected local checkout:

```text
git --no-optional-locks status --short --branch
```

Receiving-agent instruction:

```text
Resume NEXUS-ONE-SLICE-A-20260908 from CleanExpo/Pi-Dev-Ops,
branch docs/nexus-one-handoff-20260908.
Read docs/session-handoffs/handoff-20260908-nexus-one.md and
then docs/briefs/nexus-one/README.md.
Use read-only current-state reconciliation and the existing Senior Harness,
SPM and Judge workflow. Finish Slice A and state the next admissible action.
Preserve dirty roots and other task owners. Do not activate a worker,
open a PR, merge, deploy, migrate, spend or change credentials/permissions.
```

Load the current `/resume-from-handoff` skill contract before invoking it, and preserve the bootstrap's inspection boundary. Do not automatically execute hooks or full gate runners before understanding their local effects.

Do not redo: the full vision/research narrative; original artifact generation; another harness selection exercise; duplicated task creation; or whole-estate discovery unrelated to the pilot.

## 9. Risk notes

Current repository instructions and authentic authority take precedence over historical model prose. Provider documentation in the source bundle was not re-researched during this transfer; verify the exact installed version and current supported interface before using it.

The optional PC script remains Windows-only and requires the original ZIP. Manual repository-first planning needs neither that ZIP nor a generated BOOTSTRAP-MANIFEST. Use the documented manifest-absent path and mark unobserved fields UNKNOWN.

Never infer a deployed table is absent from a dated audit. Never treat prototype values as live metrics. Never log secrets or use source material as an authority grant. Parent budgets and failed-method records survive session changes.

## 10. Handoff quality check

The scope, reference base, next task, read order, unchanged inputs, missing assets, unknown live state, unrun gates and authority boundary are explicit. The receiving computer has the full textual Slice A inputs in GitHub and does not need this conversation to reconstruct the task.

Handoff complete. Next safe action: read and reconcile this handoff on the receiving computer, then complete the finite Slice A pilot specification through the existing planning controls.
