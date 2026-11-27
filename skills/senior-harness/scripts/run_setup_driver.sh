#!/bin/sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
repo_python="$script_dir/../../../.venv/bin/python"
python_bin=${SENIOR_HARNESS_PYTHON:-}

is_compatible_python() {
  [ -n "$1" ] && [ -x "$1" ] &&
    [ "$("$1" -c 'import sys; print("senior-harness-python-ok" if sys.version_info >= (3, 10) else "")' 2>/dev/null || true)" = "senior-harness-python-ok" ]
}

if is_compatible_python "$python_bin"; then
  selected_python=$python_bin
elif is_compatible_python "$repo_python"; then
  selected_python=$repo_python
elif command -v python3 >/dev/null 2>&1 && is_compatible_python "$(command -v python3)"; then
  selected_python=$(command -v python3)
else
  # Bare `python3` is often the OS's own interpreter (macOS: /usr/bin/python3 = 3.9)
  # while newer releases are installed only under versioned names. Probe those,
  # newest first, before failing closed. tests/test_senior_harness_launcher_python.py
  # guards this branch.
  selected_python=
  for candidate in python3.14 python3.13 python3.12 python3.11 python3.10; do
    if command -v "$candidate" >/dev/null 2>&1 && is_compatible_python "$(command -v "$candidate")"; then
      selected_python=$(command -v "$candidate")
      break
    fi
  done
fi

reason="Senior Harness denied execution: Python 3.10 or newer is unavailable. Set SENIOR_HARNESS_PYTHON to a compatible interpreter."
if [ -z "$selected_python" ]; then
  printf '%s\n' "$reason" >&2
  exit 2
fi

if [ "${1:-}" = "contract" ]; then
  shift
  exec "$selected_python" "$script_dir/senior_harness.py" "$@"
fi

if [ "${1:-}" = "hook" ]; then
  exec "$selected_python" "$script_dir/setup_hook_bootstrap.py" \
    "$script_dir/setup_driver.py" "$@"
fi

exec "$selected_python" "$script_dir/setup_driver.py" "$@"
