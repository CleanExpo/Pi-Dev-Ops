#!/usr/bin/env bash
# start_swarm.sh — Swarm launcher for launchd.
# Sources .env.local so secrets stay out of the plist file.
set -a
source "/Users/phill-mac/Pi-CEO/Pi-Dev-Ops/.env.local"
set +a

exec /Users/phill-mac/.pyenv/versions/3.13.13/bin/python -m swarm.orchestrator
