---
name: nexus-copywriter
description: Use when generating ANY Unite-Group Nexus customer-facing content that makes a factual claim — service/landing pages, ads, emails, blog posts, review/testimonial responses, or franchise-recruitment copy for a Nexus brand. Triggers on "write copy", "draft copy", "landing page", "service page", "ad copy", "email", "blog post", "campaign", "franchise recruitment", "review response" for a Unite-Group / Nexus brand.
automation: automatic
intents: nexus-copy, copywriting, landing-page, service-page, ad-copy, email-copy, blog-post, franchise-recruitment, review-response, content-generation
---

# nexus-copywriter

**Core principle — PEAK CRAFT CONSTRAINED BY VERIFIABLE TRUTH.** The craft of the ten greatest copywriters, bound so an unprovable claim *cannot physically reach publication*. We do not write claims then check them: we assemble proof, and only then may we write.

Full mythos, Operating Loop and Substantiation Ledger: [`references/DOCTRINE.md`](references/DOCTRINE.md). Transferable craft, AU-law tables and awareness/sophistication frameworks — with citations: [`references/craft-and-law.md`](references/craft-and-law.md).

## When to use
Any Nexus content asserting a checkable fact to a customer or prospect: service/landing pages, ads, emails, blog posts, review/testimonial responses, franchise-recruitment copy.

## When NOT to use
Internal docs, code, non-claim UI microcopy, or pure strategy (positioning → `marketing-positioning`). Never to launder an unprovable claim past the gate.

## The Fable-5 (mythos note)
Five fables, each fusing one inherited craft-gift with one hard constraint (full text in `references/DOCTRINE.md`):
- **I — Enter the conversation, honestly.** Meet the reader's desire; leave no false impression (silence can mislead).
- **II — Channel real demand; diagnose first.** Research 90 / write 10; facts are gathered, never invented.
- **III — Prove it or cut it.** Every factual claim carries a substantiation record, or it does not ship.
- **IV — One proposition, one voice, held over time.** Localise the specifics, never the standard.
- **V — Win the A-pile with real craft.** Earn the open; never fake the reason to act.

## Mandatory workflow (in order — a stage cannot open while a prior gate is open)
1. **RESEARCH** — source every fact *first*; harvest the customer's own words. → **REQUIRED SUB-SKILL:** `storm` / `deep-research` (facts). No source here → no place in the copy.
2. **DRAFT** — write the persuasion; tag every checkable sentence with a Claim-ID. → **REQUIRED SUB-SKILL:** `marketing-copywriter` (craft). An untaggable factual sentence is already invalid.
3. **CITE-OR-CUT** — walk every Claim-ID to a concrete record (invoice, review export, cert, dated price history, dispatch log, licence #). No record → automatic cut or demote to puffery. (Runs inline here for copy this skill authors; for copy written *outside* this workflow, the same gate ships standalone as the sibling `claim-verifier` skill.)
4. **SELF-VERIFY** — run the trust lens; supply named authorship + credential, first-hand detail, inline citations, the trust stack. → **REQUIRED SUB-SKILL:** `eeat` (trust).
5. **BOARD** — cross-specialist + multi-model verification against the skeptic test. → **REQUIRED SUB-SKILL:** `specialist-council` + `boardroom` (verify). Freeze the Substantiation Ledger; it travels with the asset.

## Non-negotiable truth + AU-law gates
- **Prove it or cut it.** ACCC: "a business must be able to prove any claim they advertise" — accurate, truthful, on **reasonable grounds** *at the time made* (onus on us, incl. forward-looking claims).
- **s18 ACL** — misleading/deceptive conduct: intent irrelevant, judged on overall impression, **silence can mislead**.
- **s29 ACL** — false representations re standard, quality, testimonials, price, place of origin.
- **Penalty reality** — body-corporate max is now the greater of **~AUD $100m / 3× benefit / 30% of turnover** (individual max unchanged at **$2.5m**). *Verified current 2026-07-08 (Treasury Laws Amendment — passed 26 Mar 2026, applies to conduct on/after 28 Mar 2026); beyond base knowledge cutoff — re-confirm with ACCC each campaign. Single source of truth: `references/craft-and-law.md`.*
- **Reviews/testimonials** — genuine only; connection or incentive **prominently disclosed** (applies to positive AND negative); no cherry-picking.
- **"Was/now" pricing** — only if genuinely sold at the "was" price for a reasonable prior period.
- **Franchise recruitment** — any earnings/income implication must be Franchising-Code compliant (14-day rule, accuracy statement, item-20) and substantiated.

## DO-NOT-CARRY-FORWARD (hard stop — one hit halts publish)
Unsubstantiated performance/health/"cure" claims · any superlative without dated proof · invented urgency/scarcity (resetting timers, phantom stock, fake "only 2 left") · disguising an ad as personal mail or undisclosed advertorial · fake / connected-undisclosed / incentivised-undisclosed reviews · material silence that changes the impression · unsupported "Australian Made" or green claims · non-Code-compliant earnings copy · "annoy them into buying" repetition · objectifying / stereotyping appeals · skipping the verification test on intuition · repeating unaudited legend statistics as fact. (Complete list: `references/DOCTRINE.md`.)

## Nexus wiring
`automation: automatic` — fires on **every** Nexus content generation, upstream of raw `marketing-copywriter`. It does not replace the craft skills; it wraps them in the truth-spine and owns the terminal gate. Drop-in + composition graph: [`INTEGRATION.md`](INTEGRATION.md).
