---
name: seo-report-pdf
description: Generate a professional, client-ready PDF SEO report from a saved DataForSEO-powered audit. Produces a polished PDF with score gauges, prioritized action plan, keyword opportunity tables, and competitive landscape — ready to send to a client.
allowed-tools:
  - Bash
  - Read
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

# SEO PDF Report Skill

> **Powered by:** Reads the audit JSON produced by `/seo audit`, built from live [DataForSEO API](https://dataforseo.com) data. PDF generation uses ReportLab — no additional API calls.

## Prerequisite

`/seo audit <domain>` must have run first and saved
`~/.claude/skills/seo/output/<domain>-audit.json`. If that file doesn't
exist, tell the user to run the audit first.

## Run

```bash
~/.claude/skills/seo/scripts/generate_pdf_report.py \
    --input ~/.claude/skills/seo/output/<domain>-audit.json \
    --output ~/.claude/skills/seo/output/<domain>-report.pdf
```

When the PDF is generated, print the absolute path and (on macOS) offer to
open it:

```bash
open ~/.claude/skills/seo/output/<domain>-report.pdf
```

## What's in the PDF

The generator (`scripts/generate_pdf_report.py`) reads the audit JSON and
produces:

- Cover with composite Overall / Keywords / Technical / Authority score cards
- Executive Summary
- Key Metrics block
- Prioritized Action Plan table (color-coded by priority)
- Top Keyword Opportunities table (with volume, CPC, difficulty, position)
- Competitive Landscape table

All sections gracefully skip if their data is missing from the audit JSON,
so partial audits still render a valid PDF.

## Customization

To change colors/fonts/branding for a client deliverable, edit the constants
at the top of [scripts/generate_pdf_report.py](../../seo/scripts/generate_pdf_report.py):

```python
BRAND_PRIMARY = colors.HexColor("#1f4e79")
BRAND_ACCENT  = colors.HexColor("#2e8b57")
```
