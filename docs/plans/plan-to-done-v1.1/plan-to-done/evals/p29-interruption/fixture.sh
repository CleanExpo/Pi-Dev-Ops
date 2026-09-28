#!/usr/bin/env bash
# TODO(P29): seed a fixture repository that reproduces the scenario:
#   Planning stops mid-packet and resumes with a new model session.
# Runs only with `claude plugin eval . --scaffold`. Keep it deterministic.
set -euo pipefail
mkdir -p docs/plans/
echo "fixture for P29 not yet written" > docs/plans/FIXTURE-TODO.md
exit 1  # fail loudly until the fixture exists
