---
name: seo-backlinks
description: Backlink profile audit via the DataForSEO Backlinks API. Returns total backlinks, referring domains, dofollow ratio, top anchors with over-optimization flags, top referring domains by authority, and a toxicity assessment with an Authority Score (0-100).
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

# Backlink Audit Skill

> **Powered by:** [DataForSEO API](https://dataforseo.com) — Backlinks `summary` + `referring_domains` + `anchors` + `domain_intersection`.
> **Cost:** ~$0.03-0.05 per run.

## Run

Three calls, parallel:

```bash
~/.claude/skills/seo/scripts/backlinks.py summary --target <domain>
~/.claude/skills/seo/scripts/backlinks.py refdomains --target <domain> --limit 100
~/.claude/skills/seo/scripts/backlinks.py anchors --target <domain> --limit 50
```

## What to evaluate

### Volume & freshness
- Total backlinks, total referring domains
- New backlinks in last 30/90 days
- Lost backlinks in last 30/90 days
- Trend: growing, stable, declining

### Quality
- Dofollow ratio (50-80% is healthy; >95% looks artificial)
- Domain rank distribution of referring sites
  (mostly low-rank domains = weak profile)
- TLD distribution (.edu / .gov / .org weight more)
- IP / subnet diversity (PBN red flag if all same C-class)

### Anchor text
- Top 10 anchors by frequency
- Branded anchor share — should be 40-60% for a healthy profile
  - <30% looks unnatural
  - >80% means few topical links
- Exact-match anchor share — should be < 10%
  - >20% = over-optimization, manual penalty risk

### Toxicity flags
- High share of links from low-rank domains (rank < 50)
- Sudden spike in backlinks (possible negative SEO)
- Anchor text patterns suggesting paid links
- Adult / gambling / pharma TLDs in referring domains

## Authority Score (0-100)

| Signal | Weight |
|--------|--------|
| log10(referring_domains) scaled to 0-30 | 30% |
| Domain rank percentile | 25% |
| Anchor naturalness (penalty for >20% exact-match) | 15% |
| Dofollow ratio in healthy band (50-80%) | 10% |
| TLD/IP diversity | 10% |
| Toxicity penalty (negative) | up to -10% |

## Return JSON shape

```json
{
  "authority_score": 68,
  "backlink_summary": {
    "backlinks": 12345, "referring_domains": 432,
    "dofollow_pct": 67, "broken_backlinks": 12,
    "new_30d": 18, "lost_30d": 5
  },
  "top_referrers": [{"domain": "...", "rank": 612, "backlinks": 24, "dofollow": true}],
  "anchor_distribution": {
    "branded": 0.51, "exact_match": 0.08, "partial_match": 0.18,
    "naked_url": 0.12, "generic": 0.11
  },
  "toxicity_flags": ["..."]
}
```
