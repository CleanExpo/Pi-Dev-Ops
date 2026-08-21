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

# Preflight every destination before changing any of them. A protected real
# directory in one host root must not leave earlier roots partially updated.
for target_root in "${TARGET_ROOTS[@]}"; do
  for skill in "${SKILLS[@]}"; do
    target_path="$target_root/$skill"
    if [[ -e "$target_path" && ! -L "$target_path" ]]; then
      echo "ERROR: refusing to replace real path: $target_path" >&2
      exit 3
    fi
  done
done

for target_root in "${TARGET_ROOTS[@]}"; do
  [[ $DRY_RUN -eq 1 ]] || mkdir -p "$target_root"
  for skill in "${SKILLS[@]}"; do
    source_path="$SOURCE_ROOT/$skill"
    target_path="$target_root/$skill"
    if [[ -L "$target_path" ]]; then
      if [[ "$(readlink "$target_path")" == "$source_path" ]]; then
        echo "CURRENT $target_path"
      else
        echo "UPDATE  $target_path -> $source_path"
        [[ $DRY_RUN -eq 1 ]] || ln -sfn "$source_path" "$target_path"
      fi
    else
      echo "LINK    $target_path -> $source_path"
      [[ $DRY_RUN -eq 1 ]] || ln -s "$source_path" "$target_path"
    fi
  done
done

echo "Senior Harness control stack is aligned across Codex, Claude, and Agents skill discovery."
