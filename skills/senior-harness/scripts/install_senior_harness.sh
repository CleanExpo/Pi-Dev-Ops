#!/usr/bin/env bash
# Install one canonical Senior Harness control stack for all supported skill roots.
#
# The lifecycle hooks in .claude/settings.json and .codex/hooks.json execute the
# $HOME-installed copy of setup_driver.py, not the checkout. Without this install
# step those commands resolve to nothing and the harness never runs.
set -euo pipefail

DRY_RUN=0
ENTRY_ONLY=0
while (($#)); do
  case "$1" in
    --dry-run|-n) DRY_RUN=1 ;;
    --entry-only) ENTRY_ONLY=1 ;;
    --help|-h)
      echo "Usage: install_senior_harness.sh [--dry-run] [--entry-only]"
      exit 0
      ;;
    *) echo "ERROR: unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done

# cd -P resolves symlinked path components, so running the installed copy at
# $HOME/.claude/skills/senior-harness/scripts still finds the real checkout.
SCRIPT_DIR="$(cd -P "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -P "$SCRIPT_DIR/../../.." && pwd)"
SOURCE_ROOT="$REPO_ROOT/skills"
SKILLS=(senior-harness model-router unlazy)
TARGET_ROOTS=("$HOME/.codex/skills" "$HOME/.claude/skills" "$HOME/.agents/skills")
ENTRY_SOURCE="$REPO_ROOT/scripts/pi-ceo-harness"
ENTRY_TARGET="$HOME/.local/bin/pi-ceo-harness"

for skill in "${SKILLS[@]}"; do
  [[ -f "$SOURCE_ROOT/$skill/SKILL.md" ]] || {
    echo "ERROR: required source skill is missing: $SOURCE_ROOT/$skill" >&2
    exit 2
  }
done
[[ -x "$ENTRY_SOURCE" ]] || {
  echo "ERROR: required entry launcher is missing or not executable: $ENTRY_SOURCE" >&2
  exit 2
}

if [[ $ENTRY_ONLY -eq 1 ]]; then
  if [[ ! -L "$ENTRY_TARGET" && -e "$ENTRY_TARGET" ]]; then
    echo "ERROR: refusing to replace real path: $ENTRY_TARGET" >&2
    exit 3
  fi
  if [[ $DRY_RUN -eq 1 ]]; then
    echo "ENTRY_ONLY $ENTRY_TARGET -> $ENTRY_SOURCE"
    exit 0
  fi
  mkdir -p -- "$(dirname "$ENTRY_TARGET")"
  ln -sfn -- "$ENTRY_SOURCE" "$ENTRY_TARGET"
  echo "Senior Harness entry launcher installed: $ENTRY_TARGET"
  exit 0
fi

# Preflight every destination before changing any of them. A protected real
# directory in the last slot must leave the earlier ones untouched too.
for target_root in "${TARGET_ROOTS[@]}"; do
  for skill in "${SKILLS[@]}"; do
    target_path="$target_root/$skill"
    if [[ ! -L "$target_path" && -e "$target_path" ]]; then
      echo "ERROR: refusing to replace real path: $target_path" >&2
      exit 3
    fi
  done
done
if [[ ! -L "$ENTRY_TARGET" && -e "$ENTRY_TARGET" ]]; then
  echo "ERROR: refusing to replace real path: $ENTRY_TARGET" >&2
  exit 3
fi

# The real install is a small transaction. Every prior symlink is recorded and
# rolled back if a later mkdir/link fails, so a failure in the last root cannot
# leave the earlier roots pointing at a different control stack.
changed_paths=()
previous_targets=()
previous_states=()
created_roots=()
committed=0
rollback() {
  local status=$?
  [[ "$committed" == 1 || "$DRY_RUN" == 1 ]] && return "$status"
  trap - ERR INT TERM
  local index target previous state
  for ((index=${#changed_paths[@]}-1; index>=0; index--)); do
    target="${changed_paths[index]}"
    previous="${previous_targets[index]}"
    state="${previous_states[index]}"
    if [[ "$state" == missing ]]; then
      rm -f -- "$target"
    else
      ln -sfn -- "$previous" "$target"
    fi
  done
  for ((index=${#created_roots[@]}-1; index>=0; index--)); do
    rmdir -- "${created_roots[index]}" 2>/dev/null || true
  done
  echo "ERROR: install failed; previous skill links were restored" >&2
  return "$status"
}
trap rollback ERR INT TERM

if [[ $DRY_RUN -eq 0 ]]; then
  for target_root in "${TARGET_ROOTS[@]}"; do
    if [[ ! -d "$target_root" ]]; then
      mkdir -p -- "$target_root"
      created_roots+=("$target_root")
    fi
  done
  if [[ ! -d "$(dirname "$ENTRY_TARGET")" ]]; then
    mkdir -p -- "$(dirname "$ENTRY_TARGET")"
    created_roots+=("$(dirname "$ENTRY_TARGET")")
  fi
fi

for target_root in "${TARGET_ROOTS[@]}"; do
  for skill in "${SKILLS[@]}"; do
    source_path="$SOURCE_ROOT/$skill"
    target_path="$target_root/$skill"
    if [[ -L "$target_path" ]]; then
      if [[ "$(readlink "$target_path")" == "$source_path" ]]; then
        echo "CURRENT $target_path"
      else
        echo "UPDATE  $target_path -> $source_path"
        if [[ $DRY_RUN -eq 0 ]]; then
          changed_paths+=("$target_path")
          previous_targets+=("$(readlink "$target_path")")
          previous_states+=(present)
          ln -sfn -- "$source_path" "$target_path"
        fi
      fi
    else
      echo "LINK    $target_path -> $source_path"
      if [[ $DRY_RUN -eq 0 ]]; then
        changed_paths+=("$target_path")
        previous_targets+=("")
        previous_states+=(missing)
        ln -s -- "$source_path" "$target_path"
      fi
    fi
  done
done

if [[ -L "$ENTRY_TARGET" ]]; then
  if [[ "$(readlink "$ENTRY_TARGET")" == "$ENTRY_SOURCE" ]]; then
    echo "CURRENT $ENTRY_TARGET"
  else
    echo "UPDATE  $ENTRY_TARGET -> $ENTRY_SOURCE"
    if [[ $DRY_RUN -eq 0 ]]; then
      changed_paths+=("$ENTRY_TARGET")
      previous_targets+=("$(readlink "$ENTRY_TARGET")")
      previous_states+=(present)
      ln -sfn -- "$ENTRY_SOURCE" "$ENTRY_TARGET"
    fi
  fi
else
  echo "LINK    $ENTRY_TARGET -> $ENTRY_SOURCE"
  if [[ $DRY_RUN -eq 0 ]]; then
    changed_paths+=("$ENTRY_TARGET")
    previous_targets+=("")
    previous_states+=(missing)
    ln -s -- "$ENTRY_SOURCE" "$ENTRY_TARGET"
  fi
fi

committed=1
trap - ERR INT TERM
echo "Senior Harness control stack is aligned across Codex, Claude, and Agents skill discovery."
