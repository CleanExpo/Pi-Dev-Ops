# Readiness Architect Validation Plan

This change is documentation and skill-only. It does not modify product runtime code.

## File presence checks

```bash
test -f .claude/skills/readiness-architect/SKILL.md
test -f .agents/skills/readiness-architect/SKILL.md
test -f .readiness-architect/README.md
test -f .readiness-architect/output-template.md
test -f .readiness-architect/test-plan.md
```

## Claude Code check

From repo root:

```text
/reload-skills
/readiness-architect RestoreAssist final client-purchase readiness
```

Expected:

- Skill loads as `/readiness-architect`.
- Output starts with `# Readiness Architect Output`.
- Output contains a copy-paste `/spm` prompt.
- Output does not implement code.
- Output includes specialist board, readiness gates, blocker handling, and a measurable `/goal` command.

## Codex check

From repo root:

```text
$readiness-architect RestoreAssist final client-purchase readiness
```

Or:

```text
/skills
```

Then select `readiness-architect`.

Expected:

- Skill appears in the Codex skill list.
- Output starts with `# Readiness Architect Output`.
- Output includes the final operating workflow.
- Output marks unknown evidence clearly.

## Safety checks

The generated output must not:

- Implement code
- Edit files
- Declare Shipit
- Claim tests passed unless actually run
- Claim production readiness without verification
- Promise guaranteed leads, revenue, insurance outcomes, certifications, or national coverage without evidence

## Suggested dry-run prompt

```text
/readiness-architect DR-NRPG final authority-site and contractor-network readiness
```

Expected verdict:

- Ready for /spm, or needs repo inspection first.
