# Context operating update — 10 October 2026

Task: independently test the Nate Herk transcript's proposals against current first-party guidance and existing Nexus operations (RA-7947). Scope is reversible instruction/input updates; the full runtime migration remains in progress.

## Reviewed and changed

Reviewed global CLAUDE/AGENTS/index, Done and adoption rules, context-cockpit, installed release/proof/control guidance, Hermes default + five local profiles, and current Codex/Claude configuration/help. Official source research and the Pi-Dev-Ops offline doctor are recorded in the parallel `llm-operations-20261010` worktree.

Changed the global entry point, on-demand index wiring, portable Done command, context-cockpit and conditional references. Historical Anthropic adoption and release incidents are preserved outside auto-loaded rules. Added a bounded checker with containment/guard negative controls and registered its suite in the existing CI manifest. Manifest coverage lists 60 suites: 44 run and 16 pre-existing skips; listing is not execution of that full suite. Added three optional Codex v2 effort-profile templates (medium/high/xhigh), inheriting model/auth/tools/base policy; the user's ultra default is retained.

Six Hermes SOUL templates replace Q2-as-current facts, mandatory questions/reconfirmation, routine long planning and the CI-bypass offer. They retain profile roles, Margot identity/voice, the June 2028 objective and founder/release boundaries. Historic business snapshots remain available for recovery, not live evidence. Templates for Windows-named profiles are local Mac copies; remote fleet rollout is not verified.

## Validation and claim limits

Root checker: seven unittest methods passed in700.732 seconds. Peer independently reran the same seven methods in620.126 seconds and reviewed policy/containment fixes. Guard mutations are fixture/control evidence, not a proof of model compliance. `check-context-entrypoint.py` observed 11,558 bytes versus 40,622 tracked baseline bytes (about 71.5% reduction); actual loaded provider tokens are unknown. A local 1,500-byte context-ceiling rule is outside the tracked closure and remains preserved. No output-quality improvement is asserted.

CLI observations: Claude 2.1.295, Codex 0.160.1; configured ordinary models are current. Sign-in/quota, model selection and inference liveness are separate facts. Browser account checks timed out; current Claude included-billing compatibility remains unknown. A first standalone Codex Sol/medium health probe timed out 180 seconds. The bounded no-MCP retry also failed to return an attributable response. Its real diagnostics show a locked logs database, ignored `features.codex_cloud`/`sandbox_permissions` settings, and a skills-budget warning: all descriptions removed and 69 skills omitted. These are observed bottlenecks, not proof of a single timeout cause. Logs/receipts are on external storage. No TLS bypass, credential change or third attempt was made.

## Source and recovery

Source branch: context-modernization-ra7947; starting SHA b1c374d5e1d1ff99a3379008483d9ad6e46c8824. Source commit identity and deployment readback belong in the external rollout receipt, not a self-referential source document. No push/PR/merge or service restart is implied by a local commit or instruction copy.

Byte-exact backups: /Volumes/Storage Unit/Application-Data/Codex/llm-modernization-20261010/backups/skills-library and backups/hermes. Active deployment must compare current bytes to recorded originals, copy only these candidate paths from committed source, preserve local context-ceiling/settings/hooks/auth/dirty work, and record readback hashes. Restore only if active bytes still match deployed hashes; never overwrite later user changes. Fresh sessions are required to observe startup instruction changes; existing loaded context is not retroactively reduced.

## Remaining requirements

The current provider print adapter ignores requested model/cwd and reports invented zero usage; API adaptive/tool/effort contracts and duplicated model registries need tested runtime patches. Legacy farm flags/health receipts are invalid. Mission Control has stale account/billing and runner-state evidence. Keep startup/runtime activation held until fresh account-specific included-access, adapter regressions, independent exact-tree release gates and representative old/new quality comparisons pass. Native compaction plus task/checkpoint/receipt templates replace repeated universal playbook injection; do not bypass authority or privacy floors.
