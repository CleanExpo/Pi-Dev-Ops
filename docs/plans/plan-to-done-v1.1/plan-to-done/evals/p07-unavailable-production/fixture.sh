#!/usr/bin/env bash
# TODO(P07): seed a fixture repository that reproduces the scenario:
#   Repository files are visible; deployed state cannot be read.
# Runs only with `claude plugin eval . --scaffold`. Keep it deterministic.
set -euo pipefail
mkdir -p docs/plans/
echo "fixture for P07 not yet written" > docs/plans/FIXTURE-TODO.md
exit 1  # fail loudly until the fixture exists
