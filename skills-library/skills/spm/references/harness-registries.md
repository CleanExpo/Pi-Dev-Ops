# Harness registries

Carried from main (#103) into the spm-core workflow, step 3 "Search before you build".

Glob `.claude/skills/*/harness.json` in the target repo and `~/.claude/skills/*/harness.json`. If a
harness's `triggers` match the request (e.g. Synthex `shortform-video-harness` for any
viral/short-form/social video work), load it, run its validator if it ships one (a failing validator
means the map is stale: say so, don't trust it), and use it as the skeleton:

- its nodes (skills, tools with file:line refs, inputs/outputs) become §6 Existing capability and
  §17 Implementation sequence;
- node order and `depends_on` shape §9;
- every `gap`/`stub`/`partial` node on the path becomes a §5 scope item or a §8 judge-challenge risk
  quoting its `build_hint`;
- every `gate`, `spend` and `human_gate` becomes a §15 acceptance criterion.

Name the harness file and its `last_verified` date in §2. No match ⇒ continue as normal.
