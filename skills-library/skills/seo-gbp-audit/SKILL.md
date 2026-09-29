---
name: seo-gbp-audit
description: Audits a business's Google Business Profile (GBP) for the single most-impactful local SEO lever — primary category fit. Wrong primary category = map-pack invisible. Returns the recommended primary + secondary category set per the GBP taxonomy, the rationale, and a side-by-side competitor-category comparison. Use when the user says "GBP audit", "Google Business Profile", "map pack", "local SEO start", or after a portfolio brand or client engagement begins.
---

# GBP Category Audit

The cheapest, fastest map-pack lever in local SEO. Wrong primary category = the business is structurally invisible to half its addressable searches. Every Unite-Group portfolio brand + every new client engagement runs this within the first 48 hours.

## When to invoke

- "GBP audit for {brand}"
- "Google Business Profile check"
- "map pack visibility for {brand}"
- "local SEO start" for any new client
- Automatically: the moment a `client-portal-provision` finishes Hour-1 setup

## What it does

Given a business name + primary location + 3-5 competitor business names:

1. **Look up the current GBP primary + secondary categories** for the target business (via the public GBP listing or — if absent — flag that GBP isn't claimed yet, which IS the audit result).
2. **Look up competitors' primary categories** — these are the categories Google believes win the local intent for the keyword set.
3. **Cross-reference against the full GBP taxonomy** (the 4,000+ categories Google publishes). Identify:
   - The recommended **primary** category — usually the one ≥2 of the top-3 ranking competitors use
   - Up to 9 **secondary** categories — niche modifiers that don't displace the primary
4. **Surface mismatches** — primary categories that fail the "what would a customer type into Google Maps" gut test, even if the business technically does the service.
5. **Emit:**
   - `~/2nd Brain/2nd Brain/Wiki/seo-gbp-audit-{brand}-{YYYY-MM-DD}.md`
   - One Linear issue per category change recommended, with rationale
   - One-page client-readable PDF if Phill says `--pdf` or it's a client engagement

## Steps

```
1. Resolve target business → GBP listing URL or Place ID (use DataForSEO if missing).
2. Pull competitor GBPs for the top 3 ranking keywords (use seo-rankings skill).
3. Build category-frequency table: which category wins which competitor.
4. Compare target's current primary vs the modal competitor primary.
5. Write audit Markdown + Linear issue.
```

## Constraints

- Only one primary category per GBP. The output MUST recommend ONE primary — not "either/or".
- Secondary categories are capped at 9 by Google. If the recommendation exceeds 9, pick the highest-volume keyword intents.
- Never recommend a category the business doesn't legitimately serve — Google enforces with suspensions, and the brand-guardian gate blocks it anyway.
- Respect `[[design-preferences]]` — PDFs follow Gun Metal `#1a1a1a` + Candy Red `#dc143c` if `--pdf` is set.
- `[[unite-group-only]]` when scoped to a UG client; otherwise full portfolio scope is fine.

## Output

End with explicit recommendation per `[[always-recommend]]`. Example:

> ✅ GBP audit for **CCW Carpet Cleaning Melbourne** — current primary "Cleaning service" is **WRONG** for the map-pack intent. Recommended primary: **"Carpet cleaning service"** (3/3 top-ranking competitors); add 8 secondary categories (steam cleaning, upholstery, etc.). Linear: UNI-{xxxx}. Next move: get Toby to update before he's back from holiday 26 May — it's a 60-second change with 4-6 week ranking lift.

## Related

- Companion: `[[seo-page-fix]]` (Prompt #14 — on-page audit)
- Companion: `[[seo-gbp-posting]]` (Prompt #7 — 8-week posting plan)
- Playbook: `[[playbook-local-seo-gsc-review]]` (the wider recurring GSC review)
- Underlying APIs: DataForSEO Maps + Labs (already wired)
- Source: `[[research-22-claude-seo-prompts-2026-05-14]]` Prompt #2
