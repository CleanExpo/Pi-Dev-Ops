# Fleet adoption through existing Pi-Dev-Ops capability

The operating input version is a pinned source commit plus exact file hashes.
Use host-native paths and the existing skill ownership, installer and mesh paths
to adopt it. A reachable device, installed CLI or healthy server alone does not
prove that Pi-Dev-Ops is operational or that a running LLM loaded the new inputs.

## One verified host at a time

1. Inventory the named device through the existing device connector. Record the
   native home, OS, instruction roots, relevant file types/modes/hashes and Git
   HEAD/index. Read instruction files only; keep auth, env, settings, hooks,
   model defaults and host-specific Codex instructions outside the input pack.
2. Pin the input pack to the reviewed source commit. Compare every live target
   with its recorded original before any target write. Unexpected file, directory,
   symlink, missing original or changed mode is a conflict requiring a new review.
3. Stop other writers for those instruction paths. Apply only the reviewed files,
   with byte backups before the first target change, an immediate preimage check,
   preserved modes and per-file hash readback. Keep the Git index and HEAD intact.
   The temporary application helper uses cooperative locks and per-file changes;
   it is not an atomic transaction against writers that ignore those locks.
4. Move the old automatic Anthropic reference out of `rules/` only after preserving
   its original bytes and verifying the installed on-demand reference is byte
   identical. Retain host-specific rules such as context-ceiling guidance.
5. Run offline instruction checks, independently read back exact hashes and retain
   the application receipt and recovery command. Recovery first compares current
   files with the applied hashes and refuses to overwrite later user edits.
6. Start a fresh session for loaded-input verification. An optional Codex task
   profile is installed as an explicit choice; it does not change the default
   model, account, permissions or runtime. No service restart or inference is
   implied by an input-file application receipt.

The 2026-10-10 MacBook packet covers 19 writes and one preserved reference removal:
12 Claude input assets, three global Judge/SPM policy files, three optional Codex
profiles and the native Hermes SOUL. Mac-mini Hermes profile files on external
storage are not evidence that any Windows runtime has adopted them. Historical
absolute backup paths in evidence references remain historical provenance.

## Continuous adoption when Pi-Dev-Ops is ready

The cached estate revision `08209267` already contains `skills-library/skills/HOMES.json`,
skill ownership checks and mesh preflight/self-update paths. This is a code-audit
reference, not proof of current deployment. Confirm the current canonical tree,
library pin and node revision before extending those existing paths.

Respect `HOMES.json`: `context-cockpit`, `judge` and `spm` belong to the library;
machine-local skills retain their host ownership. Do not hand-edit the generated
ownership file, replace real skill directories with symlinks, or mix a stale
library pin with a newer Pi-Dev-Ops tree. Existing installer dry runs and approved
skill-promotion reports identify conflicts before application.

Before runtime adoption, bind readiness to the deployed revision, current caller
account with included usage, workspace/trust admission, current required CI and
independent exact-candidate review. Honor STOP/HOLD, active ownership and the
existing cost/release gates. Mesh self-update already refuses branch/dirty-tree
updates and uses preflight and rollback; do not bypass those protections or start
another sync daemon, poller or runner for this modernization.

Each host receipt records input installation, source version, loaded-input proof,
runtime readiness and benchmark status independently. Disconnected hosts remain
pending catch-up. When reachable, collect fresh preimages, reconcile local changes,
use the existing installation path and run that platform's checks. A queued pack
or copied Windows profile on a Mac is not a completed Windows rollout.

## Acceptance and learning

Use `templates.md` for owned gaps and execution receipts and `benchmark-gates.md`
for equivalent before/after tasks. Bounded development uses its explicitly approved
lower score floor; promotion requires 95+ and the quality target remains 100.
Increase rigor with promotion scope and evidence, and retire duplicated guidance
only after its constraints and recovery information have a verified home.

Report measured accepted-task throughput, interventions, elapsed time and observed
usage with sample counts. Until comparable runtime receipts exist, the 10x result
remains a target. Write learnings to the existing project documentation and retain
the exact source/host receipts for the next adoption check.
