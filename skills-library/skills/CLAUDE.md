# Skills — Catalog Hygiene

> Adapted from Matt Pocock's skills repo (`github.com/mattpocock/skills`). The discipline is what makes the catalog discoverable — the rules apply to **every** future skill added here.

## Lifecycle buckets

| Bucket | Purpose | In catalog? |
|---|---|---|
| `engineering/` | Daily code work — sharp verbs (tdd, diagnose, triage). | ✅ |
| `productivity/` | Daily non-code workflow (status snapshots, scheduling, wiki ingest). | ✅ |
| `misc/` | Kept but rarely used (one-shot setup, occasional integrations). | ✅ |
| `personal/` | Tied to Phill's own setup — not promoted, not for teammates. | ❌ |
| `in-progress/` | Drafts not yet ready to ship. | ❌ |
| `deprecated/` | No longer used. Kept for archaeological reference. | ❌ |

**The catalog rule** (the engine of the discipline):

Operative reality (2026-07-01 audit): the bucket folders (`engineering/` `productivity/`
`misc/` `personal/`) exist but are **empty** — every active skill is flat at the top level —
and there is **no** `.claude-plugin/plugin.json`. So the original "3-place rule" was
aspirational. The **operative 2-place rule** every active skill MUST satisfy:

1. `~/.claude/skills/README.md` (top-level catalog — one line per skill, linked to `SKILL.md`).
2. `~/.claude/skills/index.md` (router row — **only** for entry-point skills the user invokes
   by phrase; sub-skills dispatched by an entry point do NOT get a row).

Skills in `personal/`, `in-progress/`, or `deprecated/` MUST NOT appear in either.

Each skill entry MUST link the skill name to its `SKILL.md` so anyone can read the contract.

> Aspirational future (place #3): if a `.claude-plugin/plugin.json` is ever wired up, add it
> as a third place and populate the bucket `README.md`s. Until then, do not cite places that
> don't exist. The canonical frontmatter + authoring conventions live in
> [`skill-authoring-standard`](skill-authoring-standard/SKILL.md).

## Adding a new skill

1. Decide its lifecycle bucket (default: `in-progress/`).
2. Write `<bucket>/<name>/SKILL.md` with frontmatter (`name`, `description`).
3. If active (`engineering` / `productivity` / `misc`): add to the 3 catalog locations above.
4. If quarantined (`personal` / `in-progress` / `deprecated`): do NOT add to catalogs.

## Promoting / demoting

- **WIP → active**: move the dir from `in-progress/` to the right active bucket + add the 3 catalog entries.
- **Active → deprecated**: move the dir to `deprecated/` + remove from all 3 catalogs. Don't delete — the SKILL.md is the archaeological record.
- **Active → personal**: move + remove from catalogs.

## Anti-patterns that earned this rule

- **Stacked orchestrators** — `remotion-orchestrator` was kept after `video-orchestrator` superseded it. No deprecation path = both stay live = every brief becomes a routing puzzle.
- **Docs masquerading as skills** — 30 `vercel:*` entries that are documentation lookups, not actions. Docs live in docs.
- **Bare-named skills** — skills with no `description` frontmatter leaked into the active list. The 3-place rule blocks this — if there's no description, you can't write the catalog line, so you can't promote it.
- **Cross-repo duplication** — `remotion-designer` lived in both `~/.claude/skills/` and `~/Pi-CEO/Pi-Dev-Ops/skills/`. Pick one canonical home per skill.

## Domain vocabulary

Future work: add `CONTEXT.md` once vocabulary collisions start hurting. Examples to track:
- "orchestrator" — which one?
- "guardian" / "gate" / "review" — what's the distinction?
- "brand" — is it RA-the-product or RA-the-brand-asset-pack?

When in doubt, search this file for the term before introducing a new one.

## Out of scope

`.out-of-scope/` (when needed) tracks rejected ideas explicitly so they don't get re-litigated.
