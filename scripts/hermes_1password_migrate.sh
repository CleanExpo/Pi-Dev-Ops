#!/usr/bin/env bash
# RA-1912 phase 2 — hermes_1password_migrate.sh
#
# Migrates secrets from ~/.hermes/.env into a 1Password vault, then rewrites
# .env so each line uses an `op://` reference instead of a plaintext value.
#
# Hermes' env loader in `~/.hermes/hermes-agent` runs `op inject` on startup
# (or you wrap it via a launcher) so the running daemon never sees plaintext
# unless the OS keychain has unlocked 1Password for the user.
#
# Idempotent:
#   - skips items that already exist in the vault (verifies value matches)
#   - safe to re-run after rotating any single key
#
# Pre-flight:
#   1. `op` CLI installed (Homebrew: `brew install --cask 1password-cli`)
#   2. Signed in: `eval $(op signin)` — biometric / passphrase prompt
#   3. Vault exists: `op vault create hermes` (or use an existing vault name)
#
# Usage:
#   bash hermes_1password_migrate.sh [--dry-run] [--vault VAULT_NAME]
#
# Default vault: "hermes". Override with --vault.

set -euo pipefail

VAULT="hermes"
DRY_RUN=0
ENV_FILE="${HOME}/.hermes/.env"
BACKUP_FILE="${ENV_FILE}.pre-1password-$(date +%Y%m%d-%H%M%S)"

while [ $# -gt 0 ]; do
    case "$1" in
        --dry-run) DRY_RUN=1; shift;;
        --vault) VAULT="$2"; shift 2;;
        --help|-h)
            sed -n '2,/^$/p' "$0" | sed 's/^# *//'
            exit 0;;
        *) echo "unknown arg: $1"; exit 2;;
    esac
done

# Pre-flight checks
command -v op >/dev/null 2>&1 || { echo "ERROR op CLI not installed. brew install --cask 1password-cli"; exit 3; }

if ! op vault get "$VAULT" >/dev/null 2>&1; then
    echo "ERROR vault '$VAULT' not found or not signed in to 1Password."
    echo "  Sign in:        eval \$(op signin)"
    echo "  Create vault:   op vault create $VAULT"
    echo "  List vaults:    op vault list"
    exit 4
fi

[ -f "$ENV_FILE" ] || { echo "ERROR $ENV_FILE not found"; exit 5; }

# Read every KEY=value (skip comments, blanks)
declare -a NEW_LINES
NEW_LINES=()
SECRETS_MIGRATED=0
SECRETS_SKIPPED=0

while IFS= read -r line || [ -n "$line" ]; do
    # Pass through comments + blanks unchanged
    if [[ -z "${line// }" || "$line" =~ ^[[:space:]]*# ]]; then
        NEW_LINES+=("$line")
        continue
    fi

    # Match KEY=value
    if [[ ! "$line" =~ ^([A-Z_][A-Z0-9_]*)=(.*)$ ]]; then
        # Unrecognised — pass through verbatim
        NEW_LINES+=("$line")
        continue
    fi

    KEY="${BASH_REMATCH[1]}"
    VALUE="${BASH_REMATCH[2]}"

    # If the line is already an op:// reference, skip
    if [[ "$VALUE" =~ ^op:// ]]; then
        echo "  [skip] $KEY already references 1Password — leaving as-is"
        NEW_LINES+=("$line")
        SECRETS_SKIPPED=$((SECRETS_SKIPPED + 1))
        continue
    fi

    # Strip surrounding quotes if any
    VALUE="${VALUE#\"}"
    VALUE="${VALUE%\"}"
    VALUE="${VALUE#\'}"
    VALUE="${VALUE%\'}"

    if [ "$DRY_RUN" -eq 1 ]; then
        echo "  [dry] would store $KEY in vault $VAULT (${#VALUE} chars)"
        NEW_LINES+=("${KEY}=op://${VAULT}/${KEY}/credential")
        continue
    fi

    # Idempotent: if item exists, check value matches
    if op item get "$KEY" --vault "$VAULT" >/dev/null 2>&1; then
        existing="$(op item get "$KEY" --vault "$VAULT" --field credential --reveal 2>/dev/null || echo '')"
        if [ "$existing" = "$VALUE" ]; then
            echo "  [ok]   $KEY exists in vault, value matches"
        else
            echo "  [warn] $KEY exists in vault but value differs — NOT overwriting"
            echo "         to update: op item edit $KEY credential='<new-value>' --vault $VAULT"
        fi
    else
        # Create as API Credential
        op item create \
            --vault "$VAULT" \
            --category "API Credential" \
            --title "$KEY" \
            "credential[password]=$VALUE" \
            --tags "hermes,RA-1912" >/dev/null
        echo "  [new]  $KEY → op://${VAULT}/${KEY}/credential"
        SECRETS_MIGRATED=$((SECRETS_MIGRATED + 1))
    fi

    # Replace the line in the new env with the op:// reference
    NEW_LINES+=("${KEY}=op://${VAULT}/${KEY}/credential")
done < "$ENV_FILE"

if [ "$DRY_RUN" -eq 1 ]; then
    echo ""
    echo "DRY RUN — no changes made. Re-run without --dry-run to apply."
    echo "Would migrate $SECRETS_MIGRATED secrets, skip $SECRETS_SKIPPED already-referenced."
    exit 0
fi

# Write backup of original .env
cp "$ENV_FILE" "$BACKUP_FILE"
chmod 600 "$BACKUP_FILE"

# Atomically replace .env with op:// references
TMP_FILE="$(mktemp)"
printf '%s\n' "${NEW_LINES[@]}" > "$TMP_FILE"
chmod 600 "$TMP_FILE"
mv "$TMP_FILE" "$ENV_FILE"

echo ""
echo "✓ Migrated $SECRETS_MIGRATED secrets to 1Password vault: $VAULT"
echo "✓ Skipped $SECRETS_SKIPPED already-referenced lines"
echo "✓ Original .env backed up to $BACKUP_FILE"
echo "✓ New .env uses op:// references"
echo ""
echo "Next step: ensure Hermes resolves op:// at startup."
echo "  Recommended: launch Hermes via a wrapper that runs"
echo "    op inject -i ~/.hermes/.env -o ~/.hermes/.env.resolved"
echo "  before sourcing the resolved file. Or call 'op run -- hermes ...'."
echo ""
echo "Quick verify:"
echo "  op read 'op://${VAULT}/OPENROUTER_API_KEY/credential' | head -c 20 && echo"
