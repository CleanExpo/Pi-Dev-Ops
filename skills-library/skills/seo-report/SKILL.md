---
name: seo-report
description: Generate a markdown SEO report deliverable from a saved DataForSEO-powered audit. Produces a client-ready markdown document with executive summary, scores, key findings, prioritized actions, and supporting data tables — ready to send to a client.
allowed-tools:
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

# SEO Markdown Report Skill

> **Powered by:** Reads the audit JSON produced by `/seo audit`, which is built from live [DataForSEO API](https://dataforseo.com) data. No additional API calls — pure formatting step.

Reads `~/.claude/skills/seo/output/<domain>-audit.json` and produces a
markdown report at `~/.claude/skills/seo/output/<domain>-report.md`.

## Structure

```markdown
# SEO Audit Report — <domain>
*Generated <date>*

## Executive Summary
<3-5 sentences from audit.executive_summary>

## Composite Score: <overall>/100

| Dimension | Score |
|-----------|-------|
| Keywords | <N>/100 |
| Technical | <N>/100 |
| Competitors | <N>/100 |
| Content | <N>/100 |
| Authority | <N>/100 |

## Key Metrics
<key_metrics as a 2-column table>

## Top 3 Actions This Week
1. **<action>** — <why it matters> (impact: high)
2. **<action>** — ...
3. **<action>** — ...

## Prioritized Issue List
<issues table — Priority | Issue | Recommendation>

## Top Keyword Opportunities
<top_keywords table>

## Competitive Landscape
<competitors table>

## Methodology
This report was generated using the dataforseo-claude skill pack, which
combines Claude Code's analysis with live data from DataForSEO's APIs.
All metrics reflect Google's organic search results in <location> at the
time of audit.

---
*Powered by DataForSEO + Claude Code*
```

## Tone

- Direct and confident — clients are paying for clarity
- Numbers, not adjectives — say "12,400 monthly visits" not "significant traffic"
- Recommendations are specific actions, not categories
  - ✅ "Rewrite the title tag on /pricing to lead with 'Pricing — [Brand]'"
  - ❌ "Improve title tags"
