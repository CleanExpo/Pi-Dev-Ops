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
  selected_python=
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
