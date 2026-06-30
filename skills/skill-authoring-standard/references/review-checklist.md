# Review Checklist — the gate

Run against any `SKILL.md` (new, edited, or an existing skill under review). Each item is
PASS / FAIL with the offending line. Terms link to [`GLOSSARY.md`](../GLOSSARY.md).

## 1. Trigger
- [ ] Archetype is one of command-skill / agent-role / plain-technique, and frontmatter
      matches [`frontmatter-schema.md`](frontmatter-schema.md) for that archetype.
- [ ] Invocation is deliberate: user-invoked (`disable-model-invocation: true`) unless the
      agent or another skill must reach it autonomously. If model-invoked, the added
      [`Context load`](../GLOSSARY.md) is justified.
- [ ] `description` obeys [`WHEN-not-WHAT`](../GLOSSARY.md): triggers for model-invoked, one
      human line for user-invoked. No workflow summary, no `Model: …` prose, one trigger per
      [`Branch`](../GLOSSARY.md).
- [ ] No [banned fields](frontmatter-schema.md) (`version`, `owner_role`, `status`,
      `metadata.requires`) without a stated reason.
- [ ] Any skill that mutates state (writes, posts, deploys, migrates) declares an
      `allowed-tools` set; read-only skills declare a read-only set.

## 2. Structure
- [ ] Every element sits on the [`Information hierarchy`](../GLOSSARY.md): in-skill step →
      in-skill reference → external reference.
- [ ] Branch-only or large (>~150-line) reference is in `references/`, reached by a worded
      [`Context pointer`](../GLOSSARY.md) — not inlined.
- [ ] `SKILL.md` ≤ 200 lines. Over → it is [`Sprawl`](../GLOSSARY.md); disclose reference out.
- [ ] Each step ends on a checkable [`Completion criterion`](../GLOSSARY.md).

## 3. Design elements pulled efficiently — no cache/bloat
- [ ] External reference lives **only** in `references/`. **FAIL on:** session-scoped
      symlinks, committed venvs, nested plugin repos, backup dirs in the live skill folder.
- [ ] Each external file is named for its contents and reached by a pointer whose wording
      states the condition for loading it.
- [ ] [`Single source of truth`](../GLOSSARY.md): no reference/template/trigger duplicated
      across files or steps ([`Duplication`](../GLOSSARY.md)).
- [ ] Design-heavy skills defer element ownership to the four-layer boundary
      ([[feedback-design-md-boundary]]) rather than re-encoding it.

## 4. Steering
- [ ] Restated triads are condensed into a [`Leading word`](../GLOSSARY.md) (pretrained
      before coined).
- [ ] Where extra [`Leg work`](../GLOSSARY.md) matters, the skill is split by sequence to
      hide post-completion steps, or by invocation for a distinct leading word.

## 5. Pruning (the deletion pass)
- [ ] Relevance: every line still bears on what the skill does — no [`Sediment`](../GLOSSARY.md).
- [ ] [`Deletion test`](../GLOSSARY.md) run sentence-by-sentence: no [`No-op`](../GLOSSARY.md)
      survives. Delete whole sentences, don't trim words.
- [ ] No [`Premature completion`](../GLOSSARY.md) bait — goals visible to a step are sharpened
      or hidden.

## Catalog placement (operative 2-place rule)
- [ ] Listed in `~/.claude/skills/README.md` (one line, linked to `SKILL.md`).
- [ ] If an entry-point skill, one row in `~/.claude/skills/index.md`.
