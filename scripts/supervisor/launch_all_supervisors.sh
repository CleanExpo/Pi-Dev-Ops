#!/usr/bin/env bash
# launch_all_supervisors.sh — per-machine launcher.
#
# One machine, one project, one Claude Code session, one supervisor.
# Run on each of the 3 machines (this one + CCW-CRM + RestoreAssist) with
# the project-specific values below.
#
# Usage:
#     PROJECT_DIR=/Users/you/CCW-CRM \
#     SESSION=ccw  \
#     MACHINE=mac-mini-ccw \
#         ./launch_all_supervisors.sh
#
# Or set defaults via env file:
#     cp .supervisor.env.example ~/.supervisor.env
#     edit    ~/.supervisor.env
#     ./launch_all_supervisors.sh
#
# Environment reference:
#     PROJECT_DIR   absolute path to the repo Claude should `cd` into
#     SESSION       tmux session suffix (short, no spaces)  e.g. ccw, restoreassist, synthex
#     MACHINE       human label for this machine — used in Pi-CEO dashboard check-ins
#     STALL_SECONDS default 30; threshold before the supervisor nudges
#     MAX_NUDGES    default 20; cap per Claude session before escalating
#     CHECKIN_URL   optional. If set, each nudge POSTs to this URL for dashboard visibility.
#     CHECKIN_KEY   optional bearer token for CHECKIN_URL.

set -euo pipefail

# Load ~/.supervisor.env if present (machine-specific defaults)
[ -f "$HOME/.supervisor.env" ] && source "$HOME/.supervisor.env"

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="${PROJECT_DIR:?set PROJECT_DIR in env or ~/.supervisor.env}"
SESSION="${SESSION:?set SESSION in env or ~/.supervisor.env}"
MACHINE="${MACHINE:-$(hostname -s)}"
STALL_SECONDS="${STALL_SECONDS:-30}"
MAX_NUDGES="${MAX_NUDGES:-20}"
LOG_DIR="${LOG_DIR:-$HOME/.pi-ceo}"
TMUX_NAME="claude_${SESSION}"
mkdir -p "$LOG_DIR"

log() { echo "[$(date +%H:%M:%S)] [$MACHINE] $*"; }

# ---- 1. Ollama + mistral ---------------------------------------------------
ensure_ollama() {
  if ! command -v ollama >/dev/null 2>&1; then
    log "Installing Ollama..."
    curl -fsSL https://ollama.com/install.sh | sh
  fi
  if ! curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; then
    log "Starting ollama serve in background..."
    nohup ollama serve >"$LOG_DIR/ollama.log" 2>&1 &
    for _ in $(seq 1 20); do
      curl -sf http://localhost:11434/api/tags >/dev/null 2>&1 && break
      sleep 1
    done
  fi
  if ! curl -sf http://localhost:11434/api/tags | grep -q '"mistral"'; then
    log "Pulling mistral model (one-time, ~4 GB)..."
    ollama pull mistral
  fi
  log "Ollama ready."
}

# ---- 2. tmux Claude session in the project dir -----------------------------
ensure_claude_session() {
  if tmux has-session -t "$TMUX_NAME" 2>/dev/null; then
    log "tmux session $TMUX_NAME already running — leaving it alone."
    return 0
  fi
  [ -d "$PROJECT_DIR" ] || { log "PROJECT_DIR $PROJECT_DIR missing"; exit 1; }
  log "Starting tmux session $TMUX_NAME in $PROJECT_DIR ..."
  tmux new-session -d -s "$TMUX_NAME" -c "$PROJECT_DIR"
  tmux send-keys -t "$TMUX_NAME" "claude --dangerously-skip-permissions" Enter
  sleep 2
}

# ---- 3. Supervisor ---------------------------------------------------------
ensure_supervisor() {
  local pid_file="$LOG_DIR/supervisor-$TMUX_NAME.pid"
  if [ -f "$pid_file" ] && kill -0 "$(cat "$pid_file")" 2>/dev/null; then
    log "Supervisor for $TMUX_NAME already running (pid=$(cat "$pid_file"))."
    return 0
  fi
  log "Launching supervisor for $TMUX_NAME..."
  PI_CEO_MACHINE="$MACHINE" \
  PI_CEO_CHECKIN_URL="${CHECKIN_URL:-}" \
  PI_CEO_CHECKIN_KEY="${CHECKIN_KEY:-}" \
  nohup python3 "$HERE/supervisor.py" \
        --session "$TMUX_NAME" \
        --stall-seconds "$STALL_SECONDS" \
        --max-nudges "$MAX_NUDGES" \
        >"$LOG_DIR/supervisor-$TMUX_NAME.log" 2>&1 &
  echo $! >"$pid_file"
}

main() {
  rm -f "$HOME/.pi-ceo/supervisor.stop"
  ensure_ollama
  ensure_claude_session
  ensure_supervisor
  log "All systems go on $MACHINE (session=$TMUX_NAME, project=$PROJECT_DIR)."
  log "To attach:  tmux attach -t $TMUX_NAME"
  log "To tail:    tail -f $LOG_DIR/supervisor-$TMUX_NAME.log"
  log "To stop:    touch $HOME/.pi-ceo/supervisor.stop"
}

main "$@"
