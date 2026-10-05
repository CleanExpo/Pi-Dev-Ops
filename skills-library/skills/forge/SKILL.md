---
name: forge
description: Use when a new skill must be created from a decision, verdict, or capability gap — the user says "forge a skill", "turn this verdict into a skill", "build a skill for X", or pantheon/nexus hands over a VERDICT recommending one. Produces a secure, evaluated, quarantined skill package with an AI-BOM.
allowed-tools: Read, Grep, Glob, LS, Bash, Edit, Write, Agent, Skill
---

# forge — verdict → secure, evaluated, registered skill

Eight gated phases; no phase starts until the previous one's criterion is met, and no
skill leaves quarantine without the human. House law applies throughout:
`skill-authoring-standard` (four gates + frontmatter SSOT) and the Fable-5 restraint
rules already in the estate playbook — minimum skill that closes the gap, nothing
speculative. Australian English in all generated content.

**Hard refusals (§A):** forge will not emit a skill that executes attacker-controllable
input, ships a destructive default action, contains offensive/exploit code, or whose
purpose is to avoid, weaken, or probe a safeguard. On `stop_reason:"refusal"` during
any generation subtask: re-dispatch that subtask to Opus 4.8 (`Agent` with
`model: "opus"`) — fall back, never evade.

## Phases

1. **Discovery.** State the capability gap in one sentence + who invokes the skill and
   when. *Done when:* gap + invoker + trigger written down.
2. **Spec gate.** Run `new-spec` (grounded spec, not a template) — no skill without an
   approved `spec.md`. *Done when:* the human has approved spec.md.
3. **Design.** Lightest viable archetype per the authoring standard (command-skill /
   agent-role / plain-technique); depth pushed to `references/`; every step gets a
   completion criterion. *Done when:* design fits the frontmatter schema and ≤200-line cap.
4. **Eval first (§D).** Write `eval.md` BEFORE the body: 3–7 executable checks (command +
   expected result) that define "works", plus one negative case. Run them now to confirm
   they FAIL pre-build (red). *Done when:* eval exists and is demonstrably red.
5. **Implementation.** Write SKILL.md + references + scripts in
   `~/.claude/skills/in-progress/<name>/`. Restraint rules bind: no features beyond the
   spec, no premature abstraction, validate at boundaries only. *Done when:* files exist.
6. **Security scan.** `python3 ~/.claude/skills/forge/scripts/scan.py <dir>` — checks map
   to [references/scan-checklist.md](references/scan-checklist.md); emits `ai-bom.json`.
   FAIL ⇒ fix and rescan; a skill that cannot pass stays quarantined forever.
   *Done when:* scan exits 0, fresh, this turn.
7. **Eval + smoke (§C).** Run the phase-4 eval fresh — all green now; stamp each check via
   the estate evidence tool (`evidence.py`). If results vary across runs, note variance
   and tighten until stable. *Done when:* eval green with run-stamped artifacts.
8. **Register (human-gated).** Prepare — never execute — promotion: the catalogue lines
   (README + router row if entry-point), the `git mv` out of `in-progress/`, and the
   commit. Verify `brain.js skills` WOULD stay green (run it). Hand the human the exact
   commands. *Done when:* promotion pack handed over; skill still in quarantine.

## Method references (read on demand)

- Eval-first discipline + variance analysis: [references/eval-first.md](references/eval-first.md)
- Scan checklist ↔ OWASP mapping: [references/scan-checklist.md](references/scan-checklist.md)

## Write-back

One vault Outcome note per forged skill (what gap, what shipped, eval results, AI-BOM
path). Provenance: every external pattern used is recorded in the AI-BOM by repo+commit.
