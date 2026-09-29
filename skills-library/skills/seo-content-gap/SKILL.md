---
name: seo-content-gap
description: Find keywords competitors rank for that you don't, via the DataForSEO Labs domain_intersection endpoint. Surfaces the highest-leverage content opportunities sorted by search volume and the competitor's ranking position, with cross-competitor consensus signals.
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

# Content Gap Skill

> **Powered by:** [DataForSEO API](https://dataforseo.com) — Labs `domain_intersection` (target1=competitor, target2=you, intersections=false).
> **Cost:** ~$0.02 per competitor compared.

## Run

```bash
~/.claude/skills/seo/scripts/domain_overview.py content_gap --you <you> --competitors <c1> <c2> <c3>
```

You can pass 1–5 competitors. The script returns, per competitor, the
keywords where they rank in the top 100 and you don't.

## Sort and surface

For each competitor's gap list, sort by:

```
priority = search_volume * (101 - competitor_position)
```

Higher = the competitor is ranking high for a high-volume keyword you have
nothing for — hot opportunity.

## Output structure

For each competitor:

```
Gap vs <competitor>: <N> keywords where they rank, you don't

Top 10 to pursue:
1. "<keyword>" — they're #<pos>, vol <V>, KD <D>, $<CPC>
   → They rank a <page_type> at <url>
2. ...
```

## Cross-competitor consensus

After processing all competitors, find keywords that **multiple competitors**
rank for. These are the strongest signals — if every competitor has content
on a topic and you don't, that's a clear hole in your strategy.

```
Consensus gaps (3+ competitors rank, you don't):
- "<keyword>"   ← 4 competitors rank top 20
- "<keyword>"   ← 3 competitors rank top 10
```

End with a 5-article content roadmap with target keyword, working title,
priority score, and which competitor's article to study.
