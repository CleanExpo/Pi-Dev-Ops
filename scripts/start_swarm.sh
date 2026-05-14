#!/usr/bin/env bash
# start_swarm.sh — Swarm launcher for launchd.
#
# Env precedence (load order matters — second source wins on conflict):
#   1. ~/.hermes/.env       — empire-wide secrets (GEMINI_API_KEY, SUPABASE_*,
#                             ELEVENLABS_*, OPENROUTER_API_KEY, MARGOT_*, etc.).
#                             Canonical home documented in swarm/research/
#                             gemini_research.py. Non-fatal if missing.
#   2. .env.local           — swarm-specific overrides (LINEAR_API_KEY,
#                             ANTHROPIC_API_KEY, TAO_*, GITHUB_TOKEN).
#                             Always wins on conflict with hermes.
#
# Why both: RA-1986 wired Gemini grounded research as the default Margot
# backend, and its key lives in ~/.hermes/.env. Before this change cron only
# sourced .env.local, so GEMINI_API_KEY was unset at boot and grounded
# research silently fell back. See RA-1986 follow-up.

set -a

# 1. Hermes empire-wide env (optional — graceful if missing)
HERMES_ENV="${HOME}/.hermes/.env"
if [ -f "${HERMES_ENV}" ]; then
    source "${HERMES_ENV}"
fi

# 2. Swarm-specific overrides (required)
source "/Users/phill-mac/Pi-CEO/Pi-Dev-Ops/.env.local"

set +a

exec /Users/phill-mac/.pyenv/versions/3.13.13/bin/python -m swarm.orchestrator
