#!/usr/bin/env bash
# Nexus Mesh — Hermes → ship adapter.
# Wired as a Hermes on_session_end shell hook (see mesh/bootstrap.sh). Hermes pipes
# a JSON payload on stdin carrying `cwd`; mesh_ship.sh cds there and ships the turn.
# Closes the work-plane loop for Hermes-driven turns, same as Claude/Codex Stop hooks.
#
# The shipping logic lives in mesh_ship.sh so every surface (Hermes here, the
# Claude/Codex Stop hooks wired by bootstrap.sh) shares one implementation. This
# file previously called `autogit ship` directly, which silently shipped nothing
# whenever the agent had already committed its own work (RA-7376).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec bash "$HERE/mesh_ship.sh"
