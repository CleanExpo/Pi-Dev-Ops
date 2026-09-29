#!/bin/sh
# usage: sh scripts/link_skills_home.sh <dir, normally ~/.claude/skills> [<repo root>]
#
# Library skills name their own files as ~/.claude/skills/<name>/..., the path they have on a
# workstation. Link every skill Mission Control ships into <dir> so those paths resolve in the
# image: the library copy first, then this repo's skills/, so a name in both points at the
# skills/ copy, the one src/tao/skills.py loads.
set -eu
dir="$1"
root="${2:-$(cd "$(dirname "$0")/.." && pwd)}"
mkdir -p "$dir"
for src in "$root"/skills-library/skills/* "$root"/skills/*; do
  ln -sfn "$src" "$dir/$(basename "$src")"
done
