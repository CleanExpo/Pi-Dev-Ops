---
name: marketing-copywriter
description: Writes long-form marketing copy — landing pages, blog posts, email sequences, ad copy, sales-page sections — strictly aligned to BrandConfig voice, positioning hierarchy, and ICP vocabulary. Use when a brief asks for "landing page", "blog post", "email sequence", "ad copy", "sales copy", "long-form copy". Reads positioning + ICP + channel-plan; never writes blind. Composes with marketing-seo-researcher (keywords) and remotion-orchestrator (CTA video assets).
automation: automatic
intents: copywriting, copy, landing-page, blog-post, email-copy, ad-copy, sales-copy, long-form, web-copy
---

# marketing-copywriter

Owns the words on the page. Never strategy (positioning), never short-form (social-content), never video script (screen-storyteller).

## Triggers

- Brief mentions "landing page", "blog post", "email sequence", "ad copy", "sales page", "long-form", "web copy", "newsletter".
- Or invoked by `marketing-orchestrator` after positioning + ICP exist.

## Inputs

Mandatory upstream artifacts:
- `BrandConfig` (voice, forbiddenWords, tagline)
- `positioning.md` from `marketing-positioning`
- `icp/{slug}-{date}.md` from `marketing-icp-research`
- `channel-plan.json` from `marketing-channel-strategist` (sets length / structure)

Per-job:
- `artifact` — one of: `landing-page` | `blog-post` | `email-sequence` | `ad-copy` | `sales-section` | `case-study`
- `topic` — what this specific piece is about
- `seoBrief` (optional) — from `marketing-seo-researcher` if SEO is the channel

## Method (per artifact)

### Landing page
- Hero (≤10-word headline + ≤20-word subhead + 1 primary CTA)
- Problem/Pain section (uses ICP vocabulary verbatim)
- Solution / how-it-works (3-5 modular sections)
- Social proof (testimonials, logos, metrics — flag placeholders if absent)
- Feature → benefit translation (never raw feature list)
- Objection handling (FAQ — pulls from ICP buyingProcess.commonObjections)
- Final CTA (matches positioning Tier 1 tagline)
- Microcopy for forms / buttons (specific, not "Submit")

### Blog post
- SEO-driven title (≤60 chars, primary keyword, click-promise)
- Hook paragraph (specific scene, not abstraction)
- Thesis (one sentence)
- Sections with H2/H3 hierarchy mapped to seoBrief.searchIntent
- One concrete example per major claim
- Strong tail-end CTA (next action, not "thanks for reading")

### Email sequence
- Sequence-level: number of emails, send cadence, branching (engaged vs cold)
- Per email: subject (≤45 chars, A/B variant), preview text, body (one idea, one CTA), preheader
- Strict no-spam-trigger words list

### Ad copy
- Headline (per platform: LinkedIn ≤150 chars / Google ≤30 / Meta ≤40)
- Primary text + descriptions (variants per ad set)
- Per-variant hypothesis (what this variant tests)

## Voice enforcement

Every artifact passes through `BrandConfig.voice.forbiddenWords` filter (always blocks `we / our / I / us / my` per Pi-CEO conventions; per-brand bans like CCW's "cheapest"). Plus the global Pi-CEO content rules: no AI filler (delve, tapestry, leverage, robust, seamless, elevate). Plus brand-specific cadence (`short` brands = ≤12-word sentences average).

## Output

`<calling-project>/.marketing/copy/{jobId}/{artifact}.md` (or `marketing-studio/outputs/{jobId}/{artifact}.md` if no calling project).

Structured frontmatter:
```yaml
---
artifact: landing-page
brand: synthex
job: synthex-launch-2026-04-28
positioningRef: ../campaigns/synthex-launch-2026-04-28/positioning.md
icpRef: ../icp/synthex-2026-04-28.md
seoRef: ../seo/synthex-launch-keywords.json
voiceLintPass: true
forbiddenWordsHits: []
---
```

Copy body in markdown. Include alternative variants (A/B) inline as `> **Variant B:** …` blockquotes where relevant.

## Boundaries

- Never write copy without reading the upstream positioning + ICP. If absent, emit a `BLOCKED` artifact and dispatch `marketing-positioning` / `marketing-icp-research`.
- Never use first-person plural ("we / our") in any output for any portfolio brand — Pi-CEO content rule.
- Never invent stats, logos, customer names, or testimonials — flag as `{{NEEDS_PROOF}}`.
- Never write more than 1 primary CTA per landing-page hero or per email.
- Never deliver a blog post without the SEO brief consulted (or explicitly noted "non-SEO content").

## Hands off to

- `remotion-orchestrator` (cross-pack: any video CTA / hero animation)
- `marketing-social-content` (atomise long-form into social posts)
- `marketing-launch-runbook` (slots copy onto launch calendar)

## Per-project keys

- `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` — drafting + variant generation. Missing → returns the brief skeleton and refuses to fabricate copy without LLM access (avoids low-quality regex-templated output).
- `RESEND_API_KEY` / `MAILCHIMP_API_KEY` — only used if user asks the skill to actually send (not draft) email — generally NOT used; copy lives as drafts.
