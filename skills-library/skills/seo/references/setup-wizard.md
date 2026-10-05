# First-Run Setup Wizard (Phase 0)

Every `/seo ...` request starts with a credentials check — API calls fail without
credentials, so there is nothing useful to run until it passes. `SKILL.md` holds the
quick check; this file holds the full wizard for when credentials are missing.

## Step 1 — Read the credentials file

```bash
cat ~/.claude/skills/seo/.env 2>/dev/null
```

## Step 2 — Decide if credentials are configured

The `.env` is **NOT configured** if any of these are true:
- The file doesn't exist
- `DATAFORSEO_LOGIN` is missing or contains the literal string `your_login_email_here`
- `DATAFORSEO_PASSWORD` is missing or contains the literal string `your_api_password_here`

**Step 3a — If credentials ARE configured:** continue to the requested command, no message needed.

**Step 3b — If credentials are NOT configured:** STOP. Do not run the requested command.
Instead, paste exactly this setup wizard to the user:

```
🔧 DataForSEO API Setup Required

This skill needs DataForSEO API credentials to fetch real Google SEO data.
One-time setup, takes 60 seconds:

  Step 1 — Sign up free (includes $1 trial credit, ~10 full audits):
           https://l.dataforseo.com/4epETnH

  Step 2 — After verifying your email, open API Access:
           https://app.dataforseo.com/api-access

  Step 3 — Copy your API Login (your email) and API Password
           (the long alphanumeric string under "API password")

  Step 4 — Paste both back to me in this exact format:

           login: your_email@example.com
           password: your_api_password

I'll save them securely to ~/.claude/skills/seo/.env (chmod 600) and run
your original command immediately after.
```

Then **WAIT** for the user's reply with credentials.

## Step 4 — When the user pastes credentials

1. Parse `login:` and `password:` from their message (handle `Login:`, `Password:`,
   email-only, or just two lines as well — be lenient)
2. Write them to `~/.claude/skills/seo/.env` using this format:

```
DATAFORSEO_LOGIN=<their_login>
DATAFORSEO_PASSWORD=<their_password>
```

3. Lock down permissions:

```bash
chmod 600 ~/.claude/skills/seo/.env
```

4. Run a verification call (cheap — ~$0.001):

```bash
~/.claude/skills/seo/scripts/keyword_research.py volume "test" 2>&1
```

5. Interpret the result:

| Result | Tell the user |
|--------|---------------|
| Real JSON with search volume | ✅ `Credentials verified. Running your audit now...` then run the original command |
| Status `40104 — Please verify your account` | ⚠️ `Credentials work but DataForSEO needs you to verify your account first. Visit https://app.dataforseo.com/ and complete verification (usually email click + payment method on file). Then say "continue" and I'll retry.` |
| HTTP 401 or 403 (not 40104) | 🔴 `Those credentials didn't work. Common fix: make sure you copied the API password (long alphanumeric string from https://app.dataforseo.com/api-access), not your account login password.` |
| Anything else | Show the raw error, suggest the user paste it back so we can debug |

**Important:** Never echo the credentials back to the user, never include them
in any tool output, and never commit them to git.
