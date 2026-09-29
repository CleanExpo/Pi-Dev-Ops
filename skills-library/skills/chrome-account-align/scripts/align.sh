#!/bin/zsh
# claude-chrome-align — open the machine's pinned Chrome profile on claude.ai so the
# Claude-in-Chrome extension registers under the SAME account as the Claude Code CLI.
# Mapping lives in ~/.claude/chrome-align.json: {"profileDir": "Profile 1"}
# First run without a mapping: enumerates profiles and exits with instructions.
set -euo pipefail

CLI_EMAIL=$(python3 -c "import json;print(json.load(open('$HOME/.claude.json')).get('oauthAccount',{}).get('emailAddress',''))")
[ -n "$CLI_EMAIL" ] || { echo "FAIL: no oauthAccount in ~/.claude.json — run 'claude' and sign in first"; exit 1; }

MAP="$HOME/.claude/chrome-align.json"
CHROME_DIR="$HOME/Library/Application Support/Google/Chrome"

if [ ! -f "$MAP" ]; then
  echo "No mapping yet. CLI account: $CLI_EMAIL"
  echo "Chrome profiles on this machine:"
  for d in "$CHROME_DIR"/Default "$CHROME_DIR"/Profile*; do
    [ -f "$d/Preferences" ] || continue
    python3 - "$d" <<'EOF'
import json, sys, os
d = sys.argv[1]
p = json.load(open(os.path.join(d, 'Preferences')))
name = p.get('profile', {}).get('name', '?')
ai = p.get('account_info', [])
email = ai[0].get('email', 'no-google-account') if ai else 'no-google-account'
print(f"  {os.path.basename(d)} | {name} | {email}")
EOF
  done
  echo "Pin one: printf '{\"profileDir\": \"Profile 1\"}' > $MAP"
  exit 2
fi

PROFILE=$(python3 -c "import json;print(json.load(open('$MAP')).get('profileDir',''))")
[ -n "$PROFILE" ] || { echo "FAIL: $MAP has no profileDir"; exit 1; }
PNAME=$(python3 -c "import json;print(json.load(open('$CHROME_DIR/$PROFILE/Preferences')).get('profile',{}).get('name','?'))" 2>/dev/null || echo '?')

echo "CLI account:    $CLI_EMAIL"
echo "Pinned profile: $PROFILE ($PNAME)"
open -na "Google Chrome" --args --profile-directory="$PROFILE" "https://claude.ai/chrome"
echo "Opened claude.ai/chrome in the pinned profile."
echo "CONTRACT: that profile's claude.ai login must be $CLI_EMAIL — if the page shows"
echo "another account, switch it there once; the pin makes it stick from then on."
