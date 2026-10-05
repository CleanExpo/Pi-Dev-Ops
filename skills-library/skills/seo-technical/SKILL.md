---
name: seo-technical
description: Technical SEO site audit via the DataForSEO On-Page API. Crawls the site (up to 100 pages by default), surfaces critical errors (broken links, redirect chains, missing meta, slow pages, schema gaps, indexability issues), and returns a Technical Score (0-100) with prioritized fixes.
allowed-tools:
  - Bash
  - Write
---

## Phase 0: Credential Preflight (REQUIRED — run BEFORE anything else)

Before running any of the steps below, **always** invoke the shared preflight check:

```bash
~/.claude/skills/seo/scripts/preflight.sh
```

**If exit code is 0:** credentials are configured — proceed with the rest of this skill silently.

**If exit code is 2:** the script prints the DataForSEO setup wizard to stdout. STOP, display that wizard to the user verbatim, and **wait for them to paste credentials** in this format:

```
login: their_email@example.com
password: their_api_password_here
```

When they reply:

1. Parse `login:` and `password:` from their message.
2. Write them to `~/.claude/skills/seo/.env`:
   ```
   DATAFORSEO_LOGIN=<login>
   DATAFORSEO_PASSWORD=<password>
   ```
3. `chmod 600 ~/.claude/skills/seo/.env`
4. Run a verification call: `~/.claude/skills/seo/scripts/keyword_research.py volume "test"`
5. If verification succeeds (real JSON returned): tell the user "✅ Credentials verified. Running your command now..." and proceed with the original request.
6. If status `40104 — Please verify your account`: tell the user to verify their account at https://app.dataforseo.com/, then say "continue" to retry.
7. If any other auth error: ask them to double-check the API password (the long alphanumeric string from https://app.dataforseo.com/api-access — not their account login password).

**Never** echo credentials back to the user, never include them in tool output, and never commit them.

---

# Technical SEO Audit Skill

> **Powered by:** [DataForSEO API](https://dataforseo.com) — On-Page `instant_pages` (single URL) and On-Page `task_post` + `summary` + `pages` (full crawl).
> **Cost:** ~$0.05-0.10 per 100-page crawl. Crawl takes 2-5 minutes.

## Run

For a single page (instant):

```bash
~/.claude/skills/seo/scripts/on_page_audit.py page --url <url>
```

For a full site crawl (2-5 min for 100 pages):

```bash
~/.claude/skills/seo/scripts/on_page_audit.py site --target <domain> --max-crawl-pages 100
```

## Categories to evaluate

Pull from the `summary.checks` and per-page `checks` objects:

### Indexability & Crawl
- `is_4xx_code`, `is_5xx_code`, `is_redirect` chains > 2 hops
- `canonical` mismatches
- `robots_txt`, blocked resources
- `is_https`, mixed content

### On-page meta
- Missing/duplicate `<title>`, `<meta description>`
- Title length (should be 50-60 chars), description (140-160)
- `h1` missing or duplicate
- Heading hierarchy gaps

### Speed & Core Web Vitals
- `time_to_interactive`, `largest_contentful_paint`
- `cumulative_layout_shift`
- Resource errors

### Content quality
- `plain_text_word_count` < 300 = thin content
- `plain_text_rate` (text vs. HTML)
- `automated_readability_index`

### Structured data
- Schema present? Which types?
- Missing organization / article / breadcrumb / product schema for the site type

## Issue priority rubric

| Priority | Examples |
|----------|----------|
| **Critical** | 5xx errors, no-index on key pages, broken canonical, mixed content, robots.txt blocking |
| **High** | Missing titles/descriptions on indexable pages, broken internal links, redirect chains, slow LCP (>4s) |
| **Medium** | Duplicate titles/descriptions, missing alt text at scale, thin content (<300 words) on key pages |
| **Low** | Heading hierarchy gaps, suboptimal title length, missing schema |

## Technical Score (0-100)

Start at 100. Subtract:
- 15 per critical issue (max 60)
- 5 per high issue (max 30)
- 1 per medium issue (max 15)
- 0.2 per low issue (max 5)

Floor at 0.

## Return JSON shape

```json
{
  "technical_score": 72,
  "crawl_summary": {"pages_crawled": 100, "errors": 8, "warnings": 23},
  "critical_issues": [{"title": "...", "count": 3, "recommendation": "..."}],
  "high_issues": [...],
  "medium_issues": [...]
}
```
