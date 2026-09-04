# BEWG site

Next.js 16 static site for Building Environmental Wellness Group (bewg.au), built on the
estate design system.

## Why this exists

The live bewg.au is a single page. `bewg.au/services` and `bewg.au/contact` return the same
content as the homepage — verified 2026-09-03 by fetching all three. That leaves one indexable
page for a firm offering eight distinct investigation types, so somebody searching
"interstitial condensation assessment" or "moisture mapping multi storey" has nothing to land on.

Every benchmark firm Ivi supplied — Element Forensic Engineering, PCT Building Science, Sarveli
Consulting Engineers, Makao — is structured around individually addressable service pages. This
build does the same, and adds an assessment finder none of them have.

## Design system

Colour is **not** defined in this project. It comes from
`packages/brand-config/src/brands/bewg.ts`, specified in `bewg.design.md`, and is emitted as
shadcn-convention CSS variables by `themeFactory`. `app/brand-tokens.css` is generated from
that source and committed; it must never be hand-edited.

```bash
node scripts/gen-tokens.mjs           # regenerate after a brand change
node scripts/gen-tokens.mjs --check   # fails if the committed file has drifted
```

Two rules from the brand spec are load-bearing and easy to break by accident:

- **Blue is the building, amber is the finding.** Amber marks a recommendation, an anomaly or
  the single primary action on a screen. It is never a background wash or a decorative rule.
  Amber also fails contrast as text on light surfaces — use `--accent-ink` for that.
- **Every measured value is set in mono.** Readings, sample IDs, standards codes, timestamps and
  phone numbers go through `<Reading>`. Prose never does. A reader can then tell at a glance
  which parts of a page are measured and which are argued.

## What is here

- **Eight service pages** (`/services/[slug]`) — the signs pointing to each investigation, the
  method, the deliverables and the standards applied. Content from Ivi's brief of 12 and 17 August.
- **The assessment finder** (`/assessment-finder`) — six questions scored against the service
  set. Recommends an investigation, flags urgency, and generates a written job brief the visitor
  can email or keep.
- Home, how-we-work, contact, sitemap and robots.

The finder is the commercial point of the build. An enquiry that arrives as a structured brief —
symptoms, location, building type, onset pattern, purpose, contact — can be quoted without a
round of questions first.

## Editing content

All copy lives in `content/`. No page markup is hand-edited for a content change.

- `content/site.json` — name, phone, email, coverage
- `content/services.json` — one object per service; adding one adds a page, a nav entry, cards on
  the home and services pages, and a sitemap entry
- `content/triage.json` — the finder's questions and how each answer weights each service

### Adding a service

Add an object with all of `slug`, `title`, `nav`, `short`, `headline`, `intro`, `signs`,
`method`, `deliverables`, `standards`, `related`. Then add at least one triage answer that
weights the new slug — `assertContentValid()` **fails the build** if a service exists that no
answer routes to, because that is a page nobody would ever be sent to. It also fails on a dead
`related` link, a self-reference, a bad slug or an empty required list.

## Commands

```bash
npm run dev         # dev server on :4173
npm run build       # static export to out/
npm run typecheck   # tsc --noEmit
npm run test        # browser smoke test against out/ (needs a built export)
```

The smoke test covers 24 checks: validation, three routing scenarios end to end, the brief and
mailto contents, brand tokens resolving to the real brand colour, every route rendering with one
`h1`, sitemap coverage, mobile overflow, console errors and missing assets. Set `CHROMIUM_PATH`
if chromium sits outside playwright's cache.

## Deploying

`vercel.json` targets a Vercel project rooted at `sites/bewg` — `npm run build`, output `out`.
The export has no server-side work and makes no network calls at runtime.

The finder sends its brief through the visitor's own mail client (`mailto:`). Nothing is posted
to a server and no visitor data is stored, so there is no backend and no personal information
held anywhere. Routing enquiries into a CRM or shared inbox needs a form endpoint adding — a
deliberate next increment, not an oversight.

## Claims to verify with Ivi before this goes live

The copy stays on defensible ground — method and standards rather than credentials — but these
are assertions about a real firm's capability and must be confirmed:

- NATA-accredited laboratory analysis (carried over from the current bewg.au)
- The equipment behind pressurisation testing, thermal imaging and WUFI hygrothermal modelling
- Australia-wide attendance, and any state-based licensing that applies
- **Whether BEWG performs remediation.** The how-we-work page states it does not, and that
  independence is the site's strongest positioning. If it is wrong, that page and the home page
  both need rewriting before publication.

## Known gap

The four reference sites Ivi sent are blocked by this environment's network policy (403 on
CONNECT), so the design was built from their text content and from the brand spec, not from
seeing them. Visual comparison against those references is still outstanding.
