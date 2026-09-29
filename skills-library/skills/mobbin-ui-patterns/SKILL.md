---
name: mobbin-ui-patterns
description: Use BEFORE designing or building ANY UI — page, screen, component, dashboard, or app flow (founder directive 2026-07-13 — every UI build starts from the Mobbin library) — and when the user mentions Mobbin, UI/UX reference, design inspiration, or asks how real apps solve a screen. Emits a cited ui-reference brief from production patterns.
allowed-tools: Read, Grep, Glob, Bash, WebFetch, ToolSearch
---

# mobbin-ui-patterns — production patterns before invented ones

Pull 2–3 comparable production apps from Mobbin (mobbin.com — screen-by-screen UI/UX of
hundreds of shipped iOS/Android/web apps) for the same job-to-be-done, distill the *pattern*,
and hand the build a *ui-reference brief*. Production-proven beats invented: a screen a million
users already navigate is evidence, an imagined layout is a guess.

**Non-negotiable (state it, then honour it every run):** references inform original design.
Steal the pattern — hierarchy, flow, component choice, spacing rhythm — never the pixels.
No asset copying, no screen cloning, no competitor branding. Every reference is cited in the
design note / PR so the choice is traceable.

## Reuse before rebuild (single source of truth — never duplicate these)
- **Curated cache** → vault `Wiki/mobbin-ui-library.md` (founder picks + durable gallery
  links). Read it first; grow it last.
- **Browser lane** → the `browser-routing` skill (Mobbin's full library sits behind login;
  the logged-in Chrome profile is the working route).
- **Visual tokens** → the brand's `DESIGN.md` via `design-intelligence`
  ([[feedback-design-md-boundary]]). This skill supplies patterns; tokens stay theirs.
- **Photo/moodboard references** → `image-reference-research` (industry imagery, not UI).

## Inputs → outputs
Input: the UI job-to-be-done (screen type, brand, platform). Output: a **ui-reference brief**
(format below) in the working notes or PR description, plus any new Mobbin picks appended as
rows to `Wiki/mobbin-ui-library.md`. Completion = the build proceeds from cited patterns, not
from imagination.

## Process

### 1. Frame the job-to-be-done
Name the screen's job in production terms (onboarding, checkout, dashboard, feed, intake form,
settings, catalogue, booking flow) plus platform and audience. Map the brand to its Mobbin
neighbours — the vault page's estate-relevance table seeds this (e.g. fintech-trust → Cleo/Zip,
commerce → Etsy/Depop, content library → Hulu/Tubi, AI assistant → Cleo/Genie).
- **Done when:** the job and 2–3 candidate comparables are named.

### 2. Pull patterns — cache, then live Mobbin
Read `Wiki/mobbin-ui-library.md`; if curated picks cover the job, use their galleries and skip
the live fetch. Otherwise go live, cheapest lane first:
1. ToolSearch `"mobbin"` — use a Mobbin MCP if one is connected (none is, as of 2026-07-13).
2. WebFetch the public discovery/gallery URLs (`mobbin.com/discover/apps/<platform>/...`,
   `mobbin.com/apps/<app>/<id>/screens`).
3. Browser lane per `browser-routing` when content needs the logged-in session.

Study each comparable's actual screens for the target job — not the marketing pages.
- **Done when:** 2–3 comparables have gallery URLs and raw pattern observations each.

### 3. Distill the ui-reference brief
For the target screen, write:

```
## ui-reference brief — <screen> for <brand>
Job: <job-to-be-done>
Comparables: <app> (<gallery URL>) · <app> (<URL>) · <app> (<URL>)
Pattern: <the hierarchy/flow/component choices the comparables converge on>
Divergence: <where they disagree, and which side this build takes — with the reason>
Adaptation: <how the pattern maps onto this brand's DESIGN.md tokens>
```

A brief whose Pattern line could describe any screen is not done — name the specific moves
(e.g. "progressive disclosure: amount first, method second, confirm sheet last").
- **Done when:** the brief names specific pattern moves, a decided divergence, and citations.

### 4. Grow the library, cite the build
Append genuinely reusable new picks to `Wiki/mobbin-ui-library.md` as table rows (app,
positioning, gallery link) — curation, not hoarding: only apps worth consulting again. Paste
the brief (or its Comparables line) into the design note / PR body.
- **Done when:** the wiki row is added (or existing rows sufficed) and the build artifact
  carries the citations.
