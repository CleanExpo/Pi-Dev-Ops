---
name: seo-quick
description: 60-second SEO snapshot powered by the DataForSEO API. Three parallel calls (DataForSEO Labs domain overview, Backlinks summary, ranked keywords) for core metrics on any domain — total keywords, traffic estimate, backlinks, top rankings — without waiting for a full audit.
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

# SEO Quick Snapshot

> **Powered by:** [DataForSEO API](https://dataforseo.com) — Labs `domain_rank_overview` + Backlinks `summary` + Labs `ranked_keywords`.
> **Cost:** ~$0.01-0.03 per run.

Three parallel API calls, then a tight summary.

## Run

```bash
~/.claude/skills/seo/scripts/domain_overview.py overview --target <domain>
~/.claude/skills/seo/scripts/backlinks.py summary --target <domain>
~/.claude/skills/seo/scripts/domain_overview.py ranked --target <domain> --limit 25
```

## Output Format

```
🟢/🟡/🔴 SEO Snapshot: <domain>

• Estimated organic traffic: <N>/mo
• Total ranking keywords: <N>  (top 3: <X>, top 10: <Y>)
• Backlinks: <N> from <N> referring domains  (dofollow: <X>%)
• Domain rank: <N>/1000

Top 5 keywords by traffic value:
1. <keyword> — pos <N>, vol <V>, $<CPC>
...

Headline finding: <one sentence — biggest opportunity OR biggest weakness>
```

No subagents. No PDF. ≤30 seconds end to end.
