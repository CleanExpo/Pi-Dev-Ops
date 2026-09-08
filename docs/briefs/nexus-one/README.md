# Nexus One: next-computer planning bundle

Prepared for the cross-computer handoff on 8 September 2026.

**Start here:** [next-task handoff](../../session-handoffs/handoff-20260908-nexus-one.md).

Task key: `NEXUS-ONE-SLICE-A-20260908`.
Branch: `docs/nexus-one-handoff-20260908`.
Status: handoff/reference material; implementation not admitted or started by this upload.

## Next task

Complete **Slice A: current-state reconciliation, launch-readiness assessment and the first bounded Nexus One pilot specification**. Use the existing Senior Harness, SPM and Judge. Do not start another architecture rewrite or an unrestricted portfolio rebuild.

The intended first delivery journey, after separate admission, is Margot -> one canonical task -> one eligible worker -> deterministic tests -> independent review -> receipt.

## Read order

1. The linked handoff and `NEXT_TASK.json`.
2. Current repository instructions and the current canonical skills they name.
3. `BUILD_PROMPT.md` and `NEXUS-PC-BOOTSTRAP.txt`.
4. `MASTER_BLUEPRINT.md` once, with `ACCEPTANCE.md`, `policy.proposal.yaml` and `sources.json` as focused references.

All relative blueprint references resolve within this folder. For manual cross-computer pickup, use the bootstrap's documented manifest-absent path: the selected repository is `CleanExpo/Pi-Dev-Ops`, but the actual host path, current branch, dirty state, installed tools and readiness must be observed on the receiving computer. Do not fabricate a BOOTSTRAP-MANIFEST or crawl personal directories. No original ZIP is required for this read-only planning path.

## Preserved source files

The ten files listed in `TRANSFER-CHECKSUMS.sha256` are unchanged copies of the previously delivered blueprint/package or PC-launch supplement. `PC_LAUNCH_GUIDE.md` is the launch supplement's original README under an unambiguous name. The checksum file covers those ten imports, not the newly authored handoff metadata.

`Start-Nexus-PC.ps1` is an optional Windows-only reference helper. It still requires the exact original `Nexus-One-Implementation-Package.zip`; its ZIP hash and behaviour were not changed. Do not weaken its checks, generate a replacement ZIP or use it on a Mac. Its native Windows/Claude execution remains untested. Use the repository-first read-only path above when the ZIP is not present.

The original ZIP, HTML prototype, prototype QA assets and PNG screenshots are **not included in this handoff branch**. They remain in the original download. None is needed to complete Slice A. The blueprint's visual/QA references describe that original package, not live-system acceptance or files silently supplied here.

## Snapshot and provenance

The blueprint's research snapshot is `2c4d346eb8d6723fe48db79c55e34eba1f33f09c`. This handoff branch starts from the later observed main `5cc82de67baef455eadd6c6f6d7b5e4c142c5d72`. These are different roles; never force the active checkout back to the research snapshot. Provider documents and dated operational claims must be rechecked when relevant to implementation.

`PACKAGE-INTEGRITY.json` and `LAUNCHER-VALIDATION.json` are preserved reports about preparation of the original download, not current repository test results. They do not prove worker readiness, live billing, CI, a deployed schema or independent approval.

## Publication and execution boundary

This branch stores files only. The runtime configuration, live queues, `QUEUE.md`, workflows, existing skill registries and application code are unchanged.

The current `skills/merge-gate/SKILL.md` warns that even draft PRs may be automatically readied and merged. For that reason this upload does not open a PR, merge or enable auto-merge. Read/reconcile that gate and obtain the required authority before any future PR action.

An issue is a pickup index, not a signed dispatch lease. Check for an existing task owner before continuing; do not create another competing repair branch or task. Windows remains review-only until the required native controls are proved. No merge, deployment, external send, production migration, new spending, credential change or remote worker dispatch is authorised by these files.
