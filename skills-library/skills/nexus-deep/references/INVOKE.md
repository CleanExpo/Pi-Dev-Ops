# Invoking NEXUS DEEP

**Today:** `nexus-deep` is a discoverable skill candidate. It does not automatically register `/deep` on every CLI. Neither CLI nor prompts are privileged enforcement.

## Natural language
- "Nexus, deep audit CARSI checkout, list observed blockers and evidence."
- "Deep build RestoreAssist floor-plan export. Draft PR only, do not deploy."
- "Deep challenge this PR, test claims and propose different approaches."
- "Deep simplify this module and show before/after speed, test outcomes and dependencies."
- "Deep status: task ID, owner, confidence, red flags and permissions."

## Claude (after command registration)
```text
/deep audit <repository>
/deep build <accepted work item>
/deep challenge <PR>
/deep verify <SHA>
/deep status <task-id>
```
The **command candidate** is `commands/deep.md`. An installer must validate the live CLI before wiring. Until then invoke by mentioning the skill name.

## Codex
Ask it to read the repository `AGENTS.md` route and `skills/nexus-deep/SKILL.md`. Do not assert `$nexus-deep` works without its skill discovery layer actually loading it.

## Offline CLI reference
```bash
python3 skills/nexus-deep/scripts/nexus_deep_cli.py init --repo . --tier T1 --task "Audit a feature" --out /tmp/nexus-deep-task.json
python3 skills/nexus-deep/scripts/nexus_deep_cli.py status --manifest /tmp/nexus-deep-task.json
```
`init` creates **PROPOSAL** only. `status` always returns `ENFORCEMENT_UNPROVEN`; do not use it to authorise edits or mark done.

## Installation visibility
After PR approval and merge, verify `skill-selector` discovery, actual command registration per machine, hooks, CI and one end-to-end negative test before describing the installation as active.
