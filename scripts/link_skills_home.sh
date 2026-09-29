#!/bin/sh
# usage: sh scripts/link_skills_home.sh <dir, normally ~/.claude/skills> [<repo root>]
#
# Library skills name their own files as ~/.claude/skills/<name>/..., the path they have on a
# workstation. Link every skill Mission Control ships into <dir> so those paths resolve in the
# image: the library copy first, then this repo's skills/, so a name in both points at the
# skills/ copy, the one src/tao/skills.py loads.
#
# A source that is itself a symlink could point anywhere, so it stops the script; so does a
# real file or folder already at a link's name, which ln would write into instead of replacing.
set -eu
dir="$1"
root="${2:-$(cd "$(dirname "$0")/.." && pwd)}"
mkdir -p "$dir"
for src in "$root"/skills-library/skills/* "$root"/skills/*; do
  link="$dir/$(basename "$src")"
  if [ -L "$src" ]; then
    echo "refusing $src: a symlink, which may point outside the repo" >&2
    exit 1
  fi
  if [ -e "$link" ] && [ ! -L "$link" ]; then
    echo "refusing $link: a real file or folder is already there" >&2
    exit 1
  fi
  ln -sfn "$src" "$link"
done
