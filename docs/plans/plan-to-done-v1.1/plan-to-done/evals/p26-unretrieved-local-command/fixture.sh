#!/usr/bin/env bash
# TODO(P26): seed a fixture repository that reproduces the scenario:
#   A lookup at skills/goal/SKILL.md returns 404.
# Runs only with `claude plugin eval . --scaffold`. Keep it deterministic.
set -euo pipefail
mkdir -p docs/plans/
echo "fixture for P26 not yet written" > docs/plans/FIXTURE-TODO.md
exit 1  # fail loudly until the fixture exists
