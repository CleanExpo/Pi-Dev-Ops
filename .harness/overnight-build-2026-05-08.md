# Overnight Build Queue — 2026-05-08
**Generated:** 2026-05-08 | **Target wake-up:** 07:00 AEST | **Operator:** Pi-CEO autonomous swarm
**System state entering overnight:** ZTE v2 85/100 | 371+ polls | 100% autonomy | Semrush 47,800 units available

---

## Quick Reference

| Window | What runs | Goal |
|--------|-----------|------|
| 22:00–00:00 | P0 client revenue tasks | Bulcs + CCW deliverables staged for send |
| 00:00–03:00 | P1 security triage + SEO research | Noise-filter all three security backlogs |
| 03:00–05:30 | P1 SEO content pipeline | Content gaps, keyword plans for all 5 businesses |
| 05:30–07:00 | P2 infrastructure + marketing | Wave 5 wiki update, brand research initiated |
| 07:00 | Morning briefing ready | 3 approvals waiting, metrics on dashboard |

---

## P0 — Client Revenue

### Task 1 — Send Ivi Sims: Proposal + Credentials + Week 1 LinkedIn Posts
- **Priority:** P0
- **What:** Deliver the complete Bulcs Holdings onboarding package to Ivi Sims. Three components: (1) the agency proposal at `.harness/clients/bulcs-holdings-proposal-2026-05-08.md`, (2) client portal credentials, (3) Week 1 LinkedIn posts from `.harness/clients/bulcs-holdings-linkedin-week1.md`.
- **How to execute:**
  ```
  claude --print "Read the files at:
  /Users/phill-mac/Pi-CEO/Pi-Dev-Ops/.harness/clients/bulcs-holdings-proposal-2026-05-08.md
  /Users/phill-mac/Pi-CEO/Pi-Dev-Ops/.harness/clients/bulcs-holdings-linkedin-week1.md

  Draft a single professional email to Ivi Sims (ivi@bulcsholdings.com.au or however Phill has it saved).
  Subject: Your Unite Group onboarding pack — proposal, portal access, and your first LinkedIn posts.
  Body: warm but brief intro, attach or inline both documents, set expectation that SEO briefs and video storyboards follow in 48 hours.
  Save the draft to: /Users/phill-mac/Pi-CEO/Pi-Dev-Ops/.harness/clients/bulcs-holdings-email-draft-2026-05-08.md
  Do not send — Phill approves at 7am."
  ```
- **Expected output:** `/Users/phill-mac/Pi-CEO/Pi-Dev-Ops/.harness/clients/bulcs-holdings-email-draft-2026-05-08.md`
- **Time estimate:** 15 min
- **Dependencies:** None — all source files already exist

---

### Task 2 — CCW "Hire vs Buy" Page Content
- **Priority:** P0
- **What:** Write the complete landing page copy for the CCW "Hire vs Buy" calculator/guide page. This is the highest-leverage organic entry point identified in the Semrush audit — "carpet cleaner hire" has 5,400/mo searches at KD=11.
- **How to execute:**
  ```
  claude --print "You are writing a landing page for carpetcleanerswarehouse.com.au.
  Page title: 'Hire vs Buy a Carpet Cleaning Machine — The Complete Guide for Australian Businesses'
  Target keyword: 'carpet cleaner hire' (5,400/mo, KD=11, AU)
  Secondary keywords: carpet cleaning machine for sale, commercial carpet cleaner, carpet cleaning solution

  The page must:
  - Open with a decision framework (hire costs $X/day vs owning pays off at Y days/year)
  - Include a simple table: hire vs buy comparison (cost, convenience, maintenance, professional use)
  - Feature CCW's product range naturally in the 'buy' section
  - End with a CTA to shop or call for a quote
  - Be AEO-structured with H2/H3 questions that AI assistants would answer
  - Match a direct, practical B2B Australian voice
  - Word count: 1,200–1,500 words

  Save the complete page copy (including meta title and meta description) to:
  /Users/phill-mac/Pi-CEO/Pi-Dev-Ops/.harness/clients/ccw-hire-vs-buy-page-2026-05-08.md"
  ```
- **Expected output:** `/Users/phill-mac/Pi-CEO/Pi-Dev-Ops/.harness/clients/ccw-hire-vs-buy-page-2026-05-08.md`
- **Time estimate:** 20 min
- **Dependencies:** Semrush audit already at `.harness/seo/ccw-semrush-audit-2026-05-08.md`

---

### Task 3 — Semrush Competitor Deep-Dive for CCW
- **Priority:** P0
- **What:** Run the full competitor analysis for carpetcleanerswarehouse.com.au via the semrush skill. Extends the existing audit with a full keyword gap report against Steamaster, Freshway, and Agile Equipment — surfaces the 20 highest-value content opportunities CCW is missing.
- **How to execute:**
  ```
  claude --print "Use the semrush skill to run a competitor content gap analysis.
  Primary domain: carpetcleanerswarehouse.com.au
  Competitors: steamaster.com.au, freshwaysupplies.com.au, agileequipment.com.au
  Database: AU
  
  Run: domain vs competitor keyword gap — find keywords all three competitors rank for that CCW does not.
  Sort by: search volume descending, filter KD < 40.
  
  Output: top 20 keyword opportunities with volume, KD, which competitors rank, and recommended page type (product page, category, guide, FAQ).
  Save to: /Users/phill-mac/Pi-CEO/Pi-Dev-Ops/.harness/seo/ccw-keyword-gaps-2026-05-08.md"
  ```
- **Expected output:** `/Users/phill-mac/Pi-CEO/Pi-Dev-Ops/.harness/seo/ccw-keyword-gaps-2026-05-08.md`
- **Time estimate:** 25 min (Semrush API ~10 unit calls)
- **Dependencies:** Semrush API key live, 47,800 units available

---

## P1 — Security Triage (Business Health Gaps)

### Task 4 — CCW-CRM: Triage Top 20 Security Findings
- **Priority:** P1
- **What:** 6,374 security findings in CCW-CRM repo. Run a representative sample analysis — take the top 20 by scanner severity, classify each as true-positive critical / true-positive medium / false positive / noise. Produce a severity reality report. Estimate: likely 80–90% are false positives from scanner pattern matching (self-referential code, test fixtures, commented-out code).
- **How to execute:**
  ```
  claude --print "You are doing a security triage for the CCW-CRM repo (CleanExpo/CCW-CRM).

  Step 1: Check the Pi-CEO scan results for CCW-CRM. Look in:
  /Users/phill-mac/Pi-CEO/Pi-Dev-Ops/.harness/scan-results/
  Find the most recent scan file for ccw-crm.

  Step 2: Pull the top 20 findings by raw severity score.

  Step 3: For each finding, classify it as one of:
  - CRITICAL-REAL: exploitable in production today, needs immediate fix
  - HIGH-REAL: genuine security issue, fix within 1 sprint
  - MEDIUM-REAL: real issue, fix within 2 sprints
  - FALSE-POSITIVE: scanner matched a pattern but no actual risk (e.g., test data, commented code, example values)
  - NOISE: dependency version warnings, informational only

  Step 4: For each CRITICAL-REAL or HIGH-REAL, write a 2-sentence remediation note.

  Step 5: Output a summary: total findings, estimated % false positive, actual critical count, actual high count.

  Save to: /Users/phill-mac/Pi-CEO/Pi-Dev-Ops/.harness/scan-results/ccw-crm-triage-2026-05-08.md"
  ```
- **Expected output:** `/Users/phill-mac/Pi-CEO/Pi-Dev-Ops/.harness/scan-results/ccw-crm-triage-2026-05-08.md`
- **Time estimate:** 30 min
- **Dependencies:** Scan results must exist for ccw-crm in `.harness/scan-results/`

---

### Task 5 — DR-NRPG: Triage Top 20 Security Findings
- **Priority:** P1
- **What:** 3,909 findings in DR-NRPG. Same triage methodology as Task 4.
- **How to execute:**
  ```
  claude --print "Run the same security triage as the CCW-CRM task above, but for the DR-NRPG repo (CleanExpo/DR-NRPG).
  
  Find the most recent DR-NRPG scan file in:
  /Users/phill-mac/Pi-CEO/Pi-Dev-Ops/.harness/scan-results/
  
  Apply the same 5-step triage process. Classify top 20 by severity.
  
  Save to: /Users/phill-mac/Pi-CEO/Pi-Dev-Ops/.harness/scan-results/dr-nrpg-triage-2026-05-08.md"
  ```
- **Expected output:** `/Users/phill-mac/Pi-CEO/Pi-Dev-Ops/.harness/scan-results/dr-nrpg-triage-2026-05-08.md`
- **Time estimate:** 25 min
- **Dependencies:** Task 4 methodology confirmed working

---

### Task 6 — Pi-Dev-Ops: Triage Top 20 Security Findings
- **Priority:** P1
- **What:** 7,218 findings in Pi-Dev-Ops — the highest count. Critical caveat: `scanner.py` is excluded from self-scans per RA-675 (false positives from its own regex patterns). The triage must account for this. Expected: majority are noise from the scanner scanning its own codebase patterns.
- **How to execute:**
  ```
  claude --print "Run the same security triage as Tasks 4 and 5, but for Pi-Dev-Ops (CleanExpo/Pi-Dev-Ops).
  
  Important context:
  - scanner.py is EXCLUDED from scans per RA-675 — any findings pointing to app/server/scanner.py are invalid
  - Pi-Dev-Ops scans itself, so patterns in source code (eval(), dangerouslySetInnerHTML, nosec markers) are intentional
  - Apply extra scrutiny before marking anything CRITICAL-REAL in this repo
  
  Find the most recent Pi-Dev-Ops scan file in:
  /Users/phill-mac/Pi-CEO/Pi-Dev-Ops/.harness/scan-results/
  
  Triage top 20 findings. For each self-referential pattern match, classify as FALSE-POSITIVE and note it.
  
  Save to: /Users/phill-mac/Pi-CEO/Pi-Dev-Ops/.harness/scan-results/pi-dev-ops-triage-2026-05-08.md"
  ```
- **Expected output:** `/Users/phill-mac/Pi-CEO/Pi-Dev-Ops/.harness/scan-results/pi-dev-ops-triage-2026-05-08.md`
- **Time estimate:** 30 min
- **Dependencies:** Tasks 4 and 5 complete (methodology validated)

---

## P1 — SEO Content Pipeline

### Task 7 — RestoreAssist: AEO FAQ Pages
- **Priority:** P1
- **What:** Write 5 AEO-structured FAQ pages for RestoreAssist (restoreassist.app). Each page answers one high-intent question that restoration contractors ask AI assistants and Google. Based on the existing RestoreAssist Semrush audit.
- **How to execute:**
  ```
  claude --print "Read the RestoreAssist Semrush audit at:
  /Users/phill-mac/Pi-CEO/Pi-Dev-Ops/.harness/seo/restoreassist-semrush-audit-2026-05-08.md
  
  Also read the RestoreAssist business charter at:
  /Users/phill-mac/Pi-CEO/Pi-Dev-Ops/.harness/business-charters/restoreassist.md
  
  Write 5 AEO FAQ pages. Each page must:
  - Have a clear question as the H1 (the exact question a contractor would type or say)
  - Answer in the first 2 sentences (for AI snippet capture)
  - Expand with 400–600 words of expert content
  - Include FAQ schema-ready Q&A blocks at the bottom
  - Target IICRC-certified restoration professionals in AU/NZ
  - Reference RestoreAssist features naturally where relevant
  
  Choose the 5 questions from keywords in the audit that have: search intent = informational, monthly volume > 100, KD < 35.
  
  Save all 5 pages to:
  /Users/phill-mac/Pi-CEO/Pi-Dev-Ops/.harness/content/restoreassist-aeo-faqs-2026-05-08.md"
  ```
- **Expected output:** `/Users/phill-mac/Pi-CEO/Pi-Dev-Ops/.harness/content/restoreassist-aeo-faqs-2026-05-08.md`
- **Time estimate:** 40 min
- **Dependencies:** RestoreAssist Semrush audit exists at `.harness/seo/restoreassist-semrush-audit-2026-05-08.md`

---

### Task 8 — DR Platform: Top 10 Content Gaps vs Competitors
- **Priority:** P1
- **What:** The DR Platform (disasterrecovery.com.au) ranks for 985 keywords with 276/mo traffic. Identify the top 10 content gaps — pages competitors have that DR does not — using Semrush content gap analysis.
- **How to execute:**
  ```
  claude --print "Use the semrush skill to run a content gap analysis for the DR Platform.
  
  Primary domain: disasterrecovery.com.au
  Competitors: restorationmasterfinder.com, iicrc.org (AU content), polygongroup.com (AU)
  Database: AU
  
  Find: keywords competitors rank for in positions 1–20 that disasterrecovery.com.au does not rank for at all.
  Filter: informational + commercial intent, volume > 50/mo, KD < 45.
  
  For each of the top 10 gaps:
  - Keyword + volume + KD
  - Which competitor owns it
  - Recommended content type (blog post, service page, case study, FAQ)
  - 1-sentence content brief
  
  Save to: /Users/phill-mac/Pi-CEO/Pi-Dev-Ops/.harness/seo/dr-platform-content-gaps-2026-05-08.md"
  ```
- **Expected output:** `/Users/phill-mac/Pi-CEO/Pi-Dev-Ops/.harness/seo/dr-platform-content-gaps-2026-05-08.md`
- **Time estimate:** 30 min
- **Dependencies:** Semrush API, ~15 units

---

### Task 9 — CARSI: Competitor Keyword Analysis (3 → Target List)
- **Priority:** P1
- **What:** CARSI currently ranks for only 3 keywords. Run a competitor analysis to find what CARSI should be ranking for. Identify the 15 most achievable target keywords based on competitor data and CARSI's service category.
- **How to execute:**
  ```
  claude --print "Read the CARSI business charter at:
  /Users/phill-mac/Pi-CEO/Pi-Dev-Ops/.harness/business-charters/carsi.md
  
  Then use the semrush skill to analyse CARSI's SEO position.
  Domain: carsi.com.au (or whatever domain is in the charter)
  Database: AU
  
  Step 1: Run a quick domain overview — confirm current keyword count and traffic.
  Step 2: Identify CARSI's 3 top competitors (use Semrush competitor discovery if needed).
  Step 3: Run competitor keyword gap — keywords competitors rank for that CARSI does not.
  Step 4: Filter for: volume > 30/mo, KD < 40, relevant to CARSI's service category.
  Step 5: Return the top 15 target keywords with volume, KD, and content type recommendation.
  
  Save to: /Users/phill-mac/Pi-CEO/Pi-Dev-Ops/.harness/seo/carsi-keyword-targets-2026-05-08.md"
  ```
- **Expected output:** `/Users/phill-mac/Pi-CEO/Pi-Dev-Ops/.harness/seo/carsi-keyword-targets-2026-05-08.md`
- **Time estimate:** 35 min
- **Dependencies:** CARSI charter, Semrush API

---

### Task 10 — Synthex: Domain and Content Strategy for Google Indexing
- **Priority:** P1
- **What:** Synthex (synthex.social) is not in the Google index. This is a critical SEO zero — no organic presence before the platform launches publicly. Define the domain + content strategy to get Synthex indexed and ranking within 90 days.
- **How to execute:**
  ```
  claude --print "Read the Synthex business charter at:
  /Users/phill-mac/Pi-CEO/Pi-Dev-Ops/.harness/business-charters/synthex.md
  
  Use the semrush skill to:
  1. Confirm Synthex.social domain status (indexed? any rankings?)
  2. Run a competitor keyword analysis: identify 3 comparable early-stage SaaS platforms in the AU/APAC social/marketing space
  3. Find 10 founding content keywords — the exact terms Synthex should rank for in its first 3 months to build topic authority
  
  Then produce a domain + content strategy document covering:
  - Technical indexing checklist (sitemap, robots.txt, canonical, Core Web Vitals baseline)
  - 10 founding content pieces in priority order (title, target keyword, search intent, word count, internal link plan)
  - One 'authority bet' — the single page Synthex should build first that has the highest chance of ranking #1 in < 90 days
  
  Save to: /Users/phill-mac/Pi-CEO/Pi-Dev-Ops/.harness/seo/synthex-index-strategy-2026-05-08.md"
  ```
- **Expected output:** `/Users/phill-mac/Pi-CEO/Pi-Dev-Ops/.harness/seo/synthex-index-strategy-2026-05-08.md`
- **Time estimate:** 45 min
- **Dependencies:** Synthex charter, Semrush API (~20 units)

---

### Task 11 — NRPG: First Keyword Scan
- **Priority:** P1
- **What:** NRPG has had no SEO scan to date. Run the first baseline keyword scan via Semrush and produce a starting-point SEO snapshot: current rankings, traffic, top opportunities.
- **How to execute:**
  ```
  claude --print "Read the NRPG business charter at:
  /Users/phill-mac/Pi-CEO/Pi-Dev-Ops/.harness/business-charters/dr-nrpg.md
  
  Use the semrush skill to run a first-ever baseline scan for the NRPG domain.
  (Find the live domain from the charter or projects.json)
  Database: AU
  
  Produce:
  - Domain overview: total keywords, estimated monthly traffic, authority score
  - Top 10 current organic keyword rankings (if any)
  - Top 10 keyword opportunities (not yet ranking, volume > 50, KD < 40)
  - 3 competitor domains (auto-discovered by Semrush)
  - One recommended first content piece to publish
  
  Save to: /Users/phill-mac/Pi-CEO/Pi-Dev-Ops/.harness/seo/nrpg-baseline-scan-2026-05-08.md"
  ```
- **Expected output:** `/Users/phill-mac/Pi-CEO/Pi-Dev-Ops/.harness/seo/nrpg-baseline-scan-2026-05-08.md`
- **Time estimate:** 25 min
- **Dependencies:** NRPG charter, Semrush API (~10 units)

---

## P2 — System Infrastructure

### Task 12 — PM-Core CCR Agent: First Autonomous PR Cycle on unite-group Repo
- **Priority:** P2
- **What:** Board Action 4 (PM-Core CCR agent). Initiate the first autonomous PR cycle on the unite-group repo (CleanExpo/unite-group). The CCR agent should pick one open Linear ticket in the UNI team with status Todo, build a PR, and submit it for review. This validates the end-to-end swarm cycle on the unite-group codebase.
- **How to execute:**
  ```
  claude --print "Initiate a PM-Core CCR cycle for the unite-group repo.
  
  Step 1: Query Linear for the UNI team — find the highest-priority ticket with status 'Todo' that is not blocked.
  Step 2: Read the ticket brief.
  Step 3: Clone CleanExpo/unite-group and run the standard Pi-CEO PITER flow:
    - Scan the repo for context
    - Build a grounded brief from the Linear ticket
    - Generate a plan (3 variants, pick highest confidence)
    - Execute via Claude Agent SDK
    - Run confidence evaluator (threshold: 8.5/10)
  Step 4: If confidence >= 8.5, push to pidev/auto-{session_id[:8]} branch and open a PR.
  Step 5: Log the outcome to .harness/session-outcomes.jsonl
  
  Do not merge — this is a supervised cycle. Phill reviews at 7am.
  
  Save a cycle summary to: /Users/phill-mac/Pi-CEO/Pi-Dev-Ops/.harness/artefacts/pm-core-ccr-cycle-1-2026-05-08.md"
  ```
- **Expected output:** A PR on CleanExpo/unite-group + summary at `.harness/artefacts/pm-core-ccr-cycle-1-2026-05-08.md`
- **Time estimate:** 45 min
- **Dependencies:** Linear API live, GitHub token live, Pi-CEO swarm operational

---

### Task 13 — Update Triage Rules Based on Live Run Observations
- **Priority:** P2
- **What:** The Pi-CEO Linear trigger has been live for a full run cycle. Review the triage cache and lesson patterns to update the triage rules — reduce false positive ticket creation, improve severity routing.
- **How to execute:**
  ```
  claude --print "Review the current triage state and propose rule updates.
  
  Read:
  /Users/phill-mac/Pi-CEO/Pi-Dev-Ops/.harness/triage-cache.json
  /Users/phill-mac/Pi-CEO/Pi-Dev-Ops/.harness/lesson-patterns.md
  /Users/phill-mac/Pi-CEO/Pi-Dev-Ops/.harness/lessons.jsonl (last 50 entries)
  
  Analyse:
  1. What pattern of findings is generating the most tickets? Are they real or noise?
  2. Which repos have the highest false-positive rate based on lesson patterns?
  3. What 3 triage rule changes would reduce noise without missing real issues?
  
  Output a proposed rules diff — not implemented yet, just the recommendations in structured format.
  
  Save to: /Users/phill-mac/Pi-CEO/Pi-Dev-Ops/.harness/decisions/triage-rule-update-2026-05-08.md"
  ```
- **Expected output:** `/Users/phill-mac/Pi-CEO/Pi-Dev-Ops/.harness/decisions/triage-rule-update-2026-05-08.md`
- **Time estimate:** 20 min
- **Dependencies:** At least one full scan cycle complete

---

### Task 14 — Wave 5 Wiki Update: Built vs Planned
- **Priority:** P2
- **What:** Update the WIKI.md with an accurate account of what was actually built today (2026-05-08) versus what was in the Wave 5 plan. This keeps the knowledge base honest and gives the morning briefing its system health anchor.
- **How to execute:**
  ```
  claude --print "Produce a Wave 5 build delta report for 2026-05-08.
  
  Read:
  /Users/phill-mac/Pi-CEO/Pi-Dev-Ops/.harness/WIKI.md
  /Users/phill-mac/Pi-CEO/Pi-Dev-Ops/.harness/sprint_plan.md
  /Users/phill-mac/Pi-CEO/Pi-Dev-Ops/.harness/session-outcomes.jsonl (all entries from 2026-05-08)
  /Users/phill-mac/Pi-CEO/Pi-Dev-Ops/.harness/autonomy.jsonl (last 24h)
  
  Produce a delta report covering:
  - What was planned for Wave 5 (from WIKI/sprint plan)
  - What was actually built today (from session-outcomes and autonomy logs)
  - What remains open
  - Any surprises: things that ran but weren't planned, or planned things that didn't run
  
  Append the report to WIKI.md under a new section: '## 2026-05-08 — Overnight Build Delta'
  Also save a standalone copy to: /Users/phill-mac/Pi-CEO/Pi-Dev-Ops/.harness/artefacts/wave5-delta-2026-05-08.md"
  ```
- **Expected output:** WIKI.md updated + `.harness/artefacts/wave5-delta-2026-05-08.md`
- **Time estimate:** 25 min
- **Dependencies:** Session outcomes populated from overnight run

---

## P2 — Marketing Execution

### Task 15 — CCW Brand Research (for Video and Social Content)
- **Priority:** P2
- **What:** Run the remotion-brand-research skill for CCW (carpetcleanerswarehouse.com.au). This feeds the video storyboard and social content pipeline. Without a brand dossier, all video content is generic — this fixes that.
- **How to execute:**
  ```
  Use the remotion-brand-research skill for CCW.
  Brand slug: ccw
  Domain: carpetcleanerswarehouse.com.au
  Known: B2B carpet cleaning equipment supplier, AU, trade professional audience
  ```
- **Expected output:** Brand dossier at `Synthex/packages/brand-config/src/brands/ccw.ts` or equivalent
- **Time estimate:** 30 min
- **Dependencies:** None — public web research only

---

### Task 16 — DR Platform Brand Research
- **Priority:** P2
- **What:** Run the remotion-brand-research skill for the Disaster Recovery Platform (disasterrecovery.com.au). Required before any video or social content is produced for the DR team.
- **How to execute:**
  ```
  Use the remotion-brand-research skill for DR Platform.
  Brand slug: dr
  Domain: disasterrecovery.com.au
  Known: Disaster recovery and restoration services, AU, B2B + insurance channel
  ```
- **Expected output:** Brand dossier for DR Platform
- **Time estimate:** 30 min
- **Dependencies:** None

---

### Task 17 — RestoreAssist: 4 LinkedIn Posts (Klark Brown Voice)
- **Priority:** P2
- **What:** Write 4 LinkedIn posts for Klark Brown (RestoreAssist founder), positioning him as a restoration industry thought leader in AU. Posts should not sell RestoreAssist directly — they build authority. Topics: IICRC compliance challenges, moisture measurement best practices, AI in the restoration industry, contractor education.
- **How to execute:**
  ```
  claude --print "Write 4 LinkedIn posts for Klark Brown, founder of RestoreAssist (restoreassist.app).
  
  Voice: Restoration industry practitioner. Practical, direct, credentialed without being academic.
  Audience: IICRC-certified restoration contractors, project managers, business owners in AU/NZ.
  Goal: Thought leadership — establish Klark as the go-to voice on restoration technology and compliance.
  
  Post topics (one each):
  1. Why most contractors are still using moisture readings wrong (and what IICRC S500 actually requires)
  2. The hidden cost of documentation gaps in insurance claims — what adjusters never tell you
  3. How AI is changing job site documentation — what contractors need to know in 2026
  4. What separates the contractors who scale from those who stay stuck at 3 crews
  
  Format for each post:
  - Hook line (no question hooks — make a statement or share an observation)
  - 3–5 short paragraphs, max 150 words each
  - 1 CTA line (not promotional — invite discussion or share a link to learn more)
  - 3–5 relevant hashtags
  
  Save all 4 posts to: /Users/phill-mac/Pi-CEO/Pi-Dev-Ops/.harness/content/restoreassist-linkedin-klark-brown-2026-05-08.md"
  ```
- **Expected output:** `/Users/phill-mac/Pi-CEO/Pi-Dev-Ops/.harness/content/restoreassist-linkedin-klark-brown-2026-05-08.md`
- **Time estimate:** 25 min
- **Dependencies:** None

---

## Execution Timeline

### First 2 Hours: 22:00–00:00 AEST — Client Revenue Window

```
22:00  Task 1  — Bulcs Holdings email draft (15 min)
22:15  Task 2  — CCW "Hire vs Buy" page content (20 min)
22:35  Task 3  — CCW Semrush competitor deep-dive (25 min)
23:00  Task 4  — CCW-CRM security triage top 20 (30 min)
23:30  Task 5  — DR-NRPG security triage top 20 (25 min)
23:55  CHECKPOINT: P0 and first P1 security tasks complete
```

### Middle of Night: 00:00–04:00 AEST — Long Research Window

```
00:00  Task 6   — Pi-Dev-Ops security triage top 20 (30 min)
00:30  Task 7   — RestoreAssist AEO FAQ pages (40 min)
01:10  Task 8   — DR Platform content gaps (30 min)
01:40  Task 9   — CARSI keyword targets (35 min)
02:15  Task 10  — Synthex index strategy (45 min)
03:00  Task 11  — NRPG baseline keyword scan (25 min)
03:25  CHECKPOINT: All P1 SEO pipeline complete
```

### Pre-Dawn: 04:00–06:00 AEST — Infrastructure + Marketing

```
04:00  Task 12  — PM-Core CCR first autonomous PR cycle (45 min)
04:45  Task 13  — Triage rule update recommendations (20 min)
05:05  Task 14  — Wave 5 wiki delta update (25 min)
05:30  Task 15  — CCW brand research (30 min)
05:30  Task 16  — DR Platform brand research (30 min, parallel with Task 15)
06:00  Task 17  — RestoreAssist LinkedIn posts for Klark Brown (25 min)
06:25  CHECKPOINT: All P2 tasks complete
```

### Final Window: 06:25–07:00 AEST — Morning Briefing Assembly

```
06:25  Compile morning briefing: aggregate outputs from all 17 tasks
06:40  Verify: all expected output files exist
06:45  Verify: no tasks failed silently (check for error markers in outputs)
06:50  Flag any tasks that need manual attention before Phill reviews
07:00  READY — Phill wakes up
```

---

## Morning Briefing Template

**Delivered to:** Phill McGurk  
**Time:** 07:00 AEST, 2026-05-09  
**Format:** Telegram message + this file updated with results

---

### APPROVE FIRST (needs your decision before anything ships)

- [ ] **1. Bulcs Holdings email** — Draft at `.harness/clients/bulcs-holdings-email-draft-2026-05-08.md`. Read it, confirm Ivi's email address, hit send. First client deliverable goes out today. Estimated 5 min review.

- [ ] **2. PM-Core CCR PR** — First autonomous PR on unite-group is open on GitHub. Check the PR, read the diff, approve or request changes. This is a supervised merge — your sign-off is required. Estimated 10 min review.

- [ ] **3. Triage rule changes** — Proposed at `.harness/decisions/triage-rule-update-2026-05-08.md`. Three rule changes that reduce scanner noise. Approve or modify before they are applied. Estimated 5 min review.

---

### DONE WITHOUT REVIEW (ship-ready, informational only)

- [x] **CCW "Hire vs Buy" page copy** — 1,200–1,500 word landing page targeting "carpet cleaner hire" (5,400/mo, KD=11). File at `.harness/clients/ccw-hire-vs-buy-page-2026-05-08.md`. Ready for dev upload to carpetcleanerswarehouse.com.au.

- [x] **Klark Brown LinkedIn posts** — 4 posts, thought leadership voice, ready to schedule. File at `.harness/content/restoreassist-linkedin-klark-brown-2026-05-08.md`.

- [x] **NRPG baseline keyword scan** — First-ever SEO snapshot for NRPG. File at `.harness/seo/nrpg-baseline-scan-2026-05-08.md`. No action required — reference only.

---

### THE OVERNIGHT BUILD SUCCESS METRIC

**Target:** 17 tasks queued. Success = 14+ tasks with output files present and no error markers.

Check this one number at 07:00:
```
ls /Users/phill-mac/Pi-CEO/Pi-Dev-Ops/.harness/clients/bulcs-holdings-email-draft-2026-05-08.md \
   /Users/phill-mac/Pi-CEO/Pi-Dev-Ops/.harness/clients/ccw-hire-vs-buy-page-2026-05-08.md \
   /Users/phill-mac/Pi-CEO/Pi-Dev-Ops/.harness/seo/ccw-keyword-gaps-2026-05-08.md \
   /Users/phill-mac/Pi-CEO/Pi-Dev-Ops/.harness/scan-results/ccw-crm-triage-2026-05-08.md \
   /Users/phill-mac/Pi-CEO/Pi-Dev-Ops/.harness/scan-results/dr-nrpg-triage-2026-05-08.md \
   /Users/phill-mac/Pi-CEO/Pi-Dev-Ops/.harness/scan-results/pi-dev-ops-triage-2026-05-08.md \
   /Users/phill-mac/Pi-CEO/Pi-Dev-Ops/.harness/content/restoreassist-aeo-faqs-2026-05-08.md \
   /Users/phill-mac/Pi-CEO/Pi-Dev-Ops/.harness/seo/dr-platform-content-gaps-2026-05-08.md \
   /Users/phill-mac/Pi-CEO/Pi-Dev-Ops/.harness/seo/carsi-keyword-targets-2026-05-08.md \
   /Users/phill-mac/Pi-CEO/Pi-Dev-Ops/.harness/seo/synthex-index-strategy-2026-05-08.md \
   /Users/phill-mac/Pi-CEO/Pi-Dev-Ops/.harness/seo/nrpg-baseline-scan-2026-05-08.md \
   /Users/phill-mac/Pi-CEO/Pi-Dev-Ops/.harness/decisions/triage-rule-update-2026-05-08.md \
   /Users/phill-mac/Pi-CEO/Pi-Dev-Ops/.harness/artefacts/wave5-delta-2026-05-08.md \
   /Users/phill-mac/Pi-CEO/Pi-Dev-Ops/.harness/content/restoreassist-linkedin-klark-brown-2026-05-08.md \
   2>&1 | grep -c "No such file"
```

**Result = 0** means the overnight build succeeded.  
**Result > 3** means something failed — check the task with the missing file and rerun manually.

---

### Overnight Build Summary (fill at 07:00)

| Metric | Target | Actual |
|--------|--------|--------|
| Tasks completed | 17 | ___ |
| Output files present | 14/14 checkable | ___ |
| Semrush units consumed | < 200 | ___ |
| CCR autonomous PR opened | 1 | ___ |
| Security findings triaged | 60 (20 × 3 repos) | ___ |
| SEO keyword opportunities identified | 55+ | ___ |
| Client deliverables ready to send | 2 (Bulcs email + CCW page) | ___ |

---

_This file is the single source of truth for the overnight build. Any agent executing this queue should update the task checkboxes and append error notes inline if a task fails._
