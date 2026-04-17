#!/usr/bin/env bash
# install-on-new-machine.sh — one-shot bootstrap for a fresh machine.
#
# Run this on each of the 2 new machines (CCW + RestoreAssist):
#
#     curl -fsSL https://raw.githubusercontent.com/CleanExpo/Pi-Dev-Ops/main/scripts/supervisor/install-on-new-machine.sh | bash
#
# It will:
#   1. install ollama + pull mistral
#   2. install tmux (brew on mac, apt on linux) if missing
#   3. drop supervisor.py + launch_all_supervisors.sh into ~/.pi-ceo/supervisor/
#   4. write a stub ~/.supervisor.env that you then edit with your project dir
#   5. print next-step instructions
set -euo pipefail

INSTALL_DIR="$HOME/.pi-ceo/supervisor"
ENV_FILE="$HOME/.supervisor.env"
REPO_RAW="https://raw.githubusercontent.com/CleanExpo/Pi-Dev-Ops/main/scripts/supervisor"

mkdir -p "$INSTALL_DIR"

# ---- tmux --------------------------------------------------------
if ! command -v tmux >/dev/null 2>&1; then
  if [[ "$OSTYPE" == darwin* ]]; then
    command -v brew >/dev/null 2>&1 || { echo "Install Homebrew first: https://brew.sh"; exit 1; }
    brew install tmux
  else
    sudo apt-get update && sudo apt-get install -y tmux
  fi
fi

# ---- ollama ------------------------------------------------------
if ! command -v ollama >/dev/null 2>&1; then
  curl -fsSL https://ollama.com/install.sh | sh
fi
if ! pgrep -x ollama >/dev/null 2>&1; then
  nohup ollama serve >"$HOME/.pi-ceo/ollama.log" 2>&1 &
  sleep 3
fi
ollama pull mistral

# ---- scripts -----------------------------------------------------
for f in supervisor.py launch_all_supervisors.sh .supervisor.env.example; do
  curl -fsSL "$REPO_RAW/$f" -o "$INSTALL_DIR/$f"
done
chmod +x "$INSTALL_DIR/launch_all_supervisors.sh" "$INSTALL_DIR/supervisor.py"

# ---- env stub ----------------------------------------------------
if [ ! -f "$ENV_FILE" ]; then
  cp "$INSTALL_DIR/.supervisor.env.example" "$ENV_FILE"
  chmod 600 "$ENV_FILE"
  echo ""
  echo "Edit $ENV_FILE and set PROJECT_DIR + SESSION + MACHINE, then run:"
  echo "   $INSTALL_DIR/launch_all_supervisors.sh"
else
  echo ""
  echo "Existing $ENV_FILE kept. Start supervisor with:"
  echo "   $INSTALL_DIR/launch_all_supervisors.sh"
fi
