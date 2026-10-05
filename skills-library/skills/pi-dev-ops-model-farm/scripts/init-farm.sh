#!/bin/bash
# Pi-Dev-Ops Model Farm — Quick-start wrapper for model-farm.py (Python threads, no tmux needed)

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON3="/c/Program Files/Python311/python.exe"

# Validate binaries
if [ ! -x "$PYTHON3" ]; then
    echo "Python 3.11 not found at $PYTHON3"
    echo "Falling back to system python3"
    PYTHON3="$(which python3 2>/dev/null || which python 2>/dev/null)"
    if [ -z "$PYTHON3" ]; then
        echo "ERROR: No Python found"
        exit 1
    fi
fi

case "${1:-}" in
    status|--status)
        "$PYTHON3" "$SCRIPT_DIR/model-farm.py" --status
        ;;
    stop|--stop)
        "$PYTHON3" "$SCRIPT_DIR/model-farm.py" --stop
        # Also kill any background farm stdout/stderr holder
        for p in $(ps -W 2>/dev/null | grep "model-farm" | grep -v grep | awk '{print $1}'); do
            kill "$p" 2>/dev/null || true
        done
        ;;
    start|--start|*)  # Default = start
        # Clean old stop file
        rm -f "$SCRIPT_DIR/farm.stop" 2>/dev/null || true
        # Start farm as background daemon (Windows compatible, redirects to files)
        nohup "$PYTHON3" "$SCRIPT_DIR/model-farm.py" --start >""$SCRIPT_DIR/farm.stdout.log"" 2>""$SCRIPT_DIR/farm.stderr.log"" &
        echo "Farm started (PID $!). Check with: $0 status"
        sleep 2
        ;;
esac
