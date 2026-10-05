---
name: seo-content
description: Content topical authority and gap analysis powered by the DataForSEO Labs API. Clusters a domain's ranked keywords into topics, identifies strong vs weak vs missing topic clusters versus competitors, and returns a Content Score (0-100) plus the highest-leverage content opportunities to write next.
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

# SEO Content Authority Skill

> **Powered by:** [DataForSEO API](https://dataforseo.com) — Labs `ranked_keywords` + Labs `competitors_domain` + Labs `domain_intersection`.
> **Cost:** ~$0.05 per run.

## Run

Pull what the target ranks for, plus the top competitor's ranked keywords:

```bash
~/.claude/skills/seo/scripts/domain_overview.py ranked --target <domain> --limit 200
~/.claude/skills/seo/scripts/domain_overview.py competitors --target <domain> --limit 5
~/.claude/skills/seo/scripts/domain_overview.py content_gap --you <domain> --competitors <c1> <c2> <c3>
```

## Topic clustering

Group keywords into topical clusters using common stems / shared head terms.
Don't be too granular — aim for 8-15 clusters max for a typical site.

Example clusters for an SEO tool site:
- "keyword research" (head: keyword)
- "rank tracking" (head: rank, ranking)
- "backlinks" (head: backlink, link building)
- "site audit" (head: audit, technical)
- ...

## For each cluster, classify it

| Status | Definition |
|--------|------------|
| **Strong** | 5+ keywords ranking top 10, total est. traffic > 100/mo |
| **Building** | Some keywords top 30, none top 10 yet |
| **Weak** | Keywords ranking but all below position 30 |
| **Missing** | Competitors rank, you don't (from content_gap) |

## Content Score (0-100)

```
content_score = round(
    50 * (strong_clusters / total_clusters) +
    25 * (1 - missing_clusters / total_clusters) +
    25 * (avg_position_top_quartile_score)
)
```

## Highest-leverage content moves

Surface the **top 5 specific articles to write next**. Pick from the
"Missing" and "Building" clusters, prioritizing keywords with:
- Search volume > 200/mo
- Difficulty < competitor's domain rank
- Commercial or transactional intent

For each, suggest: working title, target keyword, related keywords to include,
estimated word count.

## Return JSON shape

```json
{
  "content_score": 64,
  "strong_topics": [{"cluster": "...", "keywords": 12, "avg_position": 5.2}],
  "weak_topics": [{"cluster": "...", "keywords": 18, "avg_position": 42.1}],
  "missing_topics": [{"cluster": "...", "competitor": "...", "keyword_count": 24}],
  "content_recommendations": [
    {"title": "...", "target_keyword": "...", "volume": 880, "difficulty": 22, "intent": "commercial"}
  ]
}
```
