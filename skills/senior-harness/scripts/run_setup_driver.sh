#!/bin/sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
repo_python="$script_dir/../../../.venv/bin/python"
python_bin=${SENIOR_HARNESS_PYTHON:-}

if [ -n "$python_bin" ] && [ -x "$python_bin" ]; then
  exec "$python_bin" "$script_dir/setup_driver.py" "$@"
fi
if [ -x "$repo_python" ]; then
  exec "$repo_python" "$script_dir/setup_driver.py" "$@"
fi
if command -v python3 >/dev/null 2>&1 && python3 -c 'import sys; raise SystemExit(sys.version_info < (3, 10))'; then
  exec python3 "$script_dir/setup_driver.py" "$@"
fi

event=PreToolUse
previous=
for argument in "$@"; do
  if [ "$previous" = "--event" ]; then event=$argument; break; fi
  previous=$argument
done
reason="Senior Harness denied execution: Python 3.10 or newer is unavailable. Set SENIOR_HARNESS_PYTHON to a compatible interpreter."
if [ "$event" = "UserPromptSubmit" ]; then
  printf '{"decision":"block","reason":"%s","hookSpecificOutput":{"hookEventName":"%s","additionalContext":"%s"}}\n' "$reason" "$event" "$reason"
elif [ "$event" = "PreToolUse" ]; then
  printf '{"hookSpecificOutput":{"hookEventName":"%s","permissionDecision":"deny","permissionDecisionReason":"%s"}}\n' "$event" "$reason"
else
  printf '{"hookSpecificOutput":{"hookEventName":"%s","additionalContext":"%s"}}\n' "$event" "$reason"
fi
