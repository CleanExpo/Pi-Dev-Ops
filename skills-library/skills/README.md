---
type: skill-catalog
updated: 2026-09-24
---

# Skills Catalog — Full Inventory

Top-level catalog per the 2-place rule in [CLAUDE.md](CLAUDE.md) — one line per active skill (regenerated 2026-07-06, re-filed 2026-07-14, reconciled against the skill dirs 2026-09-24). Read on demand — never @include into global CLAUDE.md. Router with trigger phrases: [index.md](index.md). External connections: [library/connections.md](library/connections.md).

## Marketing (entry: `marketing-orchestrator`)
- [nexus-copywriter](nexus-copywriter/SKILL.md) — Fable-5 estate-wide content-quality GATE for any client-/public-facing words (post, article, email, landing/ad copy, video script, thought-leadership). Distilled from Synthex senior-copywriter v0.3: sourced+evidence-tagged claims, active-voice CTAs, falsifiable conversion hypothesis + kill threshold, show-the-working, NEVER-list self-audit. Drafts to standard; brand-guardian is the final mechanical gate.
- [nexus-viral](nexus-viral/SKILL.md) — Turns one idea into a hook-first 9:16 hero short and repurposes it into 8 platform-native cuts — YouTube (Shorts) and Instagram (Reels) first, then TikTok and the rest — grounded in live trend + competitor intelligence. Money-maker doctrine: the YouTube cut anchors the set with Google/Bing-indexable search metadata. Four gated stages: Brief Grill → hook + generate (words by nexus-copywriter, render by the Synthex engine) → Broadcast Grill → 1→8 repurpose. Human-gated publish; never self-approves, never fabricates virality signals.
- [marketing-orchestrator](marketing-orchestrator/SKILL.md) — ENTRY POINT for the Marketing Skills Package.
- [marketing-positioning](marketing-positioning/SKILL.md) — Develops value proposition, competitive positioning, and Jobs-to-be-Done articulation for a brand or feature.
- [marketing-icp-research](marketing-icp-research/SKILL.md) — Builds an Ideal Customer Profile (ICP) — firmographics, role, pains, triggers, vocabulary, watering holes, decision…
- [marketing-channel-strategist](marketing-channel-strategist/SKILL.md) — Selects the channel mix and per-channel cadence for a campaign — LinkedIn, YouTube, X, email, paid ads, SEO…
- [marketing-copywriter](marketing-copywriter/SKILL.md) — Writes long-form marketing copy — landing pages, blog posts, email sequences, ad copy, sales-page sections — strictly…
- [marketing-social-content](marketing-social-content/SKILL.md) — Writes short-form social content — LinkedIn posts, X/Twitter threads, Instagram captions, TikTok hooks — and dispatches…
- [marketing-campaign-planner](marketing-campaign-planner/SKILL.md) — Designs an end-to-end marketing campaign — objectives, audience, channels, creative concept, timeline, budget, success…
- [marketing-launch-runbook](marketing-launch-runbook/SKILL.md) — Builds a T-30 to T+30 product-launch runbook with a per-day timeline, owners, asset dependencies, gate checks…
- [marketing-analytics-attribution](marketing-analytics-attribution/SKILL.md) — Designs the UTM scheme, attribution model, and KPI dashboard for a campaign — before launch, not after.
- [marketing-seo-researcher](marketing-seo-researcher/SKILL.md) — Performs keyword research, search-intent classification, SERP analysis, and content-gap discovery for a brand or topic…
- [brand-ambassador](brand-ambassador/SKILL.md) — Generate brand-consistent content, copy, and messaging aligned with Pi-CEO tone and values.
- [output-tournament](output-tournament/SKILL.md) — Use when a creative brief has multiple plausible directions and picking wrong is costly — landing-page hero copy, taglines, headlines, hooks, video concepts, design directions.
- [content-cascade](content-cascade/SKILL.md) — Repurposes one published brand video into blog + LinkedIn + X drafts from its transcript, per-brand per-format voice via `nexus-copywriter`; drafts to vault `Briefs/`, publish founder-gated. Video→writing only; sibling of `nexus-viral` (idea→8 video cuts).

## SEO / GEO (entry: `seo`)
- [seo](seo/SKILL.md) — Full SEO toolkit for Claude Code, powered by the DataForSEO API.
- [seo-quick](seo-quick/SKILL.md) — 60-second SEO snapshot powered by the DataForSEO API.
- [seo-audit](seo-audit/SKILL.md) — Full SEO audit powered by the DataForSEO API.
- [seo-keywords](seo-keywords/SKILL.md) — Keyword research and opportunity scoring via the DataForSEO Keywords Data and Labs APIs.
- [seo-rankings](seo-rankings/SKILL.md) — On-demand rank checking via the DataForSEO SERP API.
- [seo-watchlist](seo-watchlist/SKILL.md) — Track multiple domains and keywords across runs using the DataForSEO SERP API.
- [seo-backlinks](seo-backlinks/SKILL.md) — Backlink profile audit via the DataForSEO Backlinks API.
- [seo-content](seo-content/SKILL.md) — Content topical authority and gap analysis powered by the DataForSEO Labs API.
- [seo-content-gap](seo-content-gap/SKILL.md) — Find keywords competitors rank for that you don't, via the DataForSEO Labs domain_intersection endpoint.
- [seo-competitors](seo-competitors/SKILL.md) — Identify true SEO competitors and quantify the gap, powered by the DataForSEO Labs API.
- [seo-technical](seo-technical/SKILL.md) — Technical SEO site audit via the DataForSEO On-Page API.
- [seo-page-fix](seo-page-fix/SKILL.md) — On-Page SEO audit + concrete fix list for a single URL.
- [seo-gbp-audit](seo-gbp-audit/SKILL.md) — Audits a business's Google Business Profile (GBP) for the single most-impactful local SEO lever — primary category fit.
- [seo-gbp-posting](seo-gbp-posting/SKILL.md) — Generates an 8-week Google Business Profile posting calendar — 2 GBP posts per week, varied across Offers / Events /…
- [seo-report](seo-report/SKILL.md) — Generate a markdown SEO report deliverable from a saved DataForSEO-powered audit.
- [seo-report-pdf](seo-report-pdf/SKILL.md) — Generate a professional, client-ready PDF SEO report from a saved DataForSEO-powered audit.
- [seo-compare](seo-compare/SKILL.md) — Head-to-head SEO comparison of two domains powered by the DataForSEO API.
- [geo-optimization](geo-optimization/SKILL.md) — Generative + Answer Engine Optimization (GEO/AEO) standard for AI search visibility — the 2026 successor to SEO.
- [ai-website](ai-website/SKILL.md) — Entry-point orchestrator for the AI-Websites product line: a normal-looking local-business site with an AI agent, lead capture, follow-up, and CRM under the hood. Owns the pipeline sequence (intake → generate → embed → capture/CRM/drip → deploy → provision); dispatches each stage, runs what is live (generate), reports Phase-2/5-gated stages honestly.
- [ai-website-generate](ai-website-generate/SKILL.md) — Generate stage (dispatched by ai-website): one Google Business Profile location → deterministic, on-brand, schema.org-marked site section whose copy passed the estate validators (Aid Rule, ACL §18, brand voice). Calls the Synthex generator via the `generate_site_from_gbp` MCP tool or the `/api/ai-websites/generate` route; never deploys.
- [eeat](eeat/SKILL.md) — E-E-A-T specialist — a first-class UPSTREAM consult lens that scores content for Google's Experience, Expertise…
- [pi-seo-scanner](pi-seo-scanner/SKILL.md) — Scan interpretation specialist for Pi-SEO findings.
- [pi-seo-remediation](pi-seo-remediation/SKILL.md) — Remediation advisor for Pi-SEO findings that cannot be auto-fixed.
- [pi-seo-health-monitor](pi-seo-health-monitor/SKILL.md) — Portfolio health trend analyst for Pi-SEO.
- [seo-competitor-pages](seo-competitor-pages/SKILL.md) — Generate SEO-optimized competitor comparison and alternatives pages.
- [seo-geo](seo-geo/SKILL.md) — Optimize content for AI Overviews (formerly SGE), ChatGPT web search, Perplexity, and other AI-powered search experiences.
- [seo-hreflang](seo-hreflang/SKILL.md) — Hreflang and international SEO audit, validation, and generation.
- [seo-images](seo-images/SKILL.md) — Image optimization analysis for SEO and performance.
- [seo-page](seo-page/SKILL.md) — Deep single-page SEO analysis covering on-page elements, content quality, technical meta tags, schema, images, and performance.
- [seo-plan](seo-plan/SKILL.md) — Strategic SEO planning for new or existing websites.
- [seo-programmatic](seo-programmatic/SKILL.md) — Programmatic SEO planning and analysis for pages generated at scale from data sources.
- [seo-schema](seo-schema/SKILL.md) — Detect, validate, and generate Schema.org structured data.
- [seo-sitemap](seo-sitemap/SKILL.md) — Analyze existing XML sitemaps or generate new ones with industry templates.
- [nextjs-image-seo](nextjs-image-seo/SKILL.md) — Use when optimising images in a Next.js / React codebase for SEO or accessibility — adding priority to above-fold next/image components, applying aria-hidden to decora…

## Video (entry: `video-director`)
- [video-director](video-director/SKILL.md) — The 15+ year Creative Director persona that owns brief intake, composition selection, and narrative POV for every…
- [video-script-writer](video-script-writer/SKILL.md) — The 15+ year screenwriter persona (Pixar / Apple keynote / Nike spot tier) that engineers hooks (0-3s), retention beats…
- [video-cinematographer](video-cinematographer/SKILL.md) — The 15+ year Director-of-Photography persona (Roger Deakins / Emmanuel Lubezki / Hoyte van Hoytema-tier) that owns shot…
- [video-editor](video-editor/SKILL.md) — The 15+ year editor persona (Walter Murch-tier — the Apocalypse Now / The Conversation editor; "In the Blink of an Eye"…
- [video-sound-designer](video-sound-designer/SKILL.md) — The 15+ year sound designer persona (Skywalker Sound / Sound Lounge / Audio Network-tier) that mixes ElevenLabs…
- [video-colorist](video-colorist/SKILL.md) — The 15+ year colorist persona (Light Iron / Company 3 / The Mill-tier) that applies per-brand LUT + grade pass to every…
- [video-brand-guardian](video-brand-guardian/SKILL.md) — The 15+ year brand director extension of `brand-guardian` specifically for video — frame-by-frame audit of brand-mark…
- [video-distribution-strategist](video-distribution-strategist/SKILL.md) — The 15+ year platform-native distribution expert (early TikTok creator economy + YouTube algorithm + LinkedIn organic…
- [video-use](video-use/SKILL.md) — Edit any video by conversation. Transcribe, cut, color grade, generate overlay animations, burn subtitles — for talking…
- [faceless-video](faceless-video/SKILL.md) — Produce a faceless YouTube-style video (hand-drawn doodle / simple-illustration channels like Zen, Nick Invest)…
- [brand-video](brand-video/SKILL.md) — Produce one or many consistent, on-brand faceless marketing videos end-to-end from a topic — script → ElevenLabs…
- [notebooklm-overlay](notebooklm-overlay/SKILL.md) — Apply the locked-in Unite-Group editorial overlay system to any NotebookLM-generated video (Video Overview output…
- [heygen-director](heygen-director/SKILL.md) — HeyGen specialist agent — owns avatar / talking-head / spokesperson video via the HyperFrames-by-HeyGen MCP, with a…
- [decision-room-production](decision-room-production/SKILL.md) — Production bible for RestoreAssist "Decision Room" episodes — cinematic Remotion compositions at senior production house quality.

## Remotion
- [remotion-brand-research](remotion-brand-research/SKILL.md) — Researches a portfolio company's visual identity from public sources (homepage, about page, marketing copy, GitHub…
- [remotion-brand-codify](remotion-brand-codify/SKILL.md) — Converts a BrandResearch dossier into THREE artifacts — (1) typed BrandConfig TypeScript at…
- [remotion-designer](remotion-designer/SKILL.md) — Visual-design specialist for Remotion compositions.
- [remotion-direction](remotion-direction/SKILL.md) — Use when a Remotion video needs creative direction: hook, visual sequence, scene purpose, motion restraint, and CTA…
- [remotion-script](remotion-script/SKILL.md) — Use when a Remotion marketing video needs a timed script, scene narration, on-screen text, CTA, and voice pacing that…
- [remotion-screen-storyteller](remotion-screen-storyteller/SKILL.md) — Writes the on-screen script for a video — scene-by-scene voiceover, on-screen text, b-roll callouts, and CTA.
- [remotion-composition-builder](remotion-composition-builder/SKILL.md) — Authors or extends a Remotion composition (.tsx) wired to BrandConfig + Storyboard + layout spec + motion.
- [remotion-motion-language](remotion-motion-language/SKILL.md) — Designs a brand-specific motion vocabulary — easing curves, default scene durations, signature entry/exit, transition…
- [remotion-editing](remotion-editing/SKILL.md) — Use when a Remotion video has timing, sync, transition, caption, pacing, or audio-fit risk and needs editing discipline…
- [remotion-production](remotion-production/SKILL.md) — Use when a Remotion video job needs production gates, render evidence, output discipline, and pass/fail validation…
- [remotion-professionalism](remotion-professionalism/SKILL.md) — Use when a Remotion video needs a professional marketing QA pass for brand fit, readability, pacing, typography…
- [remotion-marketing-strategist](remotion-marketing-strategist/SKILL.md) — Tunes a video's format and message for the target channel — LinkedIn, YouTube, Instagram Reel, internal training.
- [remotion-integrations](remotion-integrations/SKILL.md) — Use when /remotion-video needs existing Synthex ElevenLabs, brand-config, Remotion, output storage, Claude, or Hermes…
- [remotion-render-pipeline](remotion-render-pipeline/SKILL.md) — Final step. Synthesises ElevenLabs voiceover for each scene, runs `npx tsx render/render.ts` to produce an MP4…

## Design & UI
- [impeccable](impeccable/SKILL.md) — Frontend design skill (pbakaus/impeccable v3.9.1): 23 `/impeccable` sub-commands (init, craft, shape, audit, critique, polish, bolder, quieter, animate, live…), 46 deterministic anti-pattern detector rules, live browser variant iteration. Third-party; provenance in SKILL.md. Supersedes design-audit's 24-rule detector.
- [creative-director](creative-director/SKILL.md) — Use when someone asks to build, design, make, create, or generate any deliverable from a short prompt — a deck, web page, report, poster, campaign, brand look, prototype — especially when underspecified. Grills the gaps, routes to specialists, runs a polish gate.
- [image-reference-research](image-reference-research/SKILL.md) — Build a rights-aware industry image REFERENCE library (research only — never republish) to design ORIGINAL images from. Query-expanded discovery via Exa/Firecrawl/Apify.
- [swiftui-liquid-glass](swiftui-liquid-glass/SKILL.md) — iOS 26+ Liquid Glass in SwiftUI: build, convert and review glass surfaces. Third-party (FloWritesCode/fwc-swiftui-skills @ c2454e69, MIT), reviewed 17/09/2026: Markdown only, no scripts.
- [swiftui-iphone-duo](swiftui-iphone-duo/SKILL.md) — Adaptive SwiftUI layouts for any window size and the foldable iPhone Duo (hinge, outer display). Same source and review as above.
- [mobbin-ui-patterns](mobbin-ui-patterns/SKILL.md) — Production UI patterns before invented ones: pulls 2–3 Mobbin comparables for the screen's job, emits a cited ui-reference brief, grows the vault library. Founder directive 2026-07-13: fires before ANY UI build.
- [design-system](design-system/SKILL.md) — Design stack orchestrator for Pi-CEO. Routes UI work to the correct specialist skill (design-intelligence…
- [design-intelligence](design-intelligence/SKILL.md) — Master design context skill. Reads/writes DESIGN.md, references 66 brand archetypes from getdesign.md…
- [design-board](design-board/SKILL.md) — Five-persona deliberation skill for brand design — 15+ years of typography, layout, colour, motion, and 3D expertise.
- [design-audit](design-audit/SKILL.md) — Design quality auditor. Detects 24 anti-patterns in UI code (impeccable patterns), critiques visual hierarchy and UX…
- [design-iterate](design-iterate/SKILL.md) — Iteration loop driver for brand design. Calls design-board to generate N variants, renders each at three breakpoints…
- [design-approve](design-approve/SKILL.md) — Labelling + cache step. Once the user approves a variant in design-iterate, this skill writes the canonical brand spec…
- [design-canvas-html](design-canvas-html/SKILL.md) — Generates a self-contained `{slug}.html` preview file that demonstrates a brand's full design system (palette + WCAG…
- [design-family-coherence](design-family-coherence/SKILL.md) — Cross-brand audit. Given a colour family (`restoration | safety | industrial | consumer | training`), reads every…
- [ui-component-builder](ui-component-builder/SKILL.md) — Senior-level UI implementation skill. Generates multi-variant React/Tailwind components grounded in DESIGN.md, applies…
- [ui-ux-pro-max](ui-ux-pro-max/SKILL.md) — Full-stack design workflow skill. Orchestrates all four design layers (intelligence, build, audit, visual-qa)…
- [visual-qa](visual-qa/SKILL.md) — Playwright-powered visual testing skill.
- [frontend-slides](frontend-slides/SKILL.md) — Create stunning, animation-rich HTML presentations from scratch or by converting PowerPoint files.
- [scientific-luxury](scientific-luxury/SKILL.md) — Design system enforcement for Scientific Luxury tier UI.
- [web-design-guidelines](web-design-guidelines/SKILL.md) — Review UI code for Web Interface Guidelines compliance.
- [react-best-practices](react-best-practices/SKILL.md) — React and Next.js performance optimization guidelines from Vercel Engineering.
- [prototype](prototype/SKILL.md) — Build a throwaway prototype to answer a design question.

## Plaud (recordings — read `plaud-shared` first)
- [plaud-shared](plaud-shared/SKILL.md) — First read before any Plaud operation. Auth flow, error handling, output conventions, token refresh.
- [plaud-browse](plaud-browse/SKILL.md) — Browse, list, or paginate through Plaud recordings.
- [plaud-find](plaud-find/SKILL.md) — Find a specific Plaud recording by name keyword, date range, or topic.
- [plaud-read](plaud-read/SKILL.md) — Read the transcript, AI summary, notes, or download audio for a specific Plaud recording.
- [plaud-digest](plaud-digest/SKILL.md) — Summarize multiple Plaud recordings into a digest.
- [plaud-followup](plaud-followup/SKILL.md) — Turn a Plaud recording into a follow-up email, thank-you note, action-item list, SOAP note, or meeting brief.
- [plaud-export](plaud-export/SKILL.md) — Push Plaud content or a generated artifact to Notion, Slack, HubSpot, Linear, Gmail, or a custom webhook.

## Empire-Ops
- [nexus-recall](nexus-recall/SKILL.md) — The estate's wiki-first RECALL GATE. Before answering/researching/planning any task, deterministically pulls grounding from the 2nd-Brain vault via `brain.js find` (scores every estate index, opens the one best section), cites it, and only reaches external on a genuine miss (which self-heals the index). Fable-5: cheap-first, context-lean. Wired into nexus G2. Read-gate counterpart to `nexus-copywriter`.
- [nexus-search](nexus-search/SKILL.md) — Web search on the estate's own tooling instead of a metered vendor API. Vault first via `nexus-recall`, then Exa (proven route), native WebSearch as fallback, docs MCPs for library questions, a real browser only for JS-rendered pages. Reports what was read versus merely listed.
- [nexus-extract](nexus-extract/SKILL.md) — URLs to clean text, batched in one call. Verifies each extraction returned real body content rather than a consent banner or truncation, and names every URL that failed instead of folding it into the summary.
- [nexus-research](nexus-research/SKILL.md) — Multi-source research returning graded findings (established / single-sourced / contested / unestablished) plus what could not be established and what would settle it. Fans out differently-angled searches, not repeated synonyms.
- [nexus-enrich](nexus-enrich/SKILL.md) — Entity lists to sourced tables, one source per cell, blanks where nothing was found. Resolves identity before enriching; never guesses an email format or estimates a headcount. ABN Lookup / ASIC preferred for Australian entities.
- [empire-status](empire-status/SKILL.md) — Instant empire status snapshot. Queries Pi-CEO, Supabase, Linear, and Hermes to produce a 30-second executive briefing…
- [inbox-triage](inbox-triage/SKILL.md) — Morning Gmail triage: buckets last 24h into leads/urgent/warm/partners/meetings/noise, researches real leads to a GO/NO-GO + drafted reply, writes a one-glance brief to vault `Briefs/`. Draft-only — send stays founder-gated.
- [ceo-board](ceo-board/SKILL.md) — Transform uncertainty into decisions through structured board deliberation.
- [evidence-board](evidence-board/SKILL.md) — Answer a question or frame a decision with MULTIPLE evidence-backed viewpoints instead of a single verdict.
- [pm-core](pm-core/SKILL.md) — PM-Core — the first autonomous execution agent.
- [production-gate](production-gate/SKILL.md) — Executes the production merge after Phill's explicit approval.
- [qa-lead](qa-lead/SKILL.md) — QA Lead — holds every deliverable against a pass/fail rubric before it ships to a client or merges to main.
- [brand-guardian](brand-guardian/SKILL.md) — Brand Guardian / Editorial Standards enforcer — quality gate for all non-code output before it reaches a client portal…
- [client-portal-provision](client-portal-provision/SKILL.md) — Thin wrapper around the Pi-CEO Hour-1 provisioner.
- [sow-draft](sow-draft/SKILL.md) — Drafts a milestone-based Statement of Work for a Unite-Group client.
- [stripe-milestone-invoice](stripe-milestone-invoice/SKILL.md) — Creates a Stripe Customer + Product + AU GST Tax registration + Payment Link for the deposit milestone, plus draft…

## C-Suite & Portfolio Intelligence
- [ceo-mode](ceo-mode/SKILL.md) — CEO-level strategic analysis and executive communication.
- [cfo](cfo/SKILL.md) — Daily financial visibility across the 11 Unite-Group businesses.
- [cmo-growth](cmo-growth/SKILL.md) — Daily marketing visibility across the 11 Unite-Group businesses.
- [cto](cto/SKILL.md) — Daily platform-health visibility across the 11 portfolio repos.
- [cs-tier1](cs-tier1/SKILL.md) — Tier-1 customer support across the 11 portfolio brands.
- [daily-6-pager](daily-6-pager/SKILL.md) — Stripe-style daily executive brief assembled from CFO + CMO + CTO + CS snippets, the latest Margot deep-async insight…
- [analyst](analyst/SKILL.md) — Research and intelligence doctrine — the directing analysis layer for growth and sustainability data collection.
- [analyzing-customer-patterns](analyzing-customer-patterns/SKILL.md) — Outcome feedback loop analyser. Reads shipped feature records + post-ship signals, detects patterns in what worked vs…
- [growth-sustainability-data](growth-sustainability-data/SKILL.md) — Method for collecting and gathering data for growth and sustainability across the 11-business portfolio.
- [boardroom](boardroom/SKILL.md) — Multi-model triangulation for high-stakes decisions.
- [product-manager](product-manager/SKILL.md) — Senior Product Manager Engineer (15+ years SaaS delivery).
- [maintenance-manager](maintenance-manager/SKILL.md) — Senior Maintenance Manager (15+ years production systems).
- [security-audit](security-audit/SKILL.md) — Senior Security Officer (15+ years white/black hat experience).
- [pi-governance-gate](pi-governance-gate/SKILL.md) — Run a strategic output through the 9-persona CEO Board before it distributes.

## Pi-CEO Platform (Chief-of-Staff plumbing)
- [intent-parser](intent-parser/SKILL.md) — Classify an inbound Telegram message into one of six intent types so the Chief of Staff can route to the right role.
- [email-listener](email-listener/SKILL.md) — Convert inbound Gmail messages into Pi-CEO sessions via webhook → intent-parser → orchestrator.
- [calendar-watcher](calendar-watcher/SKILL.md) — Convert calendar event creation/modification/deletion into Pi-CEO actions.
- [telegram-draft-for-review](telegram-draft-for-review/SKILL.md) — Draft an outbound Telegram message and gate it behind a human reaction (👍 send, ❌ revise) before any actual send…
- [audit-emit](audit-emit/SKILL.md) — Centralised audit emitter sitting in front of every Dispatcher step + every Scribe send + every CoS routing decision.
- [pii-redactor](pii-redactor/SKILL.md) — Detect and redact personally identifiable information from any payload before it enters logs, prompts, or outbound…
- [pi-ceo-docparser](pi-ceo-docparser/SKILL.md) — Parse PDF / DOCX / TXT into structured ParsedDoc (text + pages + tables + metadata).
- [pi-dev-linear-contract](pi-dev-linear-contract/SKILL.md) — Binding Pi-Dev-Ops × Linear contract — Pattern B repo→project routing, autonomy pickup requires status Ready for Pi-Dev…
- [margot-align](margot-align/SKILL.md) — Aligns Margot's knowledge corpus with the latest 2nd Brain wiki, Pi-CEO health data, and empire context.
- [margot-bridge](margot-bridge/SKILL.md) — Bridge from Pi-CEO orchestrator to Margot's standalone Gemini-powered research MCP server at ~/.margot/.
- [margot-routing](margot-routing/SKILL.md) — Linear routing checklist for Margot — place broad ideas in the parent project first, then copy to vertical projects…
- [margot-sandcastle-bridge](margot-sandcastle-bridge/SKILL.md) — After a Margot Deep Research finding completes, classify "action-shaped vs informational" via existing intent_router…
- [skybridge-rollout](skybridge-rollout/SKILL.md) — Unite-Group rollout plan for Skybridge MCP-Apps framework — which businesses get an MCP App, in what order, with what…

## Orchestration & Tiers
- [pantheon](pantheon/SKILL.md) — Council of sourced minds: graded-citation persona emulations deliberate (blind → grill-me cross-exam → judge chairman) into a dissent-preserving, ACH-based verdict. Convene gate keeps trivial questions out.
- [forge](forge/SKILL.md) — Verdict → skill: 8 gated phases (new-spec gate, eval-first, OWASP scanner + AI-BOM, quarantine registration). Human promotes; forge never self-registers.
- [build-tournament](build-tournament/SKILL.md) — Compete-mode for BUILT artifacts (Angela Jiang pattern): 3 isolated persona contestants (operator/strategist/skeptic) each build the full artifact in worktrees, a blind judge scores against a pre-declared rubric, champion revised with judge feedback + grafts from losers. High-stakes builds only; sibling of `output-tournament` (creative variants).
- [gauntlet-loop](gauntlet-loop/SKILL.md) — (/gauntlet-loop) Turns a goal into ONE ~150-word paste-ready prompt: offers 2–3 named/fetchable/comparable quality bars, then writes a prompt that makes a fresh session fan out builder+harsh-critic pairs per piece and `/loop` until the critic picks ours in a blind label-stripped A/B. Exit is winning, never a round count. Upstream of the build — sibling of `build-tournament` (which runs the contest itself). Technique by Matt Shumer; packaging by RoboNuggets (CC BY 4.0).
- [gauntlet-pair](gauntlet-pair/SKILL.md) — Sub-skill of `gauntlet-loop` (no router row; dispatched by it). Emits a MATCHED PAIR of prompts — Claude Desktop (leans on its native leased worktree, no `/loop`) and Claude CLI (`/loop` + `ultracode`) — grinding SEPARATE projects at once. Exit is 100% AAA+: every piece simultaneously at a rung derived from repeated blind wins under fresh-context critics, never a score out of 10. Ships `claim.mjs`, an advisory atomic-mutex project claim so the two surfaces cannot overlap.
- [tier-orchestrator](tier-orchestrator/SKILL.md) — The orchestrator plans, decomposes briefs, and delegates to lower tiers.
- [tier-architect](tier-architect/SKILL.md) — Design tier configurations - which models for which roles.
- [tier-worker](tier-worker/SKILL.md) — Workers execute discrete, well-scoped tasks quickly.
- [tier-evaluator](tier-evaluator/SKILL.md) — QA agent that grades output against explicit acceptance criteria.
- [auto-generator](auto-generator/SKILL.md) — Generate tier configs from project briefs automatically.
- [token-budgeter](token-budgeter/SKILL.md) — Track and enforce token budgets per tier.
- [context-compressor](context-compressor/SKILL.md) — Compress context at tier boundaries to save tokens.
- [dispatcher-core](dispatcher-core/SKILL.md) — Cross-tool workflow primitive. Executes a declared sequence of steps that chain Linear, Gmail, Calendar, Margot…
- [cross-tool-flow](cross-tool-flow/SKILL.md) — Declarative YAML/JSON authoring surface over dispatcher-core.
- [parallel-delegate](parallel-delegate/SKILL.md) — Split work across multiple Claude subagents running concurrently when a task has independent subtasks.
- [persistent-subagents](persistent-subagents/SKILL.md) — Keep one warm, named specialist per domain and feed it via SendMessage resume; tiered context economy (T0 conserve / T1 maximize / T2 absorb), naming, retirement at ~300k, transcript fallback.
- [chrome-account-align](chrome-account-align/SKILL.md) — Deterministic Chrome/claude.ai account alignment: one pinned Chrome profile per machine matching the CLI account; aligner scripts (macOS zsh + Windows PowerShell); self-heal steps for "extension not connected".
- [terminal-orchestrator](terminal-orchestrator/SKILL.md) — Safely manage long-running tmux-based dev workflows (build, test, watch, log tailing) on the local machine via a…
- [specialist-council](specialist-council/SKILL.md) — AI Communication Intelligence layer — the bidirectional cross-specialist consultation protocol that makes specialist…
- [pi-dev-ops-model-farm](pi-dev-ops-model-farm/SKILL.md) — Multi-CLI agent farm orchestrator. Manages Claude Code (3x Max Plan accounts) and OpenAI Codex CLI (1x Max/Plus account) as tmux-based background workers.
- [fleet-compute](fleet-compute/SKILL.md) — Use BEFORE any heavy multi-agent, corpus-mining, research or batch task to split work across the whole Nexus fleet instead of one machine.
- [cloud-node](cloud-node/SKILL.md) — How an ephemeral managed Claude Code container (claude.ai/code, the mobile and web app, a GitHub Action) joins the estate as a first-class node instead of working blind.
- [estate-mailbox](estate-mailbox/SKILL.md) — The async channel between fleet nodes.
- [estate-sync](estate-sync/SKILL.md) — Use when fleet machines have stale/diverged skills or config ("update didn't reach the other computer"), when setting up a new machine, or when the estate-sync log sho…
- [genesis-orchestrator](genesis-orchestrator/SKILL.md) — Autonomous project orchestration protocol for Next.js full-stack builds.

## Agent Design & Autonomy
- [agent-workflow](agent-workflow/SKILL.md) — Use when defining, scoping, promoting, or debugging an agent or ADW — the 5-part agent contract, scoping formula…
- [agent-expert](agent-expert/SKILL.md) — Act-Learn-Reuse cycle for agent improvement over time.
- [agentic-layer](agentic-layer/SKILL.md) — Design products with agent-native architecture.
- [agentic-loop](agentic-loop/SKILL.md) — Infinite self-correcting iteration until completion criteria met.
- [agentic-review](agentic-review/SKILL.md) — Review agent output for quality, not just correctness.
- [afk-agent](afk-agent/SKILL.md) — Run agents unattended with stop guards and notifications.
- [piter-framework](piter-framework/SKILL.md) — 5-pillar AFK agent setup - Prompt, Intent, Trigger, Environment, Review.
- [autonomy-ladder](autonomy-ladder/SKILL.md) — Capability-tiered autonomy gating for all agent action — maps the DeepMind AGI→ASI continuum (arXiv:2606.12683) onto…
- [leverage-audit](leverage-audit/SKILL.md) — 12 Leverage Points diagnostic for agent autonomy — with explicit scoring rubrics and ROI guidance.
- [zte-maturity](zte-maturity/SKILL.md) — Zero Touch Engineering maturity model — 4-level assessment with explicit scoring criteria per dimension.
- [kill-switch-binding](kill-switch-binding/SKILL.md) — Telegram /panic command + dashboard kill button.
- [sandcastle-runner](sandcastle-runner/SKILL.md) — The primitive. Wraps a single Sandcastle invocation (`npx sandcastle run`) so Pi-CEO orchestrator can spawn AFK…
- [compound-development-loop](compound-development-loop/SKILL.md) — Agentic development operating loop for non-engineer-led builds: expand the idea, research surrounding advances, produce…

## TAO Engine
- [tao](tao/SKILL.md) — The Tao is the autonomous execution engine that ties self-direction with governance. Orchestrates /nexus (routing), /tao-loop, /tao-judge, and /session-handoff into a single autonomous mission-runner.
- [tao-skills](tao-skills/SKILL.md) — Master index of all 31 TAO skills.
- [tao-loop](tao-loop/SKILL.md) — Judge-gated autonomous coding loop runner.
- [tao-judge](tao-judge/SKILL.md) — Single-scalar termination gate for the TAO judge-gated loop.
- [tao-boomerang](tao-boomerang/SKILL.md) — Token-efficient one-shot dispatch with summary-only return.
- [tao-tdd-pipeline](tao-tdd-pipeline/SKILL.md) — Test-first iteration pipeline. Composes on tao-loop + tao-judge to enforce red→green→refactor discipline.
- [tao-context-mode](tao-context-mode/SKILL.md) — Summary-index + on-demand expansion. Walks a repo once, summarises every source file (~200B vs raw 5-50KB), and serves…
- [tao-context-vcc](tao-context-vcc/SKILL.md) — Deterministic, LLM-free conversation compactor for TAO sessions.
- [tao-codebase-wiki](tao-codebase-wiki/SKILL.md) — Self-updating per-directory WIKI.md files driven by post-merge git history.
- [claude-max-runtime](claude-max-runtime/SKILL.md) — Execute TAO natively within Claude Max subscription.
- [pi-integration](pi-integration/SKILL.md) — Bridge TAO to pi-mono runtime for multi-provider support.

## Process / Planning Gates
- [proof-discipline](proof-discipline/SKILL.md) — Before marking ANY gate, test or task passing — "verified", "green", "done", "fixed", "shipped". Catches vacuous verification, claims never checked against the live system, silent caps, deployed-vs-source drift. _(was live and routed but missing from this catalog until 2026-08-03)_
- [senior-harness](senior-harness/SKILL.md) — Diagnose and repair an entire software or AI system across every stack plane, expose false-green evidence, and turn escaped defects into permanent recurrence controls.
- [control-design](control-design/SKILL.md) — WRITE path: design a control so it can actually fail. Precondition/vacuous controls, first-run-must-be-red, fixtures that generate rather than hardcode secrets, verifications that require handling what they protect, invented-credential startup branches. _(was live and routed but missing from this catalog until 2026-08-03)_
- [control-scope](control-scope/SKILL.md) — SCOPE path, split out of `control-design` 2026-08-03: what did the instrument look at, and what sentence may I write? Misaimed instruments, fixed sets going stale, canary placement, claim-shape qualifiers. Worked incidents in `references/worked-examples.md`.
- [control-readout](control-readout/SKILL.md) — READ path counterpart to `control-design`: interpreting a verdict you did not write. A differential ATTRIBUTES, it does not EXONERATE; `skipped` ≠ `passed`; a red baseline hides other red; absent ≠ benign. Fires on "already failing", "pre-existing", "just the environment".
- [wayfinder](wayfinder/SKILL.md) — (/wayfinder) Chart an effort too big for one agent session as a shared map of decision tickets on the issue tracker; resolve one at a time until the way is clear. Sits upstream of /spm — run it when there's too much fog to spec directly. From mattpocock/skills.
  - [grilling](grilling/SKILL.md) — Interview the user relentlessly, one question at a time, until a shared understanding is reached. Wayfinder's default HITL ticket type; also usable standalone. _(distinct from `grill-me` / `grill-with-docs`)_
  - [domain-modeling](domain-modeling/SKILL.md) — Build/sharpen a project's ubiquitous language and record ADRs (formats in `ADR-FORMAT.md` / `CONTEXT-FORMAT.md`). Paired with grilling when charting a map's destination.
  - [research](research/SKILL.md) — Spin up a background agent to investigate a question against primary sources and capture findings as a repo Markdown file. Wayfinder's AFK research ticket type.
  - [prototype](prototype/SKILL.md) — Build a throwaway prototype (state model / logic / UI — see `LOGIC.md`, `UI.md`) to answer a design question. Wayfinder's prototype ticket type.
  - [setup-matt-pocock-skills](setup-matt-pocock-skills/SKILL.md) — (/setup-matt-pocock-skills) One-shot per-repo config for these skills: issue tracker (GitHub / GitLab / local-markdown), triage labels, domain-doc layout. Run once before wayfinding a new repo; defaults to a local-markdown tracker under `.scratch/`.
- [crew](crew/SKILL.md) — (/crew) Dispatch the eight operational roles from `.harness/agents/registry.yaml` (scout, planner, builder, verifier, reviewer, security, ci-recovery, release-monitor) against one task, each grounded in the vault via brain.js before it reads any code, each gated by an allowlist against its `risk_tier_ceiling`. Every step lands in an append-only, flock-serialised evidence log that mirrors to `~/Pi-CEO/.harness/swarm/` when present and never creates it when absent; the terminal render reads only that log and distinguishes an absent run from a broken one from an empty one. Grounding drift is stamped DEGRADED, never hidden.
- [capture-intent](capture-intent/SKILL.md) — (/capture-intent) Stage 1 of Anthropic's AI-Native SDLC Playbook: turns a raw founder thought (Mission Control's Capture Intent box, a paste, or a dictation here) into an accepted `intent.md` — problem, proposed outcome, affected users and systems, constraints, open questions — stages it where gstack `/plan-ceo-review` reads its design doc (proven by running the review's own lookup), then runs the CEO review. The required front door to `/plan-ceo-review`.
- [waterline](waterline/SKILL.md) — (/waterline) Dictate a goal and ramble at it. Loads the project's North Star pack, holds five intent slots and advances on the turn that adds nothing new (never asks "are you done"), sets one named/fetchable/comparable bar, researches recall-first, drafts a build-ready brief — then hands it to a fresh **Codex** process as an independent challenger (read-only sandbox, schema-enforced report, claims anchored verbatim or discarded) and loops until zero blocking findings survive, or emits an honest UNCONVERGED. The only Codex-as-adversary path aimed at intent rather than a diff. Upstream of `/spm`.
- [spm](spm/SKILL.md) — Senior Project Manager command (/spm). Use before implementation to turn a rough task, feature, bug, idea, ticket, PR…
- [judge](judge/SKILL.md) — Mandatory pre-build challenge gate (/judge).
- [grill-me](grill-me/SKILL.md) — Run a relentless one-question-at-a-time interview on a sketch or plan until every branch of the decision tree resolves…
- [grill-with-docs](grill-with-docs/SKILL.md) — Use BEFORE writing a spec or plan when the feature involves domain entities, ambiguous terminology, or new vocabulary…
- [define-spec](define-spec/SKILL.md) — Spec writer. Converts a raw idea into a structured specification with PITER classification, goals/non-goals…
- [technical-plan](technical-plan/SKILL.md) — Technical planner. Reads a spec.md and produces a concrete implementation plan: files to change, approach, effort…
- [forward-planner](forward-planner/SKILL.md) — Research a project and plan 15+ moves ahead before building anything.
- [design-pressure-test](design-pressure-test/SKILL.md) — Before writing code for a non-trivial feature or change, spawn an Opus subagent to pressure-test the proposed approach…
- [opus-adversary](opus-adversary/SKILL.md) — Run a Claude-native adversarial review using an Opus subagent to challenge the design, find race conditions, and…
- [review-command](review-command/SKILL.md) — /review specialised command skill. Use when the operator asks for /review, review, code review, launch review, or…
- [verify-test](verify-test/SKILL.md) — Test verifier. Interprets smoke test and CI results, classifies pass/fail, detects flaky tests and coverage…
- [task-completion-gate](task-completion-gate/SKILL.md) — Invoke before reporting a task "done", "complete", "fixed", "green", or "shipped" — the final gate that blocks a…
- [readiness-architect](readiness-architect/SKILL.md) — Production-Readiness Architect command (/readiness-architect).
- [session-handoff](session-handoff/SKILL.md) — Gate the tree green, then generate a precise session handoff before stopping, switching terminals, opening a PR…
- [resume-from-handoff](resume-from-handoff/SKILL.md) — Resume work from a session handoff. Reads the latest handoff, verifies current repo state against it, reconciles any…
- [engineering-requirements](engineering-requirements/SKILL.md) — Use before any spec or non-trivial change becomes code — dispatches the principal-engineer bench (17 specialist seats) to return the engineering requirements the autho…
- [spec-development](spec-development/SKILL.md) — Use when starting ANY non-trivial development work — a feature, integration, refactor, or bugfix bigger than one file — BEFORE writing code.
- [plan](plan/SKILL.md) — Architecture planning with deep reasoning.
- [implement](implement/SKILL.md) — Full build pipeline.
- [domain-modeling](domain-modeling/SKILL.md) — Build and sharpen a project's domain model.
- [grilling](grilling/SKILL.md) — Grill the user relentlessly about a plan, decision, or idea.
- [brain-scope](brain-scope/SKILL.md) — Scope a task by pulling the latest note from the user's Obsidian "2nd brain" vault, gather related context from the vault, run a client-friendly multiple-choice dialog…
- [unlazy](unlazy/SKILL.md) — Turn substantial delivery work into a dependency tree with owned files, rolling dispatch, executable gates, and exact completion evidence.
- [model-router](model-router/SKILL.md) — Use before substantive work when choosing whether to work inline, delegate, fan out, or escalate based on ambiguity, stakes, scope, repetition, privacy, and prior fail…
- [senior-harness-control](senior-harness-control/SKILL.md) — Use before substantive project work that requires governed discovery, delegation, verification, or recovery from repeated failure.
- [goal-circuit-breaker](goal-circuit-breaker/SKILL.md) — Use when a /goal Stop-hook keeps re-firing the same "Condition unsatisfied" verdict across turns without state changing — detect the unsatisfiable-loop, classify the r…
- [no-dead-ends](no-dead-ends/SKILL.md) — Use the moment you are about to write "cannot", "unable", "blocked", "not possible", "unavailable", "no way to", "would need permission", or to report a task as stopped.
- [dead-checks](dead-checks/SKILL.md) — Use BEFORE trusting any check, guard, test, gate, verifier or metric that reports success — and before writing a new one.
- [credential-custody](credential-custody/SKILL.md) — Use when a secret, token, password or key is about to be written into a test, handled during a verification, or read at startup.
- [claim-verifier](claim-verifier/SKILL.md) — The runnable cite-or-cut gate for FINISHED Nexus copy — walks every checkable factual claim in a completed asset, resolves each to a substantiation record or cuts it…

## Launch & Ship
- [reticle-verify](reticle-verify/SKILL.md) — Drives the running dev app with Reticle (HTTP, no global MCP) and gives donectl a gate command: exit 0 PROVEN, 1 FAILED/UNBOUND/GATE_BLIND, 2 UNPROVEN. Self-test plants an impossible check. Built 17/09/2026 on CARSI.
- [launch-charter](launch-charter/SKILL.md) — The immutable governance charter every autonomous launch agent loads FIRST.
- [launch-project-audit](launch-project-audit/SKILL.md) — Scan the codebase and produce a plain-English map of every feature — what's built, stubbed, orphaned…
- [launch-review](launch-review/SKILL.md) — Aggregate the repo's existing audit skills into ONE prioritized launch-readiness report through four lenses — PM…
- [launch-enhance-debloat](launch-enhance-debloat/SKILL.md) — Make existing code stronger, leaner, and more secure without over-engineering — deletion is often the best change.
- [ship-it](ship-it/SKILL.md) — A launch-readiness PRE-FLIGHT that runs before the existing ship-chain — load the charter, audit build-state, run the…
- [ship-chain](ship-chain/SKILL.md) — Ship Chain orchestrator. Routes /spec /plan /build /test /review /ship commands to the correct pipeline phase, enforces…
- [ship-release](ship-release/SKILL.md) — Release gatekeeper. Validates all pipeline phases are complete, enforces the review score ≥ 8/10 hard gate, documents…
- [northstar-shipit](northstar-shipit/SKILL.md) — NorthStar add-on for /northstar and /ship-it.
- [shipyard](shipyard/SKILL.md) — Overnight start-to-finish runner.
- [gauntlet-ship](gauntlet-ship/SKILL.md) — The gauntlet variant for getting a real product to market - grinds a ship backlog to live instead of grinding one surface against a competitor.
- [ci-quality-parity](ci-quality-parity/SKILL.md) — Run every gate CI's "Quality Checks" job runs, LOCALLY, before you push or open a PR — so a locally-green branch never opens UNSTABLE.
- [new-feature](new-feature/SKILL.md) — Start a new task in an isolated Git worktree branched from origin/main so multiple agents can work on the same repo in parallel without conflicts.
- [adopt-gstack](adopt-gstack/SKILL.md) — gstack (garrytan/gstack) pinned + curated install for Claude Code and Codex; which `gstack-*` skill (qa, benchmark, careful/freeze, retro, document-release, office-hours) to use vs estate skills.

## CI / Deployment Curators
- [curator-deployment](curator-deployment/SKILL.md) — Use when deploying services, merging PRs, configuring CI pipelines, or setting up tunnel/process launchers.
- [curator-deployment-unknown](curator-deployment-unknown/SKILL.md) — Use when hitting deployment failures in GitHub Actions dependency-review, Vercel rootDirectory config after a monorepo…
- [curator-security](curator-security/SKILL.md) — Prevents the three recurring security failures distilled from portfolio incidents across dr-nrpg, synthex, ccw-crm, and…
- [curator-scheduled-tasks](curator-scheduled-tasks/SKILL.md) — Use when authoring, debugging, or reviewing scheduled tasks that run via the Claude Code scheduled-tasks MCP — covers…
- [mac-mini-external-storage](mac-mini-external-storage/SKILL.md) — Mac Mini only: models, caches, worktrees, TMP, Docker, Ollama, HuggingFace must live on `/Volumes/Storage Unit`, never Macintosh HD.
- [scheduled-tasks](scheduled-tasks/SKILL.md) — Guidelines for writing reliable scheduled task prompts via the Claude scheduled-tasks MCP.
- [vercel-prod-debug](vercel-prod-debug/SKILL.md) — Use when a Vercel-hosted app (esp. Next.js App Router) is misbehaving in production — all /api routes 500 while pages…
- [vercel-env-puller](vercel-env-puller/SKILL.md) — Per-project Vercel env-var manifests (NAMES + targets only — never values).
- [unite-group-ci-recovery](unite-group-ci-recovery/SKILL.md) — How to ship PRs cleanly across the Unite-Group portfolio (Synthex, Pi-Dev-Ops, Disaster-Recovery, DR-NRPG…
- [merge-gate](merge-gate/SKILL.md) — Use before opening any PR, pushing to a shared branch, or merging in this estate — where automation force-readies draft PRs and squash-merges them on green within minutes, so opening a PR is authorising its merge.
- [pr-release-gate](pr-release-gate/SKILL.md) — Require exact-SHA local tests and an independent second-agent PASS before any branch push or pull request action.
- [github-actions-quota-guard](github-actions-quota-guard/SKILL.md) — Use before pushing to a GitHub Free PRIVATE repo, or when Actions jobs fail to start with the "payments failed / spending limit" message. Makes a pushed PR arrive already green (replay CI locally, rebase clean), diagnoses free-tier Actions-minute exhaustion (not a real payment failure), stops futile reruns, and trims workflow minute-bloat.
- [supabase-write-gate](supabase-write-gate/SKILL.md) — Fail-closed PreToolUse gate on Supabase MCP writes.
- [use-railway](use-railway/SKILL.md) — Operate Railway infrastructure: create projects, provision services and databases, manage object storage buckets, deploy code, configure environments and variables, ma…
- [restoreassist-app-store-phase](restoreassist-app-store-phase/SKILL.md) — Use when working on any App Store or Google Play submission task for RestoreAssist — enrollment, certificates, store listings, testing tracks, or release submission
- [restoreassist-scheduled-tasks](restoreassist-scheduled-tasks/SKILL.md) — Use when creating, editing, or fixing scheduled tasks on claude.ai/code/scheduled for RestoreAssist cron endpoints
- [nexus-connector-doctor](nexus-connector-doctor/SKILL.md) — Use when a Unite-Group Nexus app (Unite-Hub / Command Centre, RestoreAssist, Synthex, etc.) shows connector/env/auth symptoms — "No API key found in request", a login/…

## Engineering Conventions & Runtime
- [architecture](architecture/SKILL.md) — Architectural conventions and anti-patterns specific to Pi-Dev-Ops — companion model, sandbox isolation, ZTE leverage…
- [security](security/SKILL.md) — Security patterns and anti-patterns for the Pi-Dev-Ops codebase — path traversal, HMAC webhooks, secrets hygiene…
- [hooks-system](hooks-system/SKILL.md) — Use when adding lifecycle hooks or safety guardrails to a project — the 6 hook types plus the starter guardrail hookset…
- [deployment](deployment/SKILL.md) — Deployment constraints and runtime behaviour for Railway (backend) and Vercel (frontend) — proxy config, redirects…
- [claude](claude/SKILL.md) — Correct patterns for Claude SDK usage, subprocess vs API mode selection, MCP SDK imports, and streaming API call…
- [claude-runtime](claude-runtime/SKILL.md) — Rules for invoking Claude correctly — subprocess vs SDK mode, stream-json parsing, MCP SDK imports, Railway vs local…
- [code-structure](code-structure/SKILL.md) — Use when multiple workflows duplicate the same operational logic, when deciding what belongs in actions vs shared services, or when refactoring repeated operational bl…
- [fix](fix/SKILL.md) — Minimal quick fix.
- [review](review/SKILL.md) — Isolated code review.
- [resume](resume/SKILL.md) — Snapshot recovery.
- [next](next/SKILL.md) — Task transition.
- [ctx](ctx/SKILL.md) — Context health check.
- [quick](quick/SKILL.md) — Use when the user says "/quick", "/quick 3", "give me the short version", "just the takeaways", or "bullet it".
- [bro](bro/SKILL.md) — Use when the user says "/bro", "in plain English", "what does that mean", "explain that simply", or reacts to an answer as too long, too technical, or confusing.
- [unslop](unslop/SKILL.md) — Cut AI tells from text you write or edit for a human reader (commit messages, PR titles and bodies, docs, code comments, replies).
- [setup-matt-pocock-skills](setup-matt-pocock-skills/SKILL.md) — Configure this repo for the engineering skills — set up its issue tracker, triage label vocabulary, and domain doc layout.

## Connectors / Substrates
- [skill-selector](skill-selector/SKILL.md) — The library's check-out / check-in loop, as a tool: `scripts/skill_shelf.mjs find "<task>"` searches active + vault skills (router trigger phrases scored; top 5 only), `checkout` symlinks a vault skill into `~/.claude/skills` (live-reloaded, no restart), `checkin` returns it (symlink-into-vault only, `unlink` never `rm -rf`), `pull` fetches a reviewed, SHA-pinned outside repo into the vault at zero listing cost, `overrides` lists the local long tail as `name-only` so router entry-points keep their descriptions. Search vendored unchanged from sorcerai/skill-router (MIT). ≤5 skills per task, load-on-earn, check in when done.
- [context-cockpit](context-cockpit/SKILL.md) — Audit and reclaim a session's context/token budget in one pass — read /context, trim MCP tools, clear vs compact…
- [connector-routing](connector-routing/SKILL.md) — Decide which connector path to use for a given integration task — Desktop MCP, claude.ai cloud connector, or Composio.
- [composio-cli](composio-cli/SKILL.md) — Help users operate the published Composio CLI to find the right tool, connect accounts, inspect schemas, execute tools…
- [composio-cloud-routine](composio-cloud-routine/SKILL.md) — Pattern for invoking Composio tools from inside a CCR remote routine (cloud-running scheduled agent) when the routine…
- [connecting-meta-facebook-instagram](connecting-meta-facebook-instagram/SKILL.md) — Use when connecting or fixing Facebook/Instagram (Meta) OAuth in a web app — Connect button no-ops or errors, "Meta…
- [supabase](supabase/SKILL.md) — Use when doing ANY task involving Supabase.
- [supabase-postgres-best-practices](supabase-postgres-best-practices/SKILL.md) — Postgres performance optimization and best practices from Supabase.
- [nlm-skill](nlm-skill/SKILL.md) — Expert guide for the NotebookLM CLI (`nlm`) and MCP server - interfaces for Google NotebookLM.
- [browser-routing](browser-routing/SKILL.md) — Use when a task needs a browser — automating a web flow, reviewing or improving UI, debugging a page, recording…
- [chrome-browser](chrome-browser/SKILL.md) — Use when the user asks to browse, click, navigate, fill a form, screenshot, or read content from a live website via the claude-in-chrome MCP tools.
- [playwright-cli](playwright-cli/SKILL.md) — Microsoft's Playwright CLI skill (vendored @ `74354ec`, v0.1.21): headless automation, test generation, tracing, video evidence. In-memory sessions only; routed from `index.md` (the vendored `browser-routing` copy is pinned to Pi-Dev-Ops and cannot name it).
- [archify](archify/SKILL.md) — tt-a1i/archify (vendored @ `9e35d2b`, MIT): validated architecture, workflow, sequence, data-flow and lifecycle diagrams as standalone interactive HTML; reads repo evidence or Mermaid. Update check removed; tracked by `skill-watch`.
- [gs-office-hours](gs-office-hours/SKILL.md) — gstack (adapted @ `b9706f3`, MIT): YC-style forcing questions that turn an idea into a design doc before any code. Hands off to the gs-plan reviews.
- [gs-plan-ceo-review](gs-plan-ceo-review/SKILL.md) — gstack (adapted): founder-mode plan review in 4 scope modes (expand, selective, hold, reduce).
- [gs-plan-eng-review](gs-plan-eng-review/SKILL.md) — gstack (adapted): eng-manager plan review of architecture, data flow, edge cases and tests. Sits beside `engineering-requirements`.
- [gs-autoplan](gs-autoplan/SKILL.md) — gstack (adapted): runs CEO then eng review, decides Mechanical items silently, surfaces Taste and User-challenge items at one final gate.
- [gs-freeze](gs-freeze/SKILL.md) — gstack freeze (rebuilt): per-session lock on Edit/Write to one directory; fail-closed frontmatter hook, no settings.json change.
- [carsi-course-production](carsi-course-production/SKILL.md) — CARSI course build pipeline (symlink from Pi-Dev-Ops; was invisible to the Skill tool until linked 2026-07-14).
- [artlist-mcp](artlist-mcp/SKILL.md) — Use when a task needs AI image or video generation — campaign visuals, hero shots, product or social video, thumbnails, ad creative — through the official Artlist MCP (live-discovered model catalog; carries the credit-spend gate).
- [browser-harness](browser-harness/SKILL.md) — (upstream frontmatter name: `browser-use`; symlink to ~/Developer/browser-harness) — Always use browser-use for any web interaction: automation, scraping, testing, or site/app work.
- [cua-driver](cua-driver/SKILL.md) — Use when a task needs to control a native macOS desktop app that has no dedicated MCP or web UI — DaVinci Resolve, Pro…
- [apify-research-connector](apify-research-connector/SKILL.md) — Use Apify as a credential-gated data adapter for web/social/SERP/marketplace/competitor research with compliance and provenance controls — the paid Apify route card (explicit-cost gate) reached by `image-reference-research` and other research skills.
- [firecrawl](firecrawl/SKILL.md) — Web scraping, search, crawling, and page interaction via the Firecrawl CLI.
- [firecrawl-agent](firecrawl-agent/SKILL.md) — AI-powered autonomous data extraction that navigates complex sites and returns structured JSON.
- [firecrawl-browser](firecrawl-browser/SKILL.md) — DEPRECATED — use scrape + interact instead.
- [firecrawl-crawl](firecrawl-crawl/SKILL.md) — Bulk extract content from an entire website or site section.
- [firecrawl-download](firecrawl-download/SKILL.md) — Download an entire website as local files — markdown, screenshots, or multiple formats per page.
- [firecrawl-map](firecrawl-map/SKILL.md) — Discover and list all URLs on a website, with optional search filtering.
- [firecrawl-scrape](firecrawl-scrape/SKILL.md) — Extract clean markdown from any URL, including JavaScript-rendered SPAs.
- [firecrawl-search](firecrawl-search/SKILL.md) — Web search with full page content extraction.
- [agent-browser](agent-browser/SKILL.md) — Browser automation CLI for AI agents.
- [graphify](graphify/SKILL.md) — Use for any question about a codebase, its architecture, file relationships, or project content — especially when graphify-out/ exists, where the question should be tr…
- [linear-sync](linear-sync/SKILL.md) — Turn audit and review findings into Linear issues in the right project, and define how builder agents pull work from Linear and keep building until the backlog is empty.
- [linear-computer-use](linear-computer-use/SKILL.md) — Use Chrome browser to interact with Linear visually — read the board, pick up tasks assigned by board members, implement them autonomously.
- [find-skills](find-skills/SKILL.md) — Helps users discover and install agent skills when they ask questions like "how do I do X", "find a skill for X", "is there a skill that can...", or express interest i…

## Knowledge & Research
- [second-brain-adopt](second-brain-adopt/SKILL.md) — Put a repo or knowledge bot's markdown knowledge tree under the Second-Brain Standard: OKF index, brain.js check/bench gates, PR lane. Kit SSOT in brain-1 _system/ADOPTION.md.
- [wiki-ingest](wiki-ingest/SKILL.md) — Ingest current session learnings into the Brain-1 wiki at ~/2nd Brain/2nd Brain/Wiki/.
- [wiki-growth](wiki-growth/SKILL.md) — Senior-review-board audit of the 2nd Brain vault — challenge shortlisted ideas, assign dispositions, route survivors to…
- [wiki-lint](wiki-lint/SKILL.md) — Weekly health check for the Brain-1 wiki.
- [daily-intel-brief](daily-intel-brief/SKILL.md) — Morning breadth sweep: GitHub trending (3 windows via gh api), X + web headlines (Exa-first fallback ladder), YouTube momentum ranked by views-vs-subs, into one dated vault brief with ≤3 deeper-look handoffs (`deep-loop`/`nlm-skill`). Raw linked signal over analysis; failed lanes reported, never padded.
- [wiki-query](wiki-query/SKILL.md) — Query the Brain-1 wiki before hitting external research.
- [source-ingest](source-ingest/SKILL.md) — Capture real, credible data from authoritative sites into the 2nd-Brain vault Sources/ library so it can be cited by…
- [nexus-scientific](nexus-scientific/SKILL.md) — Entry point for 149 vendored scientific research skills (K-Dense, MIT). Bioinformatics/genomics, cheminformatics/drug discovery, proteomics, clinical + medical imaging, materials, physics/astronomy, stats + scientific ML, geospatial, plus the research workflow itself (literature review, hypothesis generation, experimental design, peer review, grants, scientific writing/figures/posters/slides). Router only — greps `library/INDEX.md`, checks out exactly ONE sub-skill. Refresh from upstream via `refresh.sh`.
- [storm](storm/SKILL.md) — Use when the user wants a comprehensive, neutral, citation-grounded article, report, briefing, or explainer researched…
- [deep-loop](deep-loop/SKILL.md) — Operator command `/deep-loop <topic>`: the one-topic research-DEPTH engine. Exa-first freshness (never-silent WebSearch/WebFetch fallback ladder) + honest Mixture-of-Agents rounds (perspective proposers → see-all aggregators → Opus synthesist) inside a loop-until-dry swarm that re-targets each round at the prior round's gap ledger. Inherits nexus G1/G3/G6/G7 by pointer; Executive Read over a fully cited report; watch: composes with built-in /loop, edge-triggered pings.
- [research](research/SKILL.md) — Investigate a question against high-trust primary sources and capture the findings as a Markdown file in the repo.
- [dream](dream/SKILL.md) — Use to curate machine-local memory from recent session transcripts — invoked as /dream, /dream status, or /dream apply 1,3.

## B.U.I.L.D. Pipeline
- [data-ingestion](data-ingestion/SKILL.md) — B.U.I.L.D. Inflow orchestration — run the data-capture pipeline as one routine (mine session lake → refresh OKF indexes…
- [sync-claude-sessions](sync-claude-sessions/SKILL.md) — B.U.I.L.D. Inflow pipeline #1 — mine the local Claude Code session lake (~/.claude/projects/**/*.jsonl) for CONTENT…
- [improve-system](improve-system/SKILL.md) — B.U.I.L.D. Loop — the improvement engine.
- [weekly-enhancement-loop](weekly-enhancement-loop/SKILL.md) — Weekly cross-repo self-improvement loop. Every Monday 02:00 AEST it applies the 8-Claude-Loops method (INGEST / BUILD / COMPOUND + North Star) across every repo in .harness/projects.

## Meta / Authoring
- [skill-watch](skill-watch/SKILL.md) — Daily 06:17 check of outside skills/tools (pinned SHA or npm version), context budget via `claude plugin details`, and unreviewed Claude Code releases; optional bounded model review. Registry: `external-skills.json`. Built 17/09/2026.
- [skill-authoring-standard](skill-authoring-standard/SKILL.md) — Design or review any skill to the Library standard — frontmatter, structure, steering, and pruning.
- [nexus](nexus/SKILL.md) — Master-orchestrator command. Type /nexus <goal> to have the estate's best minds work a goal end-to-end — frame it…
- [meta-curator](meta-curator/SKILL.md) — Skill self-authoring agent. Reads .harness/lessons.jsonl (weekly) and merged-PR diffs (daily), proposes new SKILL.md…
- [agentskills-manifest](agentskills-manifest/SKILL.md) — Export Pi-CEO's skill registry as an agentskills.io-format manifest.
- [big-three](big-three/SKILL.md) — The foundational framework - Model, Prompt, Context.
- [closed-loop-prompt](closed-loop-prompt/SKILL.md) — Self-correcting prompts with embedded verification.

## Self-healing chain (order: prove-the-failure → contain → diagnose → classify → propose-fix → adversarial-review → verify → immunise → incident-memory)
- [prove-the-failure](prove-the-failure/SKILL.md) — Build a tight, red-capable feedback loop that drives the actual failure path and asserts the exact symptom, before any hypothesis is formed.
- [contain](contain/SKILL.md) — Reach a safe state before diagnosing.
- [diagnose](diagnose/SKILL.md) — Find root cause by running the red loop from `prove-the-failure` and changing one variable at a time — never by reading the code and reasoning about it.
- [classify](classify/SKILL.md) — The gate in the self-healing chain.
- [propose-fix](propose-fix/SKILL.md) — Produce the repair as a diff plus a regression test, never applied directly.
- [adversarial-review](adversarial-review/SKILL.md) — Review a proposed fix with a different model in a fresh session that has no access to the builder's reasoning.
- [verify](verify/SKILL.md) — Run the loop from `prove-the-failure` and confirm red goes green, then hold a cooldown before any further action is permitted.
- [immunise](immunise/SKILL.md) — Add the check, test, or workflow guard that stops this failure recurring.
- [incident-memory](incident-memory/SKILL.md) — Write symptom, cause, fix, reviewer verdict and outcome to a searchable store — successes and failures alike.

## Quarantined (NOT in catalog per lifecycle rules)
- `deprecated/`: aura, codex-adversarial, council-of-logic, empire-ignite, nexus-session-handoff-legacy, pr-merge-ci-gate, release-path, semrush, video-orchestrator
- `in-progress/`: agent-shopping-safe-checkout, pantheon-forge-build, water-category-classifier
