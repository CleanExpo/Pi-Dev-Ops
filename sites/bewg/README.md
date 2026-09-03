# BEWG site

A content-driven static site for Building Environmental Wellness Group (bewg.au).

## Why this exists

The live bewg.au is a single page. `bewg.au/services` and `bewg.au/contact` return the same
content as the homepage — verified 2026-09-03. That means there is one indexable page for a
firm offering eight distinct investigation types, and someone searching for "interstitial
condensation assessment" or "moisture mapping multi storey" has nothing to land on.

Every benchmark firm Ivi sent through (Element Forensic Engineering, PCT Building Science,
Sarveli Consulting Engineers, Makao) structures around individually addressable service pages.
This build does the same, and adds an assessment finder none of them have.

## What is here

- **Eight service pages**, each with the signs that point to it, the method, the deliverables
  and the standards applied. Drawn from Ivi's brief of 12 and 17 August.
- **An assessment finder** (`/assessment-finder`) — six questions that score the visitor's
  symptoms against the service set, recommend the right investigation, flag urgency, and
  generate a written job brief they can email or keep.
- Home, about and contact pages, sitemap and robots.

The assessment finder is the commercial point of the build. An enquiry that arrives as a
structured brief — symptoms, location, building type, onset pattern, purpose, contact —
can be quoted without a round of questions first.

## Editing content

All copy lives in `content/`. No HTML is hand-edited.

- `content/site.json` — name, phone, email, coverage
- `content/services.json` — one object per service; adding a service adds a page,
  a nav entry, a card on the home and services pages, and a sitemap entry
- `content/triage.json` — the finder's questions and how each answer weights each service

Then rebuild: `npm run build`.

### Adding a service

Add an object to `content/services.json` with all of: `slug`, `title`, `nav`, `short`,
`headline`, `intro`, `signs`, `method`, `deliverables`, `standards`, `related`. Then add at
least one triage answer that weights the new slug — the build **fails** if a service exists
that no answer routes to, because that is a page nobody would ever be sent to.

## Commands

```bash
npm run check    # validate content, no build — fast, no dependencies
npm run build    # write dist/
npm run serve    # build and serve locally on :4173
npm run test     # build then run the browser smoke test (needs playwright)
```

`build.mjs` refuses to build on a dead `related` link, an empty required field, a triage
answer pointing at a service that does not exist, or an unreachable service.

## Deploying

`vercel.json` is set up for a Vercel project rooted at `sites/bewg`: build command
`node build.mjs`, output `dist`, clean URLs, cache headers on assets and a
content-security policy. The build has no runtime dependencies and no network calls.

The finder sends its brief through the visitor's own email client (`mailto:`). Nothing is
posted to a server and no visitor data is stored, so there is no backend to run and no
personal information held anywhere. If enquiries should instead land in a CRM or inbox
automatically, that needs a form endpoint adding — a deliberate next step, not an oversight.

## Claims to verify before going live

The copy stays on defensible ground — method and standards rather than credentials — but
these should be confirmed with Ivi before the site is published:

- NATA-accredited laboratory analysis (taken from the current bewg.au)
- The equipment and capability behind pressurisation testing, thermal imaging and WUFI
  hygrothermal modelling
- Australia-wide attendance, and any state-based licensing that applies
- Whether BEWG carries out remediation. The About page states it does not, which is what
  makes the independence claim work. If that is wrong it must be changed.
