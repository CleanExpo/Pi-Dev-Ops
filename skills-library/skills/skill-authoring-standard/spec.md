# SPM Spec — `skill-authoring-standard` (Global Skill)

> Produced by `/spm` (read-only). No build until accepted. Seeds: Wiki
> [[building-great-agent-skills]] (Pocock rubric) + two research agents
> (Pocock ground-truth + Global-skills architecture map), this session 2026-07-01.

---

## 1. Task being planned
Create one **global, user-invoked skill** — `skill-authoring-standard` — that makes every
new or edited skill in `~/.claude/skills/` (and the symlinked Pi-Dev-Ops packages) be
designed by Matt Pocock's Skill Checklist method (Trigger / Structure / Steering /
Pruning), and that defines a disciplined `.md` reference architecture so design/reference
elements are **pulled on demand and leave no cache or bloat behind**.

## 2. Current project context (evidence)
- **84 `SKILL.md`** files; flat top-level layout. Documented buckets
  (`engineering/ productivity/ misc/ personal/`) **exist but are empty** — the bucket
  discipline in `~/.claude/skills/CLAUDE.md` is not physically realised.
- **Library model works:** one always-loaded router (`index.md`, ≤60 lines) + three
  on-demand docs (`README.md`, `CLAUDE.md`, `library/connections.md`) + per-skill bodies
  loaded only when the Skill tool fires. This already *is* progressive disclosure.
- **3-place rule is aspirational:** place #3 (`.claude-plugin/plugin.json`) does not exist;
  place #2 (`<bucket>/README.md`) can't exist because buckets are empty. Only place #1
  (`README.md`) is operative. `UNSUPPORTED` as written.
- **Best-in-class template already present:** the command-skill family (`judge`, `spm`,
  `session-handoff`, `resume-from-handoff`, `readiness-architect`) — consistent
  `argument-hint` + `disable-model-invocation: true` + read-only `allowed-tools` +
  `references/` subfolder. Refactored 2026-06-27.
- **Upstream meta-skill exists:** `superpowers:writing-skills`
  (`/Users/phill-mac/Developer/superpowers/skills/writing-skills/SKILL.md`, 656 lines) —
  TDD-for-skills (RED→GREEN→REFACTOR), CSO, "description = WHEN not WHAT", externalize at
  100+ lines. **No local equivalent exists.**

## 3. Problem statement
There is no enforced standard, so skills drift: **frontmatter has no schema** (description
written as folded/quoted/bare across three "schools"; WHEN-vs-WHAT violations that bake
workflow + model tier into the description; one-off fields `version`, `owner_role`,
`status`, `metadata.requires`); **5 skills breach the 200-line cap** (`nlm-skill` 710,
`ceo-board` 349, `frontend-slides` 322, `seo` 309, `brand-guardian` 247); and **reference
material bloats and duplicates** (nlm-skill inlines a command catalog it already has in
`references/`; `frontend-slides` ships a whole nested plugin repo; `ceo-board` points at a
session-scoped symlink that can dangle; `seo/.venv/` committed inside a skill;
`.backup-cmds-*` sediment parked in the live catalog). No single artifact teaches the
Pocock method or pins the conventions, and nothing checks a skill against them.

## 4. Desired outcome
A maintainer (human or agent) authoring or editing any skill invokes
`/skill-authoring-standard`, gets the rubric + the canonical frontmatter schema for the
skill's **archetype**, applies the 3-rung information hierarchy with context pointers, and
runs a pruning pass (relevance + sentence-level no-op deletion). New skills ship compliant;
edited skills move toward compliance. Result: smaller `SKILL.md` files, on-demand reference
pulls, zero duplicated/sediment reference, predictable invocation.

## 5. Scope and non-goals
**In scope**
- One global skill `~/.claude/skills/skill-authoring-standard/SKILL.md` (≤200 lines; itself
  exemplary) + a disclosed `GLOSSARY.md` (leading-word definitions, Pocock-style with
  `_Avoid_:` synonym bans) + `references/frontmatter-schema.md` (the per-archetype schema)
  + `references/review-checklist.md` (the gate).
- A **3-archetype frontmatter schema** (command-skill / agent-role / plain-technique).
- The `.md` reference architecture rule: `references/` is the **only** external location;
  worded context pointers; externalize at branch-only or >~150 lines.
- A **review checklist** runnable against any existing skill (the "design elements
  understood + pulled efficiently" gate), including the deletion test.

**Non-goals (explicit NO-GOs)**
- **Not** re-deriving TDD-for-skills — that is `superpowers:writing-skills`; this skill
  *references* it as required background.
- **Not** a one-shot retroactive rewrite of all 84 skills. Cleanup of the 5 over-cap
  offenders + sediment is a **separate backlog ticket**, not this build.
- **Not** a runtime hook/enforcer that blocks skill edits — this is a user-invoked standard
  + checklist, not a CI gate (a gate can follow once the standard stabilises).
- **Not** model-invoked. It carries no per-request context load.

## 6. Existing capability review (do not rebuild)
| Capability | Where | Reuse decision |
|---|---|---|
| TDD-for-skills, CSO, WHEN-not-WHAT | `superpowers:writing-skills` | **Reference, don't duplicate** — cite as prerequisite |
| Command-skill template | `judge/`, `spm/` + their `references/` | **Copy the shape** for the new skill |
| Catalog hygiene, buckets, 3-place rule | `~/.claude/skills/CLAUDE.md` | **Reconcile + point to it** — don't restate |
| Library check-out/check-in | `~/.claude/CLAUDE.md` §6, `index.md` | **Build on** — this is the no-cache discipline |
| Connections registry | `library/connections.md` | Cross-link for tool-resolution rule |

## 7. Specialist board review
- **Product:** real recurring pain (every skill author re-invents conventions); user-invoked
  fits — authors already know when they're authoring. APPROVE.
- **Architect:** layering on `superpowers:writing-skills` avoids a competing source of
  truth; archetype schema is the load-bearing new artifact. Risk: a second skill-about-skills
  could itself become sediment — mitigate by making it the *Library-native* layer only
  (frontmatter schema + the no-bloat `.md` rule), not a general essay. APPROVE.
- **UX:** one command, archetype-routed output, a copy-pasteable frontmatter block per
  archetype, and a checklist. Keep `SKILL.md` ≤200 lines or it fails its own rubric.
- **Security:** read-only authoring aid; `allowed-tools` Read/Grep/Glob/LS/Bash. No secrets,
  no external calls. Low risk.
- **QA/Test Lead:** testable by self-application + a subagent dry-run on a deliberately bad
  skill (must catch the planted violations). Define below.
- **Devil's advocate:** see §8.

## 8. Judge-style challenge
- *"superpowers:writing-skills already exists — this is duplication."* → Rebutted: that skill
  is intentionally generic and **rejects** project-specific/compliance conventions (per its
  repo CLAUDE.md). The Library-specific schema (archetypes, `references/`-only rule, 3-place
  reconciliation, model-tier pinning, connections discipline) has **no** home today. The new
  skill is the *local layer*, ~150 lines, that the upstream explicitly won't hold.
- *"A standard nobody runs is a no-op."* → Mitigated by making it the named gate inside the
  existing command chain (author → `/skill-authoring-standard` → `/judge`) and by shipping a
  checklist that `opus-adversary`/`qa-lead` can apply in review.
- *"Enforcing on 84 skills is huge."* → Out of scope (§5). Standard applies forward;
  cleanup is one backlog ticket.
- **Score: 88/100 → APPROVE BUILD** (scoped). −7 evidence (3-place rule must be reconciled,
  not assumed); −5 risk that it becomes a second essay (mitigated by the ≤200-line +
  glossary-externalised constraint, self-enforced).

## 9. Proposed solution
**Files**
```
~/.claude/skills/skill-authoring-standard/
  SKILL.md                        # ≤200 lines: the method + archetype router + pruning pass
  GLOSSARY.md                     # leading words, Pocock-style, with _Avoid_: synonym bans
  references/
    frontmatter-schema.md         # canonical schema per archetype (the new SSOT)
    review-checklist.md           # the runnable gate (design-elements + no-bloat)
```

**SKILL.md spine (user-invoked, `disable-model-invocation: true`):**
1. **Trigger gate** — pick archetype + invocation. Default **user-invoked**; go model-invoked
   only if the agent/another skill must reach it autonomously (pay context load with a
   trigger-rich description). Leading words: *context load* vs *cognitive load*.
2. **Structure gate** — place every element on the **3-rung hierarchy** (in-skill step →
   in-skill reference → external reference behind a worded **context pointer**). Externalize
   branch-only or >~150-line material to `references/`. Each step ends on a **checkable
   completion criterion**.
3. **Steering gate** — coin/borrow **leading words** (pretrained first); split a skill **by
   sequence** to force **leg work** (hide post-completion steps) or **by invocation** (a
   distinct leading word worth its context load).
4. **Pruning gate** — **single source of truth** → **relevance** pass → sentence-level
   **no-op deletion** (deletion test; delete whole sentences, be aggressive). Diagnose with
   the 5 failure modes: premature completion, duplication, sediment, sprawl, no-op.

**`references/frontmatter-schema.md` — the canonical schema (the real new value):**

| Field | command-skill | agent-role | plain-technique |
|---|---|---|---|
| `name` (lowercase-hyphen) | ✅ | ✅ | ✅ |
| `description` | human one-line (triggers stripped) | **WHEN** triggers ("Use when…") | **WHEN** triggers |
| `disable-model-invocation: true` | ✅ | optional | ✗ |
| `argument-hint` | ✅ | optional | ✗ |
| `allowed-tools` | ✅ (read-only unless it builds) | ✅ | optional |
| `model` | optional (pin if tier matters) | ✅ (pinned tier) | ✗ |
Rules: description = **WHEN not WHAT** (no workflow summary, no "Model: …" prose baked in);
ban one-off fields (`version`, `owner_role`/`status`, `metadata.requires`) unless a stated
reason; `allowed-tools` as inline comma list; resolve MCP tools by capability via ToolSearch,
never hardcode `mcp__…` prefixes (per `connections.md`).

**"Design Elements, pulled efficiently, no cache/bloat" — explicit rules:**
- `references/` is the **only** standard external location. **Banned:** session-scoped
  symlinks (`ceo-board` board-members), committed venvs (`seo/.venv`), nested plugin repos
  (`frontend-slides`), backup dirs in the live catalog (`.backup-cmds-*`).
- Every external file is **named for its contents** and reached by a **context pointer whose
  wording states the condition** ("X are defined in [`GLOSSARY.md`](GLOSSARY.md); look them
  up there"). Fix pointer wording before inlining.
- **Single source of truth:** a reference (template/definition) lives in exactly one file;
  never duplicated across skills or steps.
- **Check-in discipline:** once a checked-out reference has served its purpose, it falls out
  of context — don't re-read. This is the "no cache left behind" rule at the agent level;
  the `references/`-only + dedup rules are it at the filesystem level.
- For **design-heavy** skills (visual/motion), defer element ownership to the four-layer
  boundary in [[feedback-design-md-boundary]] (design.md / motion.md / scene.md /
  BrandConfig) — the standard points there rather than re-encoding it.

**Reconcile the 3-place rule:** update `~/.claude/skills/CLAUDE.md` to match reality — either
(a) create `.claude-plugin/plugin.json` + populate buckets, or (b) drop to the **operative
2-place rule** (top-level `README.md` + `index.md` router entry for entry-point skills). The
spec recommends **(b)** now (cheapest, true), with (a) as a later option. *(This doc edit is
part of the build, not this read-only spec.)*

## 10. UX requirements
- `/skill-authoring-standard` with no args → ask which archetype / paste the skill to review.
- With a skill path → run the review checklist and return findings (pass/fail per gate +
  the corrected frontmatter block).
- Output is copy-pasteable; no narration of process.

## 11. Technical requirements
- `SKILL.md` ≤200 lines (self-enforcing); glossary + schema externalized.
- Read-only `allowed-tools: Read, Grep, Glob, LS, Bash`.
- Add to `~/.claude/skills/README.md` (place #1) and, since it's a maintainer entry point,
  one row in `index.md`. No `plugin.json` dependency.

## 12. Security / privacy requirements
Read-only; no network; no secrets; no external systems. The skill must instruct authors to
resolve MCP tools by capability (ToolSearch), never hardcode hashed `mcp__…` prefixes.

## 13. Verification plan
1. **Self-application:** run the skill's own checklist against its `SKILL.md` — must pass
   every gate, be ≤200 lines, glossary externalized. If it fails its own rubric, reject.
2. **Subagent dry-run** (superpowers `testing-skills-with-subagents` pattern): hand a fresh
   subagent a deliberately bad skill (bloated description with workflow + model prose, an
   inlined 200-line template, a no-op paragraph) and confirm the checklist flags all three.
3. **Regression spot-check:** apply to `judge` (should pass clean) and `nlm-skill` (should
   flag the 710-line inline + stale `version`). Both verdicts must be correct.

## 14. Loop / stress testing
- Run the checklist across all 84 skills in a batch (read-only) and confirm it produces a
  finite, deduplicated findings list (no crash on the symlinked packages, no infinite
  pointer-following). Capture the count of skills flagged as the cleanup backlog input.

## 15. Acceptance criteria
- [ ] `skill-authoring-standard/` exists with `SKILL.md` (≤200 lines) + `GLOSSARY.md` +
      `references/frontmatter-schema.md` + `references/review-checklist.md`.
- [ ] Frontmatter schema covers all three archetypes and is the cited SSOT.
- [ ] Self-application passes; subagent dry-run catches all planted violations; `judge`
      passes clean and `nlm-skill` is flagged.
- [ ] Added to `README.md` + `index.md`; `~/.claude/skills/CLAUDE.md` 3-place rule
      reconciled to the operative 2-place reality.
- [ ] A backlog ticket filed for cleanup of the 5 over-cap skills + sediment (nlm-skill,
      frontend-slides nested plugin, `.backup-cmds-*`, ceo-board symlink, seo/.venv).

## 16. Goal command
```
/goal Build the skill-authoring-standard global skill per spec.md. Done when:
SKILL.md ≤200 lines passes its own review-checklist; GLOSSARY.md + references/frontmatter-schema.md
+ references/review-checklist.md exist; the subagent dry-run flags all 3 planted violations and
judge passes clean while nlm-skill is flagged; README.md + index.md updated; skills/CLAUDE.md
3-place rule reconciled to the 2-place reality; and a cleanup backlog ticket is filed.
```

## 17. Implementation sequence
1. Author `GLOSSARY.md` (leading words + `_Avoid_:` bans) — the vocabulary first.
2. Author `references/frontmatter-schema.md` (the 3-archetype table) and
   `references/review-checklist.md` (the gate).
3. Author `SKILL.md` spine pointing at both via worded context pointers; keep ≤200 lines.
4. Self-apply the checklist; fix until clean.
5. Subagent dry-run + `judge`/`nlm-skill` spot-check; fix until verdicts correct.
6. Update `README.md`, `index.md`, reconcile `skills/CLAUDE.md`.
7. File the cleanup backlog ticket (Pi-Dev-Ops project, priority 3).

## 18. Session-handoff seed
Built the SPM spec for `skill-authoring-standard`: a user-invoked global skill layering
Pocock's Trigger/Structure/Steering/Pruning rubric + a 3-archetype frontmatter SSOT + a
`references/`-only no-bloat `.md` architecture on top of `superpowers:writing-skills`.
Spec at `~/.claude/skills/skill-authoring-standard/spec.md`. Judge 88/100 APPROVE BUILD
(scoped). Next: `/goal` to build per §16, or implement steps §17 in order.

## 19. Final recommendation
**APPROVE BUILD (scoped).** Build the standard + glossary + schema + checklist now; keep the
84-skill cleanup as a separate backlog ticket. The single highest-value artifact is
`references/frontmatter-schema.md` — it closes the concrete, evidenced gap (no enforced
frontmatter schema) that the rest of the catalog drift flows from.

---
SPM spec complete. Next safe action: run the §16 `/goal` command to build the skill, or say "build it" to proceed through §17.
