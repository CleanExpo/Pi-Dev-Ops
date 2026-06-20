#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

pick_python() {
  for candidate in "${PYTHON:-}" "$ROOT/.venv/bin/python" python3.12 python3.11 "$HOME/.local/bin/python3.11" "$HOME/.local/bin/python3.12"; do
    if [[ -n "$candidate" ]] && command -v "$candidate" >/dev/null 2>&1; then
      "$candidate" - <<'PY' >/dev/null 2>&1 && { printf '%s\n' "$candidate"; return 0; }
import sys
raise SystemExit(0 if sys.version_info >= (3, 11) else 1)
PY
    fi
  done
  return 1
}

PYTHON_BIN="$(pick_python || true)"
if [[ -z "$PYTHON_BIN" ]]; then
  echo "Pi-CEO tests require Python >=3.11. Install python3.11 or set PYTHON=/path/to/python3.11." >&2
  exit 2
fi

if "$PYTHON_BIN" - <<'PY' >/dev/null 2>&1
import pytest  # noqa: F401
import pytest_asyncio  # noqa: F401
import claude_agent_sdk  # noqa: F401
PY
then
  exec "$PYTHON_BIN" -m pytest "$@"
fi

if command -v uv >/dev/null 2>&1; then
  exec uv run --no-project --python "$PYTHON_BIN" --with-requirements app/requirements.txt --with pytest pytest "$@"
fi

echo "$PYTHON_BIN exists but pytest is not installed, and uv is unavailable." >&2
echo "Install test dependencies or run: uv run --python $PYTHON_BIN --with pytest --with pytest-asyncio pytest <tests>" >&2
exit 2
