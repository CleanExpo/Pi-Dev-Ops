#!/usr/bin/env bash
# Install one canonical Senior Harness control stack for all supported skill roots.
set -euo pipefail

DRY_RUN=0
if [[ "${1:-}" == "--dry-run" || "${1:-}" == "-n" ]]; then
  DRY_RUN=1
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_ROOT="$REPO_ROOT/skills"
SKILLS=(senior-harness model-router unlazy)
TARGET_ROOTS=("$HOME/.codex/skills" "$HOME/.claude/skills" "$HOME/.agents/skills")

for skill in "${SKILLS[@]}"; do
  [[ -f "$SOURCE_ROOT/$skill/SKILL.md" ]] || {
    echo "ERROR: required source skill is missing: $SOURCE_ROOT/$skill" >&2
    exit 2
  }
done

# Preflight every destination before changing any of them. A protected real
# directory in the ninth slot must leave the first eight untouched too.
for target_root in "${TARGET_ROOTS[@]}"; do
  for skill in "${SKILLS[@]}"; do
    target_path="$target_root/$skill"
    if [[ ! -L "$target_path" && -e "$target_path" ]]; then
      echo "ERROR: refusing to replace real path: $target_path" >&2
      exit 3
    fi
  done
done

# The real install is a small transaction. We record every prior symlink and
# roll it back if a later mkdir/link fails, so a ninth-root failure cannot leave
# the first eight roots on a different control stack.
changed_paths=()
previous_targets=()
created_roots=()
committed=0
rollback() {
  local status=$?
  [[ "$committed" == 1 || "$DRY_RUN" == 1 ]] && return "$status"
  trap - ERR INT TERM
  local index target previous
  for ((index=${#changed_paths[@]}-1; index>=0; index--)); do
    target="${changed_paths[index]}"
    previous="${previous_targets[index]}"
    if [[ "$previous" == __MISSING__ ]]; then
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
          ln -sfn -- "$source_path" "$target_path"
        fi
      fi
    else
      echo "LINK    $target_path -> $source_path"
      if [[ $DRY_RUN -eq 0 ]]; then
        changed_paths+=("$target_path")
        previous_targets+=(__MISSING__)
        ln -s -- "$source_path" "$target_path"
      fi
    fi
  done
done

committed=1
trap - ERR INT TERM
echo "Senior Harness control stack is aligned across Codex, Claude, and Agents skill discovery."
