---
name: geo-optimization
description: Generative Engine Optimization (GEO) standard for AI search visibility — the 2026 successor to SEO. Use when adding or auditing GEO infrastructure (llms.txt, JSON-LD schema, WebMCP, Lighthouse Agentic) on any portfolio site or via the Synthex client-audit module.
version: 1.0.0
source: Manus AI "Comprehensive SEO/GEO Research Report" — May 2026
applies_to:
  - all portfolio websites (10 repos)
  - Synthex client-audit module (forthcoming Phase 3)
---

# GEO Optimization Standard (2026)

> Generative Engine Optimization is the successor to SEO. AI Overviews appear on 60%+ of US queries; CTR drops up to 65% where they appear. Optimizing for AI agents, not just humans, is the new baseline.

## Why this skill exists

Every portfolio site needs the same GEO foundations so AI agents (Google AI Overviews, ChatGPT citations, Perplexity, Gemini, autonomous browsing agents) can extract, cite, and transact with the site. The same standard powers the Synthex client-audit module's gap analysis + remediation.

Without this skill, each repo reinvents the implementation and drifts from the standard. With it, the standard is single-source-of-truth.

## When to invoke

**Always invoke when:**

- Adding a new public page to any portfolio site → check it has Tier-1 schema, FAQ block, front-loaded answer
- Auditing a site's GEO readiness → run the checklist in §7
- Building or extending Synthex's client-audit module → §6 is the spec
- Reviewing a PR that touches a public-facing route, contact/intake form, or product page

**Skip when:** purely internal admin tooling, build scripts, infrastructure that's not user-facing.

## §1 — Foundational ranking factors (2026)

| Factor | AI-citation correlation | Implication |
|---|---|---|
| Brand mentions across the web | **0.664** | Off-page brand presence > backlinks. Earn web mentions via PR, press, original research, partnerships. |
| Backlinks | 0.218 | Still matter for top-10 ranking, but weaker direct GEO signal. |
| Top-10 organic ranking | **92%** of AI Overview citations | Traditional SEO is the floor — must rank top-10 to be cited. |
| Featured snippet structure | **62%** overlap with AI Overview sources | Structure that wins snippets transfers directly. |
| Content extractability (≈800-token chunks) | High | Direct answer immediately after H2 = cited. Walls of text = ignored. |
| First-third placement of answers | **55%** of citations | "Ski ramp" — citations drop sharply past first 30% of doc. Front-load. |
| FAQ blocks as self-contained answer units | **44% citation lift** | Structured FAQ → high-leverage citation surface. |

## §2 — Content structure rules

**Always:**

1. Direct, declarative answer in the **first 150–200 words** of any informational page.
2. H2-based section structure — AI extracts in ≈800-token chunks around H2 boundaries.
3. FAQ block on every meaningful page. Answers ≤50 words, plain language, schema-marked as `FAQPage`.
4. Original media (photos, diagrams, screenshots) — pure AI-generated header images are a May 2026 Core Update penalty signal.
5. Demonstrate Information Gain — what does this page add that doesn't exist elsewhere? If the answer is "nothing", the May 2026 update demotes it.

**Never:**

- Dense, repetitive AI-generated text (May 2026 Core Update penalty).
- Broad topic sprawl on a single domain without demonstrated expertise (penalty).
- Keyword stuffing or academic-dense paragraphs (AI prefers plain declarative).
- Manufacturer copy on product pages — needs unique insight, original photos, expert review.

## §3 — Structured data (JSON-LD)

**Hard rules:**

1. **Server-side rendered.** AI crawlers do not execute JavaScript. JSON-LD must be in the initial HTML response.
2. **Visible counterpart required.** Hidden schema with no on-page equivalent is ignored.
3. **Complete Tier-1 schema or no Tier-1 schema.** Half-implemented Product schema (missing GTIN/MPN/price) often does more harm than none.

**Tier-1 (essential — implement on every relevant page):**

| Type | When | Required fields |
|---|---|---|
| `Product` | Every product page | `name`, `description`, `brand`, `GTIN` or `MPN`, `price`, `availability` |
| `AggregateRating` | Every Product page with reviews; LocalBusiness root | `ratingValue`, `reviewCount`. 3x lift in AI shopping citations. |
| `Organization` | Site root (layout) | `name`, `url`, `logo`, `sameAs` (LinkedIn, Wikidata, Crunchbase) |
| `LocalBusiness` | Every local-service site | `address`, `geo`, `openingHours`, `telephone`, `priceRange` |

**Tier-2 (high leverage):**

| Type | When |
|---|---|
| `FAQPage` | Every page with an FAQ block (every page should have one) |
| `Service` | Every service-detail page |
| `Article` + `Person` (author) | Every blog post — `datePublished`, `author`, `hasCredential` |
| `BreadcrumbList` | Every page deeper than root |

**Tier-3 (situational):**

- `Event` — events, webinars, launches
- `Course` — training pages (CARSI)
- `JobPosting` — careers pages
- `HowTo` — step-by-step guides
- `VideoObject` — embedded video content

## §4 — llms.txt standard

Place at site root (`/llms.txt`). Markdown-formatted, machine-readable. Pattern:

```markdown
# {Site Name}

> One-line value proposition aimed at an AI agent deciding whether to cite or interact with this site.

## Business Identity
- Legal Name, ABN, Website, Coverage area

## What We Do
2–3 paragraphs. Direct, declarative, no marketing fluff.

## Services / Products
- Bullet list with short descriptions

## Agent Capabilities (WebMCP)
- POST /api/contact — submit contact enquiry (form: name, email, message)
- POST /api/claim/intake — submit a restoration claim (form: address, damage_type, urgency)
- GET /api/availability/{postcode} — check service availability

## Trust Signals
- Certifications, awards, member-of bodies

## Policies
- Privacy: /privacy
- Terms: /terms
- Contact: /contact
```

**Implementation per stack:**

- **Next.js (App Router):** Static `public/llms.txt` is simplest. For dynamic content, `app/llms.txt/route.ts` returning `text/plain`.
- **Express/NodeJS:** Dynamic `app.get('/llms.txt', ...)` returning `text/plain` with `generateLlmsTextFromDatabase()`.
- **Shopify:** No native root-level `.txt` support. Two options:
  1. App-based: SEO app intercepts root requests and serves dynamically (preferred).
  2. Liquid workaround: create `templates/page.llms.liquid`, page named `llms`, redirect `/llms.txt` → `/pages/llms` via URL redirect. Less reliable — AI agents probe `/llms.txt` exactly.
- **Static sites:** Drop the file in build output. Cloudflare Workers can intercept if SSG limits prevent it.

## §5 — WebMCP (Web Model Context Protocol)

Lets autonomous AI agents in-browser execute actions on the site. Proposed W3C standard. Two flavours:

**Declarative (annotate existing HTML forms):**

```html
<form toolname="submit_claim_intake"
      tooldescription="Submit a disaster recovery claim for distribution to vetted contractors">
  <input name="postcode"
         toolparamdescription="Australian postcode (4-digit) of the damaged property">
  <select name="damage_type"
          toolparamdescription="Type of damage: water, fire, mould, storm, biohazard">
    <option value="water">Water damage</option>
    <option value="fire">Fire damage</option>
    <!-- ... -->
  </select>
  <input name="urgency"
         toolparamdescription="emergency (within 24h), urgent (within 72h), or scheduled">
</form>
```

**Imperative (JS-registered tools):**

```js
navigator.modelContext.registerTool({
  name: 'check_postcode_coverage',
  description: 'Check if Disaster Recovery services this postcode and get expected response time',
  parameters: { postcode: { type: 'string', pattern: '^\\d{4}$' } },
  handler: async ({ postcode }) => fetch(`/api/coverage/${postcode}`).then(r => r.json())
})
```

**Where to add:**

- Every public form (contact, intake, signup, booking) → declarative annotation
- Every API endpoint that does useful work without auth → imperative registration

## §6 — Lighthouse Agentic Browsing audit (CI gate)

Chrome Lighthouse 13.3+ adds an "Agentic Browsing" category. Four audits:

1. **Accessibility tree well-formedness** — semantic HTML + correct ARIA. Agents use the a11y tree as their data model.
2. **WebMCP integration** — declarative form annotations OR imperative JS tools detected.
3. **`llms.txt` present** — valid `/llms.txt` at root with `# H1` and adequate length.
4. **Layout stability (CLS)** — agents click faster than humans; layout shifts mid-interaction break flows.

**CI integration pattern:**

```yaml
# .github/workflows/lighthouse-agentic.yml
on: [pull_request, push: {branches: [main]}]
jobs:
  agentic-audit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: treosh/lighthouse-ci-action@v12
        with:
          urls: |
            ${{ vars.PREVIEW_URL }}/
            ${{ vars.PREVIEW_URL }}/contact
            ${{ vars.PREVIEW_URL }}/services
          configPath: ./.lighthouserc.json
          uploadArtifacts: true
```

`.lighthouserc.json`:

```json
{
  "ci": {
    "collect": {
      "settings": { "preset": "desktop", "onlyCategories": ["agentic-browsing", "accessibility", "seo"] }
    },
    "assert": {
      "assertions": {
        "categories:agentic-browsing": ["error", { "minScore": 0.75 }],
        "categories:accessibility": ["warn", { "minScore": 0.90 }]
      }
    }
  }
}
```

## §7 — Audit checklist (use for every site)

Run this checklist when auditing a site or before opening a "GEO migration" PR.

- [ ] `/llms.txt` at root, ≥40 lines, includes `# H1` + Business Identity + Services + WebMCP capability list
- [ ] Organization schema in site root layout (server-rendered JSON-LD, includes `sameAs`)
- [ ] AggregateRating on every Product / LocalBusiness (3x AI-citation lift)
- [ ] FAQPage schema on every page with an FAQ block (every page should have one)
- [ ] Every public form has WebMCP `toolname` + `tooldescription` annotations
- [ ] At least one imperative WebMCP tool registered via `navigator.modelContext`
- [ ] First 200 words of every informational page contains the direct answer to the page's primary question
- [ ] Lighthouse Agentic Browsing audit ≥ 0.75 (CI gate)
- [ ] No raw AI-generated header images without original media supplement
- [ ] All product copy unique (no manufacturer boilerplate)

## §8 — Local SEO post-May-2026 update

The May 2026 Core Update demoted directory/aggregator sites by up to 75% for "near me" queries. Provider sites that demonstrate Information Gain rose to fill the gap.

**Local-business requirements (every local service site in portfolio):**

- Google Business Profile fully optimised — rich media, accurate hours, consistent NAP, active review generation
- Site must demonstrate provider-specific expertise that a directory cannot replicate: detailed case studies, team bios, service methodology, certifications
- LocalBusiness schema with `geo`, `areaServed`, `openingHoursSpecification`
- Service-specific landing pages per geographic area (avoid thin templated location pages — each must add unique local context)

**Bottom-of-funnel stability:** Transactional intent pages ("emergency roof repair Austin") survived the update with minimal volatility. Top-of-funnel informational content is now AI-Overview territory — to win clicks there, you must be the cited source.

## §9 — Implementation playbook (per stack)

### Next.js (App Router) sites

Most of the portfolio. The pattern:

1. **llms.txt** → `public/llms.txt` (static) or `app/llms.txt/route.ts` (dynamic).
2. **Org / Site schema** → JSON-LD `<script>` in `app/layout.tsx` head.
3. **Page-level schema** → JSON-LD in each `app/*/page.tsx` (server component).
4. **FAQ blocks** → reusable `<FAQ>` server component that emits both visible Q&A AND FAQPage JSON-LD.
5. **WebMCP** → annotate form components; one global `WebMCPRegistrar` client component for imperative tools.
6. **Lighthouse Agentic** → `.github/workflows/lighthouse-agentic.yml` against Vercel preview URL.

### Express / NodeJS sites

1. **llms.txt** → dynamic route returning `text/plain`.
2. **Schema** → server-side template (Pug/EJS/Handlebars) renders JSON-LD.
3. Rest of pattern: same.

### Shopify clients (Synthex audit module target)

1. **llms.txt** → SEO app or Cloudflare Worker (Liquid workaround is brittle).
2. **Product schema** → use Shopify's built-in JSON-LD + extend with AggregateRating from a reviews app (Yotpo, Loox, Judge.me).
3. **FAQPage** → Liquid section embedded on PDPs with both visible + JSON-LD output.
4. **WebMCP** → annotate the cart + product form Liquid templates.

## §10 — Synthex client-audit module spec (Phase 3 target)

When this skill is invoked from Synthex's audit module:

- Input: client site URL + Shopify/NodeJS/Static/Wordpress detection
- Output: per-section pass/fail against §7 checklist, with severity (critical/high/medium) and a remediation snippet per failure
- Generates an "GEO Migration Plan" PR for client repos when authorised, OR a copy-paste implementation pack for non-repo clients
- Auto-detects May 2026 Core Update penalty risk patterns (scaled AI content, raw manufacturer copy, missing Information Gain markers)

## References (May 2026 source report)

1. Onely — "How to Rank in Google AI Overviews"
2. CXL — "Where Google AI Overviews pull their answers from"
3. Nudge — "7 Schema Markup Types That Get Products Cited by AI"
4. Google Search Central — "Optimizing your website for generative AI features"
5. Chrome Developers — "Agentic Browsing and WebMCP Documentation"
6. Stackmatix — "Structured Data AI Search: Schema Markup Guide (2026)"
7. web.dev — "Build agent-friendly websites"
8. Internal — "Google May 2026 Core Update Rollout and Impact"
9. Internal — "May Core Update Chaos and Local SEO Shakeup"

## Related skills

- `seo-baseline` (legacy) — superseded by this skill for AI-search work
- `accessibility-audit` — accessibility tree well-formedness overlaps with §6 audit 1
- `synthex-client-audit` (forthcoming) — will invoke this skill's §7 checklist as its core engine
