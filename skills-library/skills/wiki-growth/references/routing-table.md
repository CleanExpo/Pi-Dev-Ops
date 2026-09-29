# Disposition → lane → downstream skill

The routing map for apply mode. Labels are defined in `review-rubric.md`; this file only
maps them. All lane outputs are staged in `_system/wiki-growth/drafts/<note-slug>/` —
never written into the live vault.

| Disposition | Lane | Downstream action in apply mode |
|---|:--:|---|
| Keep | A | Report row only. No draft, no dispatch. |
| Archive | A | Draft a one-paragraph archive note (what supersedes it, why). Pilot moves the page. |
| Merge | A | Draft the merged page (survivor + absorbed content). Pilot replaces the originals. |
| Split | A | Draft the N split pages. Pilot replaces the original. |
| Strengthen | B | Invoke `storm` on the idea's topic scoped to its gaps; save the cited write-up as the strengthened draft. |
| Research | B | Invoke `storm` (breadth of perspective) or `source-ingest` (raw source capture into `Sources/` is the one sanctioned out-of-sandbox write, because that skill owns that path). Attach findings to the draft. |
| Turn into skill | C | Invoke `skill-authoring-standard` to design it; stage the draft SKILL.md in drafts/, NOT in `~/.claude/skills/`. |
| Turn into SOP | C | Invoke `spm` fast-lane micro-spec; stage the SOP draft. |
| Turn into training module | C | Invoke `spm` for the module spec; stage the draft. |
| Turn into product feature | C | Invoke `spm` full spec against the owning repo; stage the spec draft. |
| Turn into marketing asset | C | Invoke `marketing-orchestrator` in plan-only form; stage the brief/asset draft. |

Lane meanings: **A** = verdict-only metadata call · **B** = strengthen with sources ·
**C** = promote to a new artefact class.

Hard line on lane C: every draft states in its header that implementation requires a
separate `/judge` real-100/100 pass plus explicit user approval. wiki-growth never builds.
