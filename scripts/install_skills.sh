#!/usr/bin/env bash
# install_skills.sh — make Pi-Dev-Ops the single source of truth for skills on any machine.
#
# Symlinks every Pi-Dev-Ops/skills/<name> into ~/.claude/skills/<name> (the established
# pattern used by the marketing-* and remotion-* families). Idempotent and non-destructive:
# a real (non-symlink) directory already in ~/.claude/skills is never clobbered — it is
# reported and skipped so machine-local skills survive.
#
# Cross-machine flow ("pull the skills from Pi"):
#   git -C ~/Pi-CEO/Pi-Dev-Ops pull
#   bash ~/Pi-CEO/Pi-Dev-Ops/scripts/install_skills.sh           # apply
#   bash ~/Pi-CEO/Pi-Dev-Ops/scripts/install_skills.sh --dry-run # preview only
#
# Authoring standard for every skill it installs: skills/skill-authoring-standard/SKILL.md.
set -euo pipefail

DRY_RUN=0
[[ "${1:-}" == "--dry-run" || "${1:-}" == "-n" ]] && DRY_RUN=1

REPO_SKILLS="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/skills"
TARGET="${CLAUDE_SKILLS_DIR:-$HOME/.claude/skills}"

[[ -d "$REPO_SKILLS" ]] || { echo "ERROR: skills dir not found at $REPO_SKILLS" >&2; exit 1; }
mkdir -p "$TARGET"

linked=0 updated=0 skipped_real=0 already=0
for dir in "$REPO_SKILLS"/*/; do
  [[ -f "${dir}SKILL.md" ]] || continue
  name="$(basename "$dir")"
  src="${REPO_SKILLS}/${name}"
  dst="${TARGET}/${name}"

  if [[ -L "$dst" ]]; then
    if [[ "$(readlink "$dst")" == "$src" ]]; then
      already=$((already+1)); continue
    fi
    echo "UPDATE  $name (re-point symlink)"
    [[ $DRY_RUN -eq 0 ]] && ln -sfn "$src" "$dst"
    updated=$((updated+1))
  elif [[ -e "$dst" ]]; then
    echo "SKIP    $name (real dir in ~/.claude/skills — left untouched)"
    skipped_real=$((skipped_real+1))
  else
    echo "LINK    $name"
    [[ $DRY_RUN -eq 0 ]] && ln -sfn "$src" "$dst"
    linked=$((linked+1))
  fi
done

mode=$([[ $DRY_RUN -eq 1 ]] && echo "(dry-run) " || echo "")
echo "${mode}done: ${linked} linked, ${updated} re-pointed, ${already} already-current, ${skipped_real} real-dirs-skipped → $TARGET"
[[ $skipped_real -gt 0 ]] && echo "Note: skipped real dirs are machine-local; move them into Pi-Dev-Ops/skills/ to make them portable."
exit 0
