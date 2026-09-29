# TypeSafe — pinned copy

Pulled 2026-09-29 so the Jev work in `evals/jev_constitution/` has the vendor's docs and
skill on hand. Pinned, not installed from the vendor marketplace: a marketplace plugin
updates itself, and a skill is instructions an agent follows, so a change upstream
would change agent behaviour with no review here. This settles decision D2 in
`docs/plans/idea-to-live/handoff.json` for Pi-Dev-Ops: pinned copy.

| File | Source | Version |
|---|---|---|
| `llms.txt` | https://docs.typesafe.ai/llms.txt | fetched 2026-09-29 |
| `llms-full.txt` | https://docs.typesafe.ai/llms-full.txt (all docs pages in one file) | fetched 2026-09-29 |
| `skills/` | https://github.com/typesafe-ai/skills | commit `65a39f393687675ce170e6094757de20370365b9`, plugin `0.5.7`, MIT |

The skill is active in this repo through `.claude/skills/typesafe-ai` (a relative
symlink to `skills/skills/typesafe-ai`). It was read in full before linking: guidance
on primitives, state, thresholds and composition, no tool calls or install steps.

The skill itself says the live docs are the source of truth. These copies are for
offline reference and review; check the live page before relying on a version-specific
detail.

To update: re-fetch both `llms` files, download the new skills commit, read the diff of
`SKILL.md` before replacing it, and change the table above.
