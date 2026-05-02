---
name: agentskills-manifest
description: Export Pi-CEO's skill registry as an agentskills.io-format manifest. Closes Hermes RA-1838 SWARM-009 (open question #5 from the original Hermes brief — answered yes). Future-proofs Pi-CEO if/when it adopts the Hermes runtime via Path C.
owner_role: Curator
status: wave-3
---

# agentskills-manifest

Walks `Pi-Dev-Ops/skills/`, normalises every SKILL.md frontmatter into the agentskills.io v1 schema, writes a single `agentskills.json` (and `.yaml`) manifest at the repo root.

## Why this exists

The Hermes Path C verdict (RA-1838) commits Pi-CEO to running on the Hermes v0.12.x runtime with our policy layer on top. Hermes natively understands the agentskills.io manifest format. If Pi-CEO's skill registry is in that format, switching is a config change, not a re-author.

Independently, the format is a useful interlingua — same manifest can drive a registry browser, search, dependency analysis, deprecation warnings.

This skill is a one-way export today (Pi-CEO → manifest). Two-way sync (manifest → SKILL.md from upstream agentskills.io packs) is a separate Wave 4 concern.

## Manifest schema (agentskills.io v1, distilled)

```yaml
manifest_version: 1
package:
  name: pi-ceo-skills
  version: "0.1.0"        # bumped on every regeneration; semver based on diff shape
  generated_at: ISO-8601
  source: "github.com/CleanExpo/Pi-Dev-Ops"
skills:
  - id: margot-bridge
    description: "..."
    owner_role: Margot
    status: wave-1
    path: skills/margot-bridge/SKILL.md
    sha256: "..."         # of SKILL.md content
    dependencies:
      tools:
        - mcp.margot.deep_research
        - mcp.margot.deep_research_max
      skills:
        - skill.intent-parser
    safety:
      requires_kill_switch: true
      requires_hitl_gate: false
      pii_handling: pass-through  # | redacts | tokenizes
  - id: ...
```

Fields beyond the SKILL.md frontmatter (dependencies, safety) are extracted via lightweight static analysis of the SKILL.md body — looking for tool references in tables, "Owns" blocks, "Safety bindings" section. Best-effort; flagged as `inferred: true` when extraction confidence is low.

## CLI

`python -m swarm.agentskills_manifest` — generates `agentskills.json` + `agentskills.yaml` at repo root.

CI gate: a workflow that regenerates the manifest on every PR touching `skills/` and fails if the committed manifest is stale.

## Versioning

Manifest version bump rules:
- New skill added → MINOR bump
- Existing skill removed → MAJOR bump
- SKILL.md content changed (sha256 diff) → PATCH bump

Persisted in `package.version` field. Stored separately in `.harness/agentskills_history.jsonl` (one row per regeneration, append-only).

## Dependency extraction heuristics

The skill body has tables like:

```
| Tool | mcp.margot.deep_research |
```

The extractor:
- Finds tables in the SKILL.md
- Looks for cells matching `mcp\.[a-z_-]+\.[a-z_-]+` → tool dependency
- Looks for cells matching `skill\.[a-z_-]+` → skill dependency
- Looks for "Owns" / "Calls (downstream)" sections in the topology doc patterns

Confidence floor: if a SKILL.md has no extractable dependencies but the body length is >100 lines, flag `inferred: true` and `low_confidence: true`. User reviews the manifest line for that skill.

## Safety bindings extraction

Three boolean flags + one enum:
- `requires_kill_switch`: true if SKILL.md mentions "TAO_SWARM_ENABLED" or "kill-switch" in a Safety section.
- `requires_hitl_gate`: true if mentions "telegram-draft-for-review" or "review chat" in a Safety section.
- `pii_handling`:
  - `redacts` if mentions "pii-redactor" as a binding.
  - `tokenizes` if mentions tokenization (rare in current codebase).
  - `pass-through` (default) otherwise.

These flags are best-effort. Manual override file: `.harness/agentskills_overrides.yaml` (one entry per skill that needs a hand-coded safety annotation).

## Output locations

- `agentskills.json` — at repo root, machine-readable
- `agentskills.yaml` — same content, human-readable
- `.harness/agentskills_history.jsonl` — version + diff log

## Verification

1. Run `python -m swarm.agentskills_manifest` in the Pi-Dev-Ops checkout.
2. Expect: `agentskills.json` written with 12+ skills (current registry as of 2026-05-01).
3. Expect: every Wave 1/2/3 skill appears with correct owner_role + status.
4. Modify a SKILL.md body, re-run → version PATCH bumps, history.jsonl gains a row.
5. Add a stub SKILL.md in `skills/test-skill/` → re-run → version MINOR bumps, manifest gains a row.
6. Remove the stub → re-run → version MAJOR bumps.
7. Manifest passes the agentskills.io v1 schema validator (offline copy of the schema vendored in `Pi-Dev-Ops/.harness/agentskills_v1.schema.json`).

## When NOT to use this skill

- Importing a skill pack from agentskills.io into Pi-CEO — the reverse direction. Wave 4.
- One-off skill discovery — use `ls Pi-Dev-Ops/skills/` directly.
- Distribution to other portfolio repos (CARSI, RestoreAssist) — those each generate their own manifest from their own registry.

## Out of scope

- Two-way sync (Hermes registry ↔ Pi-CEO registry).
- Skill marketplace / paid distribution.
- Multi-language skills.
- Embedded screenshots / icons in the manifest.

## References

- Closes Hermes RA-1838 SWARM-009 + answers original brief open question #5
- Hermes Path C verdict: `/Users/phill-mac/Pi-CEO/Hermes-Swarm-Recommendation-2026-04-14.md` v0.12.0 Re-evaluation appendix
- Topology: `/Users/phill-mac/Pi-CEO/Second-Brain-Agent-Topology-2026-05-01.md`
- agentskills.io v1 schema (offline-vendored): `Pi-Dev-Ops/.harness/agentskills_v1.schema.json` (to be added with the Wave 3 implementation)
