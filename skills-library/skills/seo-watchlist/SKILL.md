---
name: seo-watchlist
description: Track multiple domains and keywords across runs using the DataForSEO SERP API. Saves a local watchlist of domains + their target keywords, then re-runs live rank checks on demand and surfaces any position changes (gains, losses, drops) since the last check.
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

# SEO Watchlist Skill

> **Powered by:** [DataForSEO API](https://dataforseo.com) — SERP `google/organic/live/advanced` for live rank checks across the saved keyword set.
> **Cost:** ~$0.002 per keyword per check.

A simple file-based watchlist at `~/.claude/skills/seo/output/watchlist.json`.

## Schema

```json
{
  "domains": {
    "example.com": {
      "label": "Main site",
      "keywords": ["seo audit tool", "keyword research", "..."],
      "history": [
        {"date": "2026-04-15", "rankings": [{"keyword": "...", "position": 8}, ...]},
        {"date": "2026-04-22", "rankings": [{"keyword": "...", "position": 6}, ...]}
      ]
    }
  }
}
```

## Subcommands

### `add <domain> <keywords...>`

Read the existing watchlist (if any), add or update the domain entry, write back.
Run an immediate rank check and store as the first history entry.

### `list`

Print the watchlist in a human-readable table:
- Domain | label | # keywords | last checked | last avg position

### `check <domain>` or `check all`

Re-run SERP rank check on the saved keywords:

```bash
~/.claude/skills/seo/scripts/serp_check.py rank --domain <domain> --keywords <kw...>
```

Append the result to history, then **diff against the previous check**:

```
Movement since <last_date>:
🟢 Up:    "seo audit tool"     8 → 5  (+3)
🔴 Down:  "ai content tool"   12 → 18 (-6)
⚪ Same:  "..." 3 → 3
```

### `remove <domain>` and `remove <domain> <keyword>`

Drop a domain or a single keyword from the watchlist.

## Output

Always end with a short take: any concerning drops (-5 or worse), any
opportunities (rankings just outside top 10), and one suggested action.
