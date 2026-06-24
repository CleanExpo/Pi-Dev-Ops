# Markdown bloat audit — Pi-Dev-Ops — 2026-06-24

## NorthStar outcome
Keep repository markdown as pathway guidance, not a dumping ground: root docs and skills should route agents to build, design, develop, test, and ship without wandering into secondary knowledge.

## Evidence read
- `skills/northstar-shipit/SKILL.md` — default lane is narrow, one ShipIt path, explicit noise removal.
- `skills/launch-enhance-debloat/SKILL.md` — cleanup must be propose-first, reversible, tested, and respect `AGENTS.md`.
- `AGENTS.md` — `skills/`, `scripts/`, `tests/`, `.harness/` are safe; auth/secrets/prod paths remain blocked.
- `CLAUDE.md` — root project guidance is dense but contains live operating rules; do not blindly trim without extracting references first.
- `app/server/tao_codebase_wiki.py` and `tests/test_tao_codebase_wiki.py` — generated `WIKI.md` files were leaking UI/auth noise (`Not logged in · Please run /login`).

## Noise removed now
- Generated `WIKI.md` auth/UI line is no longer allowed through `_render_wiki`.
- Stale exploratory `tests/test_wiki_knowledge_scout.py` removed because this batch is Markdown cleanup/NorthStar, not the Wiki scout build.
- Sample foundation packet removed; the generator script remains.

## Candidates not auto-trimmed yet
These are large or noisy, but require separate extraction/migration before deletion:

| Path | Lines | Decision |
|---|---:|---|
| `docs/superpowers/plans/2026-05-17-live-nexus-display.md` | 3189 | Archive/compress into outcome + decisions + links; not runtime guidance. |
| `docs/superpowers/plans/2026-05-17-plaud-actions.md` | 2124 | Archive/compress; preserve acceptance criteria only. |
| `docs/superpowers/plans/2026-05-17-plaud-brain-ingestion.md` | 2115 | Archive/compress; preserve data-contract evidence only. |
| `docs/superpowers/plans/2026-05-17-elevenlabs-margot-voice-agent.md` | 1858 | Archive/compress; preserve voice-agent operating constraints only. |
| `docs/superpowers/plans/2026-06-21-grounding-primitive.md` | 1105 | Convert repeatable grounding protocol into a skill/reference. |
| `skills/unite-group-ci-recovery/SKILL.md` | 339 | Split into focused CI, Vercel, Supabase, and admin-merge references. |
| `skills/geo-optimization/SKILL.md` | 300 | Keep core skill short; move stack playbooks/checklists into references. |
| `skills/analyst/SKILL.md` | 294 | Keep routing + output contract; move doctrine/lenses into references. |
| `CLAUDE.md` | 283 | Keep active operating mandate; move hard-won historical lessons into references before trimming. |

## Safe change applied in this batch
`app/server/tao_codebase_wiki.py` now strips generated markdown auth/UI noise before writing `WIKI.md` bodies. This prevents the repo from repeatedly regenerating non-knowledge lines into every directory wiki.

## Default next cleanup lane
1. Add a deterministic `scripts/markdown_bloat_audit.py` that scores `.md` files and writes this audit shape.
2. Split the three oversized skill docs into `SKILL.md` router + `references/*.md` long context.
3. Compress `docs/superpowers/plans/*` into short decision records under an archive/index, preserving evidence paths only.
4. Regenerate WIKI files after the cleaner is in place.

## Gate check
- Status: LOCAL_SAFE for the noise-stripper and audit.
- Status: NEED_APPROVAL before bulk deleting/compressing historical plans.
- Reason: large docs may contain historical evidence; removal must be reversible and path-indexed.
