# INTEGRATION — wiring `nexus-copywriter` under Nexus

How this skill fires under the Nexus automation layer, how it composes with the estate's
existing skills, and how to drop the folder into the live skills catalog **safely** (it was
authored in isolation while a Pi-Dev-Ops session is active — see the caution).

---

## 1. What it is in the graph

`nexus-copywriter` is a **plain-technique** skill (model-invoked) that sits **upstream of** and
**wraps** the existing craft skills. It does not re-implement copywriting, research, trust
scoring, or board review — it **orchestrates** them behind the truth-spine and owns the terminal
gate. Every checkable claim leaves through its Substantiation Ledger or not at all.

```
nexus-copywriter  (truth-spine + terminal gate)
  1 RESEARCH   → storm / deep-research      (facts → raw substantiation set)
  2 DRAFT      → marketing-copywriter        (craft → Claim-ID-tagged draft)
  3 CITE-OR-CUT→ (self; standalone: claim-verifier) (Claim-ID → record, else cut/demote)
  4 SELF-VERIFY→ eeat                         (Experience/Expertise/Auth/Trust fixes)
  5 BOARD      → specialist-council + boardroom (cross-specialist + multi-model skeptic test)
                 → freeze Substantiation Ledger; ship
```

The five `REQUIRED SUB-SKILL` markers in `SKILL.md` are the composition contract: a stage is not
complete until its marked sub-skill has run and its gate is closed. Missing sub-skills fail the
stage — they are not optional enhancements.

**Stage 3 vs the sibling `claim-verifier/`:** they are the same gate at two moments, not
redundant. Stage 3 runs **inline during authoring** (this skill applies it to its own draft
before freeze); `claim-verifier/` is the standalone, **post-hoc** form — run it on copy that
arrives already written (legacy pages, third-party drafts, pre-existing campaigns) or as an
independent re-audit of shipped assets. New copy authored through nexus-copywriter does not need
a separate claim-verifier pass; anything authored outside it does.

## 2. Nexus auto-fire

The frontmatter carries the estate's Nexus wiring fields (same mechanism as `marketing-copywriter`):

- `automation: automatic` — Nexus fires the skill without an explicit user invocation.
- `intents: nexus-copy, copywriting, landing-page, service-page, ad-copy, email-copy, blog-post,
  franchise-recruitment, review-response, content-generation` — the intent tags Nexus matches
  against an incoming brief.

Effect: on **every** Nexus content-generation intent, `nexus-copywriter` engages **ahead of** raw
`marketing-copywriter`, so no Nexus asset reaches a customer without passing the truth + AU-law
gates. When `marketing-orchestrator` dispatches copy work, route it through `nexus-copywriter`
rather than calling `marketing-copywriter` directly.

## 3. Drop-in procedure (catalog placement)

Per `skill-authoring-standard` (operative 2-place rule) and `~/.claude/skills/CLAUDE.md`:

1. Copy the folder `nexus-copywriter/` (this `SKILL.md` + `references/DOCTRINE.md` +
   `references/craft-and-law.md` + `INTEGRATION.md`) into the estate skills source,
   `~/Pi-Dev-Ops/skills/nexus-copywriter/`. It surfaces at `~/.claude/skills/nexus-copywriter/`
   via the existing symlink convention.
   **1b.** Copy the companion gate `claim-verifier/` into `~/Pi-Dev-Ops/skills/claim-verifier/` — a
   **sibling** of `nexus-copywriter/`. Its `SKILL.md` resolves the shared doctrine via
   `../nexus-copywriter/references/DOCTRINE.md`, so the two install as **siblings** under
   `~/.claude/skills/` (they always do); no separate doctrine copy, single source of truth preserved.
   Verified: from `claim-verifier/`, `../nexus-copywriter/references/DOCTRINE.md` resolves.
2. `DOCTRINE.md` ships **inside** the skill folder at `nexus-copywriter/references/DOCTRINE.md`
   (the `SKILL.md` pointer is `references/DOCTRINE.md`), so it survives drop-in to any catalog
   layout — no sibling file, no `../` pointer to break.
3. Register it: add one row to `~/.claude/skills/README.md`. As a Nexus entry point for content
   generation, add one `index.md` row too.
4. No `.claude-plugin/plugin.json` edit is required (place #3 of the documented 3-place rule is
   aspirational and does not exist).

Frontmatter is already `skill-authoring-standard`-compliant: plain-technique archetype,
WHEN-triggers description, no banned fields (`version`/`owner_role`/`status`/`metadata.requires`).
No `mcp__…` prefixes are hardcoded — sub-skills are resolved by name.

## 4. Isolation caution — active Pi-Dev-Ops session

This skill was authored **in isolation** in `~/nexus-copywriter-skill-20260708/`. A Pi-Dev-Ops
session is **active** and may share the working tree / switch branches under you.

- **Do not** run git surgery on the live Pi-Dev-Ops checkout, and do not move or overwrite files
  in `~/Pi-Dev-Ops/skills/` while that session owns the tree.
- Keep the deliverable staged here until the active session is clear, then hand off by PR or a
  clean copy into an isolated worktree — never by editing the shared checkout in place.
- If unsure who owns the skills folder right now, ask before writing to it.

## 5. Verification after drop-in

- The three `REQUIRED SUB-SKILL` targets exist in the catalog: `storm`/`deep-research`,
  `marketing-copywriter`, `eeat`, `specialist-council`, `boardroom`.
- Both `references/DOCTRINE.md` and `references/craft-and-law.md` pointers resolve from the installed path.
- A test brief with a content-generation intent auto-fires `nexus-copywriter` (not bare
  `marketing-copywriter`), and a deliberately unprovable superlative is **cut** at CITE-OR-CUT,
  not shipped.
