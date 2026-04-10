# RestoreAssist — Business Charter

**Source:** Derived from the `restoreassist-national-inspection-report-nir-initiative` skill at `/sessions/zealous-laughing-ptolemy/mnt/.claude/skills/restoreassist-national-inspection-report-nir-initiative/SKILL.md`. Facts about opportunity, business model, and roadmap are sourced from that skill unless marked `[FOUNDER INPUT NEEDED]`.
**Charter date:** 2026-04-11
**Status:** Pre-build. Business model validated in the source skill. Roadmap defined. No code written. No pilot company engaged.
**Portfolio role:** Pi-SEO first target. The skill supplies enough concrete context for Pi-SEO to have something real to monitor on day one.

---

## 1. The problem RestoreAssist solves

The Australian restoration industry runs on fifty-plus different inspection report formats. Fragmentation costs every stakeholder money. Insurance adjusters spend two to three hours decoding each report and twenty to thirty percent of claims require re-inspection due to missing data. Restoration companies incur an extra two thousand to five thousand dollars per claim in disputes, delays, and re-inspections. Admin and TPA companies process inconsistent data across formats. Technician skill varies, so report quality varies with it. The industry lacks credibility because its output looks amateurish.

## 2. The solution — the National Inspection Report (NIR)

A single standardised inspection and scope-of-work format that eliminates ambiguity, prevents re-inspections, allows unskilled technicians to produce professional reports, accelerates claims processing, reduces disputes through standards-justified scope, and professionalises the industry through one credible national standard.

The technical flow has four steps. A technician of any skill level takes measurements (moisture, humidity, temperature), photos (auto-timestamped), and completes a structured form with dropdowns. The mobile app auto-validates the data and uploads it to cloud storage. The NIR generation system automatically produces a professional report by extracting the property address to determine state building code, applying IICRC standards (S500 / S520 / S700), classifying damage by category and class, identifying state-specific triggers, evaluating scope items, estimating costs, and creating a verification checklist with an audit trail. Output ships as PDF for humans, JSON for claims system integration, and Excel for billing and operations.

The key innovation: the technician measures, the system interprets, a junior tech produces pro-level reports.

## 3. Reality check

The problem is real and measurable. Industry-wide savings of four-and-a-half to eight million dollars per claim multiplied by roughly two hundred and fifty thousand annual claims implies a one-point-one-two-five to two billion dollar annual opportunity. The solution is standards-based rather than opinion-based; every finding is defensible by regulation. The business model is sustainable on recurring subscriptions. Insurance companies will demand NIR once it exists, and restoration companies will adopt to keep insurance buy-in — which produces a network effect that locks in adoption.

What is uncertain has a finite list. Pilot company engagement is unnamed. The technology stack is unchosen. Insurance industry pre-validation has not happened. Regulatory alignment beyond IICRC standards is unknown. The two-hundred-and-fifty-thousand annual claims number requires verification from industry bodies.

Overall risk is LOW per the source skill. The core risks (low adoption, technical defects, industry resistance, insurance apathy) are all mitigatable through pilot validation, extensive testing, and early insurance partnerships.

## 4. Scope by phase

**Phase 1 (Months 1–3, Foundation), budget $100–120k.** Design the complete NIR specification — report structure, data model, validation rules. Build the core system — data capture mobile app, cloud backend, NIR generation engine. Build the export pipeline — PDF, JSON, Excel. Extensive testing and QA. Outcome: production-ready system for pilot.

**Phase 2 (Months 4–7, Pilot), budget $50k.** Recruit and onboard three to five pilot companies. Process fifty-plus real claims through the system. Gather feedback from technicians, insurance adjusters, and admin teams. Refine the system based on real-world use. Measure success metrics: report generation rate, technician satisfaction, adjuster approval, cost accuracy.

**Phase 3 (Months 8–12, Public Launch), budget $95k.** Public announcement and positioning as the industry standard. Onboarding campaigns targeting restoration companies and insurers. Sales and customer success teams stood up. Target outcome: fifty-plus companies signed, fifty thousand dollars in Year 1 revenue.

**Phase 4+ (Year 2 onward, Growth).** Expand to one hundred-plus companies (Year 2, three hundred thousand dollars revenue, profitability). Expand to two hundred and fifty-plus companies (Year 3, eight hundred thousand dollars revenue, de facto industry standard). Premium features: API, analytics, white-label. Training certification program. Industry consulting services.

**Out of scope.** Full-service restoration work — the system documents scope, it does not perform restoration. Insurance claim processing — insurers own the claim workflow, NIR feeds into their systems. Per-company custom report formats — the entire business depends on standardisation. International expansion — Year 1 is Australia only.

## 5. Definition of done by horizon

**Done at 30 days:** RestoreAssist has an entry inside Pi-SEO's portfolio monitor. Phase 1 specification work has started with a named design team. At least one pilot company has had a preliminary conversation. Roadmap milestones recorded in `.harness/decisions/`.

**Done at 90 days:** Phase 1 development is fifty percent-plus complete — core data model and mobile app in alpha. Pilot companies are formally committed — three to five signed letters of intent. Insurance industry validation has started — conversations with at least two major insurers. Phase 2 pilot plan exists in writing.

**Done at 12 months:** Phase 1 complete, system production-ready. Phase 2 pilot complete — fifty-plus real claims processed, ninety percent-plus report generation success rate, success metrics met. Phase 3 launch initiated — public positioning live, fifty-plus companies signed up, fifty thousand dollars Year 1 revenue achieved.

## 6. Non-negotiable constraints

1. **IICRC standards compliance.** All damage classification, scope items, and cost estimates must align with IICRC S500, S520, S700. Non-negotiable for industry credibility.
2. **One national format.** No per-company customisation in Phase 1. Custom branding or custom fields is a Phase 4+ premium feature. Phase 1 proves that one format works for everyone.
3. **The founder does not write code.** Every technical decision must be expressible as a business requirement.
4. **Data privacy and security.** The system handles property addresses, damage photos, and technician and homeowner data. Compliance scope pending founder input — GDPR, Australian Privacy Act, state-specific rules.
5. **Pilot must show ROI.** Phase 2 is a revenue exercise, not a validation exercise. Pilot companies must see measurable savings — two to five thousand dollars per claim — within thirty days of go-live, or the model fails.
6. **Network effect must be provable.** By end of Phase 2, the business must demonstrate that insurance companies demand the NIR format rather than tolerate it. Without insurer demand, adoption stalls.

## 7. Stakeholders

- **Phill** — Founder, sole decision-maker, final approver on every phase gate.
- **Restoration companies** — End users. Must see two to five thousand dollar savings per claim to adopt. Pilot names pending.
- **Insurance companies** — Gatekeepers of adoption. Must approve the format and integrate NIR data into claims systems. Target insurers pending.
- **Admin and TPA companies** — Secondary users. Must find NIR easier to process than the current fifty-plus formats.
- **Technicians** — System usability must be high enough for junior technicians to succeed without training.
- **Software delivery team** — Development partner, internal team, or contractor — pending founder decision.
- **Pi-CEO orchestrator** — Acts as business owner and oversight layer until Phase 1 is stable.

## 8. Open questions (founder input needed)

1. Which restoration companies become pilots?
2. Which insurance companies have early validation conversations underway?
3. Technology stack — React + Node.js SaaS, mobile-native, or PWA?
4. Regulatory scope beyond IICRC — building codes, TPA certifications, insurance regulations?
5. Pricing sensitivity — Starter ($99/mo, 10 reports), Professional ($299/mo, unlimited), Enterprise (custom) — validated with restoration companies?
6. Data ownership and custody — technician's company, property owner, or insurance company?
7. Go-to-market sequence — restoration companies first then insurers, or pre-commit an insurer then push to restoration companies?
8. Competitive map — existing platforms attempting to standardise restoration reporting?

## 9. Complementary capability

The source skill references `inspection-to-seo-authority-skill` (at `/sessions/zealous-laughing-ptolemy/mnt/.claude/skills/inspection-to-seo-authority-skill/SKILL.md`). That skill supplies a go-to-market content strategy for RestoreAssist once NIR is built — real inspection reports become case-study-driven SEO content that positions RestoreAssist as the market authority. Phase 4+ scope, not Phase 1.

## 10. How Pi-SEO should treat this charter

Pi-SEO's portfolio monitor should flag RestoreAssist if any of the following go stale:
- No Phase 1 progress update in the `.harness/` tree for more than seven days.
- No pilot company named by Day 30.
- No insurer conversation logged by Day 45.
- Any open question above unanswered at Day 60 when the answer is a precondition for the next phase.

---

*Living document. Allowed to be incomplete. Not allowed to be ignored.*
*Derived from: `/sessions/zealous-laughing-ptolemy/mnt/.claude/skills/restoreassist-national-inspection-report-nir-initiative/SKILL.md`*
*Original orphan location (now deleted): `/Pi-CEO/Pi-SEO/businesses/RestoreAssist/PROJECT.md`*
