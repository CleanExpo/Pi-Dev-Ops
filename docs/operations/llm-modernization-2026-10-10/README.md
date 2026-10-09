# LLM operations modernization — 10 October 2026

The safe update provides a secrets-safe offline inventory, smaller task/checkpoint
contracts and corrected current-model/farm guidance. Full estate runtime modernization
and improved model output quality remain unverified; they require adapter, included
access, independent review and fleet receipts.

## Current bottlenecks and evidence

- **Instruction volume:** the initial inventory measured global Codex instructions
  at 3,373 bytes, global Claude at 23,961 bytes, and this repo's AGENTS/CLAUDE at
  12,101/17,754 bytes. Claude imported material adds more; these are source sizes,
  not actual loaded-token measurements. The separate global skills-library input update reduced its measured
  source closure from 40,622 to 11,558 bytes while retaining reviewed normative
  rules; actual loaded tokens and model quality remain unmeasured.
- **Skill discovery:** the initial inclusive global + project inventory found 430
  unique physical SKILL files, 9 symlink aliases and 134,150 name/description
  characters. A provider may load only a subset; this is not a session bill or
  evidence that every catalog character is loaded. References need review using
  Markdown-relative versus repository-root semantics.
- **Source/runtime drift:** local configs already select Codex `gpt-6.1-sol` and
  Claude `claude-opus-5-5`, while inspected route sources retain older identifiers.
  A source literal or config string does not establish live availability. The
  doctor excludes worker names such as `claude-1` from model evidence.
- **Adapter mismatch:** the existing farm pins `o3`, uses an obsolete Codex flag,
  and bypasses Claude permissions. Its documented tmux service differs from the
  daemon-thread implementation. A standalone status command cannot inspect the
  original process's threads; old readiness files can survive it.
- **API contracts:** newer model families differ in effort/thinking/tool support.
  The coordinator found an existing print adapter that ignores requested model/cwd
  and fabricates zero usage, plus adaptive-thinking handling limited to Fable.
  Runtime source correction is required; no blind name replacement is applied here.
- **Runner evidence:** the coordinator observed Mission Control's last END record
  on 9 September with a billing hold and a contradictory recorded-running status.
  No runner PID was proven. The inventory does not read runner env/session files
  or infer current health from that historic receipt.

Source/model facts and URLs are in [vendor-catalog.md](vendor-catalog.md).
The initial external receipt is
`/Volumes/Storage Unit/Application-Data/Codex/receipts/llm-operations-20261010-offline.json`.
It predates final import/reference parsing refinements and later input deployments;
use a new final receipt rather than relabeling old evidence current.

## Run the offline doctor

```bash
source ~/.config/ccw-external-storage.env
cd '/Volumes/Storage Unit/Application-Data/Codex/worktrees/llm-operations-20261010'
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_llm_operations_audit.py' -v
PYTHONDONTWRITEBYTECODE=1 python3 scripts/llm_operations_audit.py \
  --home-root /Users/phill-mac \
  --project-root '/Volumes/Storage Unit/Application-Data/Codex/worktrees/llm-operations-20261010' \
  --output '/Volumes/Storage Unit/Application-Data/Codex/receipts/llm-operations-next-run.json'
```

Output must be a new `.json` on mounted `/Volumes/Storage Unit`; existing receipts
are never overwritten. `--no-cli-probes` avoids even version probes. Optional repeatable
`--skill-root` replaces default skill roots; `--runner-root` reads only known JSON
receipt filenames. Env, auth, sessions, memory and attachments are excluded.
Version probes execute only installed Claude/Codex `--version`, with bounded output
and timeout. They do not establish login, quota, model response or runner health.

The doctor supplements the existing `scripts/markdown_bloat_audit.py` and
`context-cockpit`; it does not create a new inference runner or context compressor.
Its byte/character/4 estimates are deliberately separate from measured tokens.
Instruction scope is named entrypoints plus up to 64 import rows. Auto-loaded
rules, ancestor/nested conditional instructions and actual activation still require
native context inspection; this inventory is not a complete loaded instruction closure.

## Adoption and remaining work

Use [task/checkpoint/evidence templates](templates.md) and the corrected existing
farm skill now. Follow [benchmark gates](benchmark-gates.md) for adapter/schema,
account and fleet changes. The [spec/Judge record](spec-and-judge.md) preserves the
honest full-migration gaps. No production inference, restart, payment, deployment,
cron activation or publication is part of these offline assets.

## Change and recovery boundary

Reviewed in this repository: `AGENTS.md`, `.agents/skills/judge/SKILL.md`,
`.agents/skills/spm/SKILL.md`, `scripts/markdown_bloat_audit.py`,
`scripts/audit_sandboxes.py`, `skills/context-compressor/SKILL.md`,
`skills/closed-loop-prompt/SKILL.md`, `skills/context-cockpit/SKILL.md`,
`skills/pi-dev-ops-model-farm/SKILL.md`,
`skills/pi-dev-ops-model-farm/scripts/model-farm.py`,
`skills/pi-dev-ops-model-farm/scripts/init-farm.sh` and `docs/WIKI.md`.
The doctor's bounded source inventory additionally checks the explicit paths in
`DEFAULT_ROUTE_FILES`; runtime conclusions also use the coordinator's reviewed
adapter/runner evidence. Primary vendor URLs are recorded in the model catalog.
The separate input source review is bound to the commit and receipt below.

Changed: `scripts/llm_operations_audit.py`, `tests/test_llm_operations_audit.py`,
`skills/pi-dev-ops-model-farm/SKILL.md`, this documentation directory and `docs/WIKI.md`.
No app/server or canonical dirty harness file is changed by this workstream.

This worktree starts at `44d7edb6af3d8a3b2be28ca8297fbf5253be7927`.
Revert the eventual scoped commit to remove these reversible assets; keep its
external receipts for audit. Removing a branch or guide cannot roll back live
provider calls or deployments, and none were made here. Separate global input
rollout backups are owned by the coordinator; do not overwrite them from this branch.

## Verified local evidence

The final offline suite passed all 21 unittest methods in 436.742 seconds on
10 October 2026 (Brisbane). It covers secret exclusion, lexical/resolved path
containment with no-open controls, Unicode sizing, alias/cycle limits, malformed
config/metadata, nonmutation, real subprocess deadlines/output caps and runner
false positives. The doctor SHA256 is
`11229394b2cc646f0811b47078ecc0edf6a52fc725dd25a2f58c6bc37db3f85a`;
the test SHA256 is
`4103257a2640489873bb95e831bae2fe6706f5bf4f5e4a770c6ddd8e9fbd3e43`.
The predeployment core inventory receipt is
`/Volumes/Storage Unit/Application-Data/Codex/receipts/llm-operations-20261010-reviewed.json`.
The narrow postdeployment receipt is
`/Volumes/Storage Unit/Application-Data/Codex/receipts/llm-operations-20261010-post-input-update.json`.
It confirms the global Claude entrypoint at 8,588 bytes and matching imported Done
rule at 2,970 bytes; its explicitly limited two-skill catalog is not a new estate
skill count. Separate live readback measured the entrypoint/imports/local floor
at 13,058 bytes versus 42,122 before, retaining the local 1,500-byte floor.

The coordinator's separate source update is local commit
`55224c671a6bab0c33031bf6777f9abeb48a61fa`. Its checkpoint suite passed seven
methods independently in 620.126 seconds; the reviewed source includes restored
safety/lookup triggers and contained reads. The deployment receipt records 15
Claude/Codex files and six Hermes prompts with hash readback, plus removal of the
historical auto-loaded rule after its byte-exact preservation as an on-demand
reference. This peer review establishes local input verification, not a separate
production release gate or remote Windows deployment.

The coordinator's included-capacity Codex health attempts timed out without an
attributable model response. CLI diagnostics included a locked logs database,
ignored settings and a skill-budget warning removing all descriptions and
omitting 69 skills. These observations do not establish a single timeout cause.
Billing alignment, adapter/schema correction and representative runtime quality
checks remain required.

No token savings, output-quality gain, healthy farm or full task completion is asserted.
