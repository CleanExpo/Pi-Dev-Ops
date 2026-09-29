---
name: seo-keywords
description: Keyword research and opportunity scoring via the DataForSEO Keywords Data and Labs APIs. Returns search volume, CPC, competition, intent classification, related keywords, and long-tail suggestions with a Keyword Score (0-100).
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

# SEO Keyword Research Skill

> **Powered by:** [DataForSEO API](https://dataforseo.com) — Keywords Data `google_ads/search_volume` + Labs `related_keywords` + Labs `keyword_suggestions` + Labs `bulk_keyword_difficulty`.
> **Cost:** ~$0.05-0.10 per keyword run.

## Inputs

- A seed keyword OR a domain (call it `<seed>`)
- Optional: `--location` (default United States), `--language` (default en)

## Run

For a **seed keyword**:

```bash
~/.claude/skills/seo/scripts/keyword_research.py related "<seed>" --limit 200
~/.claude/skills/seo/scripts/keyword_research.py suggestions "<seed>" --limit 100
```

For a **domain** (find the keywords it already ranks for):

```bash
~/.claude/skills/seo/scripts/domain_overview.py ranked --target <domain> --limit 200
```

## Analysis

### Group by search intent

Classify each keyword into one of:
- **Informational** — "how to", "what is", "guide", "tutorial"
- **Commercial** — "best", "review", "comparison", "vs"
- **Transactional** — "buy", "price", "deal", "near me", brand+product
- **Navigational** — brand names, specific URLs

### Opportunity score per keyword

```
opportunity = search_volume / (keyword_difficulty + 10)
```

Higher = better. Surface the **top 20** sorted by opportunity.

### Keyword Score (0-100)

| Signal | Weight |
|--------|--------|
| Avg. search volume of top 50 keywords (log-scaled) | 30% |
| Share of low-difficulty keywords (KD < 30) in top 50 | 25% |
| Intent diversity (4 buckets present) | 15% |
| CPC value (high CPC = commercial intent) | 15% |
| Long-tail breadth (count of suggestions) | 15% |

Output: a Keyword Score with a one-sentence justification.

## Return JSON shape (when called from `/seo audit`)

```json
{
  "keyword_score": 78,
  "top_opportunities": [
    {"keyword": "...", "search_volume": 1000, "cpc": 2.5, "difficulty": 25, "intent": "commercial", "opportunity": 28.5},
    ...
  ],
  "intent_breakdown": {"informational": 45, "commercial": 32, "transactional": 18, "navigational": 5}
}
```
