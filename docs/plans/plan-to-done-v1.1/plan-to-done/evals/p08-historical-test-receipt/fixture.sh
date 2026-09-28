#!/usr/bin/env bash
# TODO(P08): seed a fixture repository that reproduces the scenario:
#   The only passing test report belongs to an older commit.
# Runs only with `claude plugin eval . --scaffold`. Keep it deterministic.
set -euo pipefail
mkdir -p docs/plans/
echo "fixture for P08 not yet written" > docs/plans/FIXTURE-TODO.md
exit 1  # fail loudly until the fixture exists
