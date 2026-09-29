---
name: seo-competitors
description: Identify true SEO competitors and quantify the gap, powered by the DataForSEO Labs API. Returns the top 10 competing domains by SERP overlap, with shared and unique keywords, traffic estimates, and a Competitive Score (0-100) showing how dominant the target is in its category.
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

# SEO Competitor Analysis Skill

> **Powered by:** [DataForSEO API](https://dataforseo.com) — Labs `competitors_domain` + Labs `domain_intersection`.
> **Cost:** ~$0.05-0.08 per run.

## Run

```bash
~/.claude/skills/seo/scripts/domain_overview.py competitors --target <domain> --limit 20
```

For each of the top 5 competitors, also pull intersection (shared keywords):

```bash
~/.claude/skills/seo/scripts/domain_overview.py intersect --you <domain> --competitor <competitor>
```

## What to surface

### Top 10 competitors table

| Rank | Domain | Common keywords | Their unique keywords | Est. traffic | Domain rank |
|------|--------|----------------|-----------------------|--------------|-------------|

The DataForSEO competitors endpoint already ranks them by SERP overlap with
your target — keep that order.

### SERP overlap analysis

For the top 3 competitors:
- How many keywords does the target share with them? (intersect call)
- What's the average position gap? (you at #15, them at #4 = -11 gap)
- Any keywords where the target outranks the competitor? (rare wins to defend)

### Strategic groupings

- **Direct competitors** — share 30%+ of keywords
- **Adjacent competitors** — share 10-30% (worth monitoring, not chasing)
- **Aspirational** — much higher domain rank, shared keywords < 10% (long-term)

## Competitive Score (0-100)

How dominant is the target in its competitive set?

```
competitive_score = 100 * (target_traffic / max(sum_of_top_10_traffic, 1))
```

Capped at 100. Above 30 = strong, 10-30 = mid-tier, <10 = challenger.

## Return JSON shape

```json
{
  "competitive_score": 24,
  "competitors": [
    {"domain": "...", "common_keywords": 1234, "unique_keywords": 5678, "traffic": 99999, "rank": 421},
    ...
  ],
  "serp_overlap": {
    "<competitor>": {"shared": 234, "avg_gap": -8.4, "wins": 12}
  },
  "strategic_groups": {
    "direct": ["a.com", "b.com"],
    "adjacent": ["c.com"],
    "aspirational": ["d.com"]
  }
}
```
