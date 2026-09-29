#!/usr/bin/env bash
# Run any script in this skill through the skill's own venv.
#
# Why this exists (2026-08-10): the scripts used to carry a shebang pointing
# straight at one Mac's venv interpreter. That resolved on exactly one machine.
# Replacing it with `#!/usr/bin/env python3` made it portable but ALSO made it
# wrong by default on Windows, where the shebang is ignored and the system
# Python — which has none of the dependencies — gets used instead. The failure
# then shows up as a confusing ImportError deep in a script rather than as
# "your environment isn't set up".
#
# So: resolve the venv explicitly, on whichever platform, and refuse to run
# without it. A missing venv is a loud, one-line diagnosis; a silent fallback
# to system Python is not.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ -x "$here/.venv/bin/python" ]; then
  py="$here/.venv/bin/python"            # macOS / Linux
elif [ -x "$here/.venv/Scripts/python.exe" ]; then
  py="$here/.venv/Scripts/python.exe"    # Windows
else
  {
    echo "seo: no venv at $here/.venv — refusing to fall back to system Python."
    echo "Create it with:"
    echo "  python3 -m venv \"$here/.venv\""
    echo "  \"$here/.venv/bin/python\" -m pip install -r \"$here/requirements.txt\"   # or .venv/Scripts/python.exe on Windows"
    echo "  \"$here/.venv/bin/python\" -m playwright install chromium                 # only if using capture_screenshot / analyze_visual"
  } >&2
  exit 2
fi

if [ $# -lt 1 ]; then
  echo "usage: run.sh <script> [args...]        e.g. run.sh backlinks summary --help" >&2
  echo "scripts:" >&2
  # Loop, not `ls | xargs basename` — the estate's own paths contain spaces
  # ("Disaster Recovery 4"), which xargs splits on. Caught by testing the
  # usage path rather than only the happy path.
  for f in "$here/scripts"/*.py; do
    [ -e "$f" ] || continue
    echo "  $(basename "$f" .py)" >&2
  done
  exit 64
fi

script="$1"; shift
case "$script" in
  */*) ;;                                   # explicit path, use as given
  *.py) script="$here/scripts/$script" ;;
  *)    script="$here/scripts/$script.py" ;;
esac

if [ ! -f "$script" ]; then
  echo "seo: no such script: $script" >&2
  exit 66
fi

exec "$py" "$script" "$@"
