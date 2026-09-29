#!/usr/bin/env bash
# Preflight credential check for every dataforseo-claude skill.
#
# Exit code 0  : credentials look configured. Skill should proceed.
# Exit code 2  : credentials missing or still placeholders. Skill must
#                show the setup wizard (printed to stdout) and wait for
#                the user to paste creds.
#
# Skills invoke this with:
#     ~/.claude/skills/seo/scripts/preflight.sh
# and check the exit code.

set -u

ENV_FILE="${HOME}/.claude/skills/seo/.env"

# Helper: emit the wizard to stdout, exit 2.
emit_wizard() {
  cat <<'WIZARD'
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

I'll save them securely to ~/.claude/skills/seo/.env (chmod 600) and
run your original command immediately after.
WIZARD
  exit 2
}

# Case 1: file doesn't exist
if [ ! -f "$ENV_FILE" ]; then
  emit_wizard
fi

# Case 2: read values
LOGIN=$(grep -E '^DATAFORSEO_LOGIN=' "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'" | xargs)
PASSWORD=$(grep -E '^DATAFORSEO_PASSWORD=' "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'" | xargs)

# Case 3: empty
if [ -z "$LOGIN" ] || [ -z "$PASSWORD" ]; then
  emit_wizard
fi

# Case 4: placeholders left over from .env.example
if [ "$LOGIN" = "your_login_email_here" ] || [ "$PASSWORD" = "your_api_password_here" ]; then
  emit_wizard
fi

# All good. Skill can proceed.
exit 0
