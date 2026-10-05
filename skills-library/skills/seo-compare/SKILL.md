---
name: seo-compare
description: Head-to-head SEO comparison of two domains powered by the DataForSEO API. Side-by-side metrics across keywords, traffic, backlinks, referring domains, and shared keyword overlap with a verdict on which domain has the stronger SEO position.
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

# SEO Domain Comparison Skill

> **Powered by:** [DataForSEO API](https://dataforseo.com) — Labs `domain_rank_overview` + Backlinks `summary` + Labs `domain_intersection` (×2 for both domains).
> **Cost:** ~$0.05 per comparison.

## Run (parallel)

```bash
~/.claude/skills/seo/scripts/domain_overview.py overview --target <d1>
~/.claude/skills/seo/scripts/domain_overview.py overview --target <d2>
~/.claude/skills/seo/scripts/backlinks.py summary --target <d1>
~/.claude/skills/seo/scripts/backlinks.py summary --target <d2>
~/.claude/skills/seo/scripts/domain_overview.py intersect --you <d1> --competitor <d2> --limit 100
```

## Output: side-by-side table

```
                          | <d1>          | <d2>          | Winner
--------------------------|---------------|---------------|-------
Estimated organic traffic | 12,400/mo     | 8,900/mo      | <d1>
Total ranking keywords    | 3,420         | 5,180         | <d2>
Top-10 keywords           | 412           | 287           | <d1>
Backlinks                 | 14,200        | 8,900         | <d1>
Referring domains         | 612           | 891           | <d2>
Dofollow ratio            | 71%           | 58%           | <d1>
Domain rank               | 421           | 502           | <d2>
```

## SERP overlap section

From the intersect call:

```
Shared keywords: <N>
- Where <d1> wins: <X> keywords
- Where <d2> wins: <Y> keywords
- Top 5 keywords where <d1> outranks <d2>: ...
- Top 5 keywords where <d2> outranks <d1>: ...
```

## Verdict

3-4 sentence summary covering:
1. Which domain is stronger overall
2. Where the weaker one is winning anyway (their leverage points)
3. The single biggest gap the weaker domain should close
4. The single biggest threat to the stronger domain
