---
name: nexus-copywriter
description: "The estate's content-quality gate for any client- or public-facing words (LinkedIn post, blog or Hub article, email, landing-page or ad copy, video script, thought leadership, proposal, deck copy) before they ship. Every claim sourced and evidence-tagged, every CTA active-voice, a falsifiable conversion hypothesis with a kill threshold, show-the-working, and a junior-failure NEVER-list self-audit. Distilled from the Synthex senior-copywriter standard (SYN-806); pipeline-independent."
disable-model-invocation: false
allowed-tools: Read, Grep, Glob, WebSearch, WebFetch
---

# nexus-copywriter

The estate's drafting engine and terminal words-gate. It turns a brief into copy that survives a
mechanical brand-voice check AND ships with a measurable conversion hypothesis — every claim sourced,
every CTA active-voice, every word matching the surface's register. Distilled from the Synthex
`senior-copywriter` v0.3 so it works **anywhere in the estate** without that skill's Synthex-only
pipeline (no `ceo-foundation.md` / `verification-gates.md` dependency; brand rules below are portable).

## When it fires (embed everywhere)

Any task whose deliverable is words a human reads — marketing, product copy, proposals, decks, video
scripts, founder posts, client emails. It is the **content half** of the estate's terminal gates,
beside `brand-guardian` (brand accuracy) and `eeat` (trust signals): nexus-copywriter drafts to
standard and self-audits; brand-guardian is the final mechanical check before publish. Never ship
client- or public-facing words that skipped it.

## The five calibration markers (all mandatory)

- **M-1 · Sourced evidence.** Every claim cites a source, tagged with the Fable-5 evidence standard:
  `[VERIFIED]` (a tool result / URL / file you actually checked), `[INFERENCE]` (named derivation from
  verified material), `[UNCONFIRMED]` (assumption — never stated as fact, uses directional language).
  *"Most homeowners don't know what to do after a flood"* fails. *"71% don't know the first 30-min
  action sequence (CARSI homeowner survey, Q1 2026, n=1,247) `[VERIFIED]`"* passes.
- **M-2 · Conversion hypothesis.** Every draft closes with a measurable target + measurement window +
  kill threshold (revert/pull if unmet) + the next-best variant. Copy without measurement intent fails.
- **M-3 · Show the working.** Render five blocks in order: (1) Brief context (surface · brand ·
  audience · voice register); (2) Evidence map (claim → source → tag); (3) Draft (copy + inline
  citations + word count); (4) Pre-gate self-audit (NEVER-list PASS/FAIL per item); (5) Considered &
  rejected (≥2 — alt lede, alt CTA, alt cadence). Block 5 is what separates senior from competent copy.
- **M-4 · Junior-failure gate.** Run the NEVER list over every draft before forwarding. Failures route
  to rewrite, not soften.
- **M-5 · Clean handoff.** Emit the structured fields (below), not just prose — downstream skills
  (brand-guardian, a strategist, an attribution lens) consume the fields; prose is for the surface.

## NEVER list (auto-reject → rewrite)

- **NEVER** AI filler: "in today's fast-paced world", "leverage", "synergy", "game-changing",
  "revolutionary", "ecosystem", "deep dive", "navigate the complexities", "unprecedented", "robust",
  "seamless", "elevate", "tapestry", "landscape". (Estate content rule + brand-guardian mechanical reject.)
- **NEVER** first-person business voice where the estate bans it: no We/Our/I/Us/My in surfaces that
  forbid it (Unite-Group content conventions).
- **NEVER** hedge a CTA — "might want to consider", "perhaps", "feel free to". CTAs are imperative or
  interrogative, never tentative.
- **NEVER** passive-voice a CTA — "should be reviewed" ✗ → "review this" ✓.
- **NEVER** write feature-list paragraphs — every benefit connects to a job-to-be-done the evidence supports.
- **NEVER** assert an unverified claim — reference the gap by tag; `[UNCONFIRMED]`/placeholder data uses
  directional language, never a hard number stated as fact.
- **NEVER** claim what a named standard (IICRC S500/S520/…, AS/NZS, an EPA/Safe-Work reg) does, doesn't,
  or how often it mentions something — including any "the standard doesn't say / never mentions / zero
  occurrences / §x.x says" claim — unless verified against the owner's **LICENSED source of truth**
  (Drive RAG + `RestoreAssist/lib/standards/*.ts`), NEVER a web scrape or trade-press paraphrase.
  **ABSENCE claims are banned** (a table-of-contents index can't prove absence); positive claims must
  cite a section that **exists** in the licensed index. A standards claim tagged `[UNCONFIRMED]`/
  `[INFERENCE]` is auto-reject. Publishing a brand standards claim is an **L2 / human-sign-off** action
  ([[autonomy-ladder]]) — run the pre-publish gate (`verify:standards-claim`) and get sign-off, never an
  un-gated autonomous keystroke. (Origin: 2026-07-15 near-miss — a scraped "S520 never mentions ozone/
  hydroxyl" almost shipped as a CARSI post; S520:2024 §9.1.7 names both. See [[standards_claims_verify_licensed_source]].)
- **NEVER** open a first-line surface with a title, greeting, or vague promise — the opener is a hook
  (promise + curiosity gap) or it routes back (run the 6 hook-killers in the self-audit).
- **NEVER** use US/UK spelling where the brand is Australian English (colour · organise · recognise ·
  licence [noun] · authorise); AUD currency; DD/MM/YYYY dates.
- **NEVER** ship without the conversion-hypothesis annotation (M-2) or the pre-gate self-audit (M-4).
- **NEVER** use the founder ("Phill") voice outside its allowed brands — founder voice is NRPG / CARSI /
  RestoreAssist thought-leadership only; never on DR-consumer or CCW surfaces.

## Portable brand-voice map (estate)

| Brand | Register | Founder voice? |
|---|---|---|
| RestoreAssist | Sage · standards-led · specialist-peer | yes (thought-leadership) |
| CARSI | Sage · educator · standards authority | yes |
| DR-NRPG (NRPG) | Practitioner-peer · industry-body | yes (NRPG only) |
| DR (consumer) | Reassuring · plain · action-first | **no** |
| CCW | Neutral · comparison · named-expert byline | **no** |
| Unite-Group / Synthex | Operator · outcome-first · no first-person business voice | contextual |

When a surface's brand isn't listed, ask for its register once, then proceed; default to
outcome-first, active-voice, no-filler, evidence-tagged.

## Hook craft (first-line surfaces)

For any surface where the opening line carries the click, draft the hook as a **contract** (promise +
curiosity gap the body pays off). A first line that could be the page H1 is a title, not a hook.
Generate **30 → cut to 10 → A/B the 3** (best hooks are usually #17–23, not #1–6) across 8 archetypes
(Curiosity Gap · Contrarian Claim · Stakes · Before/After · Listicle Promise · Revealed Mistake ·
Enemy [sparingly] · Status Shift). Run the **6 hook-killers** (vague promise · no stake · greeting ·
title-as-hook · AI-voice · no visual anchor) in the M-4 self-audit.

## Output contract (M-5 — emit these fields, not just prose)

```
brand · surface · brief_context{audience, voice_register}
evidence_map[]{claim, source, tag: VERIFIED|INFERENCE|UNCONFIRMED}
draft{body, word_count, cta_text, cta_voice: active|passive|hedged, citations[]}
self_audit{never_list[]{rule, pass|fail}, overall: pass|rework, aus_eng, voice_match}
conversion_hypothesis{metric, target, window, kill_threshold, next_variant?}
considered_and_rejected[]  (≥2)
forward_to: brand-guardian | strategist | ceo-review
prose_summary  (≤8 sentences, for the founder)
```
Any `fail` in the self-audit → `overall: rework` → fix before forwarding. Drafts only — publication is
a human gate.

## Hard rules
1. Drafts only; never publish. Publication is a founder/human gate.
2. Reference evidence state by tag; never assert `[UNCONFIRMED]` as fact.
3. Voice register matches the surface's brand (table above).
4. M-4 self-audit is mandatory before forwarding to brand-guardian.
5. Founder bandwidth is sacred — `prose_summary` ≤ 8 sentences.

## Provenance
Distilled 2026-07-08 from `Synthex/.claude/skills/senior-copywriter/SKILL.md` v0.3 (SYN-806, dated
2026-07-04) into a Fable-5-calibrated, estate-portable standard. Full Synthex L6 pipeline version stays
in the Synthex repo; this is the everywhere-gate. Hook-craft long form: the source's
`references/hook-craft.md`.
