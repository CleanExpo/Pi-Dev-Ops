---
name: remotion-brand-research
description: Researches a portfolio company's visual identity from public sources (homepage, about page, marketing copy, GitHub README) and produces a structured BrandResearch dossier. Triggered when `remotion-studio/src/brands/{slug}.ts` is missing, older than 90 days, or the user explicitly says "refresh brand for {brand}". Output feeds remotion-brand-codify.
automation: automatic
intents: brand-research, refresh-brand, brand-discovery
---

# remotion-brand-research

Discovery skill that builds a structured picture of a brand before any rendering happens.

## Triggers

- `remotion-orchestrator` flags `brands/{slug}.ts` as missing or `mtime < now - 90 days`.
- User says "refresh the {brand} brand", "redo brand research for {brand}", or pastes a new brand guidelines URL.

## Inputs

- `brandSlug` — one of `dr` | `nrpg` | `ra` | `carsi` | `ccw`
- Optional: list of source URLs (homepage, brand book PDF, style guide page)
- Optional: existing `brands/{slug}.ts` for delta detection

## Method

1. Fetch the company's homepage and 2-3 deep pages (about, services, contact). Extract:
   - Visual: dominant hex colours sampled from the hero region; logos linked from `<header>` and `<img alt=...logo>`; web fonts from `<link href=fonts...>` or `font-family` declarations.
   - Verbal: headline phrases, taglines, repeated CTAs, prohibited claims (e.g. "cheapest", "guaranteed").
   - Audience: who the page addresses (B2B vs B2C, regional, role-specific).
2. Read the company's GitHub repo `README.md` and `package.json` if present — sometimes the design tokens leak there.
3. Cross-reference with `Pi-Dev-Ops/.harness/business-charters/{slug}-charter.md` and `Pi-SEO/business-charters/projects/{slug}-charter.md` for mission/voice cues.

## Output

Markdown dossier at `remotion-studio/.research/brand-{slug}-{YYYY-MM-DD}.md`:

```markdown
# Brand research: {displayName} ({slug})
Date: 2026-04-28
Sources: [url1, url2, ...]

## Visual
- Primary colours (sampled): #..., #..., #...
- Logos found: [...]
- Web fonts: [...]

## Verbal
- Tagline candidates: [...]
- Tone descriptors: [...]
- Forbidden words: [...]

## Audience
- Primary: ...
- Secondary: ...

## Channel signals
- Active on: LinkedIn / YouTube / Instagram (frequency, last post)

## Risks / open questions
- ...
```

And a structured JSON sibling at `.research/brand-{slug}-{YYYY-MM-DD}.json` matching a partial `BrandConfig`.

## Boundaries

- Never scrape sites that block bots via robots.txt (skip + note in dossier).
- Never invent hex codes — if sampling fails, leave field null and note "needs founder input".
- Never source brand voice from competitor sites — only the brand itself.

## Hands off to

`remotion-brand-codify` reads this dossier and produces `src/brands/{slug}.ts`.
