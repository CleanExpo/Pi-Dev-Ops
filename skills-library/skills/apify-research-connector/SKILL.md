---
name: apify-research-connector
description: Use when a project needs Apify-powered web, social, SERP, marketplace, or competitor research with credential, compliance, and dataset controls.
---

# Apify Research Connector

Use Apify as a credential-gated data adapter for research, not as a bypass for
platform rules. Keep credentials in ignored env stores and keep outputs
provenance-rich.

## Context Gate

Operate only from the current project folder. Read local docs, `.env.example`,
package scripts, existing Apify modules, and Brain-1 wiki pages. If project
identity or credential ownership is unclear, stop with a blocked report.

## Credential Gate

Check presence without printing values:

```bash
git check-ignore -v .env.local .env 2>/dev/null || true
awk -F= '/^APIFY_(API_TOKEN|API_KEY)=/{print $1"=present"}' .env.local 2>/dev/null || true
vercel env ls --scope unite-group 2>/dev/null | awk '/APIFY|apify/{print $1, $2, $3, $4, $5}'
```

Preferred variable is `APIFY_API_TOKEN`. Treat `APIFY_API_KEY` as legacy or
project-specific until verified. Never echo, log, screenshot, commit, or paste
token values.

## Official Docs Gate

Refresh current Apify docs before adding or changing integration behavior:

- API overview: `https://docs.apify.com/api`
- Run Actor and retrieve data:
  `https://docs.apify.com/academy/api/run-actor-and-retrieve-data-via-api`
- JavaScript client: `https://docs.apify.com/api/client/js`
- Dataset API: `https://docs.apify.com/api/v2/default-dataset`
- Apify API page: `https://apify.com/api`

## Operating Pattern

1. Define the research question, platform, and business use.
2. Select `mode`: `official_actor`, `custom_actor`, `licensed_vendor`,
   `manual_review`, or `blocked`.
3. Check actor page/docs, input schema, pricing, usage limits, and terms.
4. Prefer existing project service modules and scripts before adding code.
5. Run the smallest verification that proves auth and actor compatibility.
6. For short runs, use Apify client `.call()` or sync endpoints; for longer
   runs, use async run plus polling or webhooks.
7. Store structured outputs in datasets; use key-value stores for single files,
   images, PDFs, or `OUTPUT`.
8. Capture provenance: actor ID, input, run ID, dataset ID, access date,
   source URLs, platform terms checked, and limitations.
9. Feed findings into wiki/content/SEO/YouTube skills with clear source labels.

## Safety Rules

- No CAPTCHA bypass, logged-in scraping, paywall bypass, forbidden platform
  scraping, personal-data enrichment, or terms evasion.
- Do not use Apify to scrape Google Search directly when Search Console,
  official APIs, licensed vendors, or manual review are the correct route.
- Use official platform APIs when a platform requires them.
- Treat Store actors as adapters with their own docs and commercial terms.
- Emit a blocked JSON/report when credentials, rights, consent, rate limits, or
  actor schemas are missing.

## Verification

Low-cost auth check:

```bash
node -e "const fs=require('fs'); const key='APIFY_'+'API_TOKEN'; const s=fs.readFileSync('.env.local','utf8'); const m=s.match(new RegExp('^'+key+'=(.*)$','m')); process.exit(m?0:2)"
```

Live API identity check without printing token:

```bash
TOKEN=$(node -e "const fs=require('fs'); const key='APIFY_'+'API_TOKEN'; const s=fs.readFileSync('.env.local','utf8'); const m=s.match(new RegExp('^'+key+'=(.*)$','m')); if(!m) process.exit(2); let v=m[1].trim().replace(/^['\\\"]|['\\\"]$/g,''); process.stdout.write(v)")
curl -fsS -H "Authorization: Bearer $TOKEN" https://api.apify.com/v2/users/me \
  | jq '{username: .data.username, idPresent: (.data.id != null)}'
```

Do not run paid actors until the expected cost and approval gate are explicit.

## Output Contract

Return:

- project and credential status, masked
- Synthex/Vercel env coverage when relevant
- mode and actor/task selected
- docs and terms checked
- run/dataset IDs, if created
- output location
- compliance blockers
- wiki/catalog updates
