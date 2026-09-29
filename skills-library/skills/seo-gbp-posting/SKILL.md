---
name: seo-gbp-posting
description: Generates an 8-week Google Business Profile posting calendar — 2 GBP posts per week, varied across Offers / Events / Updates / Products, each pre-written with a CTA + image brief + UTM-tracked link. The recurring retention asset that compounds local rankings over months. Use when the user says "GBP posts", "posting calendar", "Google Business Profile content", "8-week plan", or after `seo-gbp-audit` completes and the primary category is correct.
---

# GBP 8-Week Posting Plan

GBP posts are a continuous freshness signal Google uses for map-pack ranking. Most local businesses post zero. Every Unite-Group-managed client gets a rolling 8-week plan, refreshed weekly, scheduled via the swarm.

## When to invoke

- "GBP posts for {brand}" / "8-week plan"
- "Google Business Profile content schedule"
- "posting calendar for {brand}"
- After `seo-gbp-audit` confirms primary category is correct
- Standing weekly cron: every Sunday 18:00 AEST for every Unite-Group-managed brand

## What it does

Given a business + its industry + 3-5 target keywords:

1. **Read the brand's BrandConfig** (Synthex/packages/brand-config/src/brands/{slug}.ts) for voice, audience, forbidden words.
2. **Plan 16 posts** (8 weeks × 2/week), distributed as:
   - 4× Offer (limited promo, with discount + CTA "Call now")
   - 4× Event (workshop, open day, on-site demo, before/after walkthrough)
   - 4× Update (new equipment, new technician, certification, seasonal advice)
   - 4× Product (highlighting a specific service line for SEO depth)
3. **Each post gets:**
   - Headline (≤ 58 chars, hooks first 4 words)
   - Body (≤ 1,500 chars, but optimised at 180-250 — Google truncates beyond that)
   - CTA (one of: Book, Call, Learn more, Order, Sign up)
   - Image brief (subject + composition + brand-locked colour palette — handed to `video-director` or photo-upload reminder)
   - UTM-tracked URL: `?utm_source=gbp&utm_medium=organic&utm_campaign={slug}-{week}-{post_type}`
   - Schedule date (per the cadence — typically Tue + Fri 09:00 AEST)
4. **Emit:**
   - `~/2nd Brain/2nd Brain/Wiki/gbp-posting-{slug}-{YYYY-MM-DD}.md` (human review)
   - `~/Pi-Dev-Ops/.harness/gbp-posts/{slug}-{week}.json` (machine-readable schedule)
   - Linear epic with 16 child issues (one per post), tagged `source:gbp-posting`
5. **If the brand has Composio + GBP connection wired:** auto-schedule via Composio GBP integration. Else: flag the manual step.

## Steps

```
1. Read BrandConfig + recent posts (avoid duplicates).
2. Pull current local search intent (seo-keywords skill).
3. Generate 16 post drafts via marketing-copywriter using BrandConfig voice.
4. Brand-Guardian pass to enforce design preferences and forbidden words.
5. Schedule (Composio GBP or manual fallback).
6. File Linear epic.
```

## Constraints

- **Never** post the same headline twice within a 12-week rolling window.
- **Never** include AI-generated imagery for client posts — only photographed assets or Remotion-rendered brand-locked frames.
- **Never** use Lucide icons or generic stock-style overlays per `[[design-preferences]]`.
- Respect `[[no-ad-spend]]` — these are ORGANIC GBP posts, not promoted; no "boost this post" recommendations.
- AU-specific holidays + ANZAC Day handled — never post promotional Offers on solemn dates.
- Respect `[[no-slack]]` — no Slack-based approval workflow; use the magic-link approval portal at `/approvals/[token]`.

## Output

End with explicit recommendation per `[[always-recommend]]`. Example:

> ✅ 8-week GBP plan for **CCW** generated — 16 posts, 4 of each type, all Brand-Guardian PASS, all UTM-tracked. Composio not wired for GBP yet, so 1st batch needs Toby to paste-and-go when back 26 May (3 min total). Linear epic UNI-{xxxx} with 16 child issues. Next move: wire Composio GBP integration as a P3 task so Week 9+ goes fully autonomous.

## Related

- Pre-req: `[[seo-gbp-audit]]` (Prompt #2)
- Pre-req: `[[seo-page-fix]]` (Prompt #14)
- Brand voice: `Synthex/packages/brand-config/src/brands/{slug}.ts`
- Composer: `marketing-copywriter`
- Gate: `brand-guardian`
- Source: `[[research-22-claude-seo-prompts-2026-05-14]]` Prompt #7 (recurring retention asset)
