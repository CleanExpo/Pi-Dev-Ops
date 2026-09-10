#!/usr/bin/env python3
"""Fail when CI gates a pull request on something the local gate does not run.

WHY THIS EXISTS
---------------
`scripts/handoff-loop.sh` is the definition-of-done gate every session runs before
handing off, and its exit code is read as "this branch is green". On 2026-09-10 a
branch was green under it and would have failed CI, because its 18 gates contained
no size checks. That is a FALSE GREEN, and a false green is worse than a red: a red
stops you, a false green ships.

The instinct is to add the one missing gate. That is the mistake this file refuses
to repeat. When the omission was enumerated properly, CI turned out to gate on FIVE
commands the local gate never ran, not one. Patching the one you happened to trip
over leaves four holes and restores your confidence in the instrument, which is the
worst of both outcomes.

So this compares the WHOLE list, mechanically, and fails on drift:

    every `run:` command in a CI job that gates a pull request
        must appear in .github/gate-parity.map.json
        mapped either to a gate name that really exists in handoff-loop.sh,
        or to an explicit exemption WITH a reason.

A new CI step therefore fails this check until somebody decides, in writing,
whether the local gate should run it. Silence is not an answer here; an unmapped
step is a failure, never a pass (rules/truth-hacking.md, Law 3).

HONEST LIMIT
------------
This proves the local gate RUNS an equivalent command. It cannot prove the two
behave identically -- CI runs on ubuntu with a clean checkout, the local gate runs
on a developer Mac with whatever state that has. Parity of coverage, not parity of
verdict. Where those diverge the map's `note` field is the place to say so.

    python3 .github/scripts/gate_parity_lint.py            # check
    python3 .github/scripts/gate_parity_lint.py --report   # show the full mapping
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import NamedTuple

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"
HANDOFF = ROOT / "scripts" / "handoff-loop.sh"
MAP_PATH = ROOT / ".github" / "gate-parity.map.json"

# Steps that cannot meaningfully run on a laptop before a push. Kept deliberately
# short: every entry here is coverage we do NOT have locally, so the list is a
# liability, not a convenience.
_NEVER_LOCAL = "not-runnable-locally"

# Steps that set the stage rather than judge anything: dependency installs, starting
# and stopping the server, waits, log dumps. They can fail a CI run, but they cannot
# fail a BRANCH — there is no defect in your code they detect. Classified once so
# they stop being noise, and named explicitly so nobody can quietly file a real gate
# here to make this check go green.
_ENVIRONMENT = "environment"


def local_gate_names() -> set[str]:
    """The gate names handoff-loop.sh actually declares."""
    if not HANDOFF.exists():
        sys.exit(f"REFUSED: {HANDOFF} is missing — cannot check parity against nothing")
    return set(re.findall(r'gate "([a-z0-9-]+)"', HANDOFF.read_text()))


def gating_workflows() -> list[Path]:
    """The workflows this check holds the local gate to.

    SCOPE, stated rather than implied: ci.yml only. It is the workflow that runs
    on every pull request with no path filter, so it is the one whose red the
    local gate must be able to predict.

    The other PR-triggered workflows (design-lint, fail-open-check, pgtap-pilot,
    smoke_surface_gate, and the drift checks) are path-filtered specialists that
    mostly cannot run on a laptop — pgtap needs a postgres service, the surface
    gate needs the PR's base..head diff. They are deliberately OUT of scope for
    now, which means a green local gate still does not predict THEIR red. That is
    a real remaining hole and it is named here so it stays visible; widening this
    tuple is how it gets closed.

    Returning an empty list would make the whole check vacuous, so that is a hard
    failure rather than a pass.
    """
    scoped = ("ci.yml",)
    out = [WORKFLOWS / n for n in scoped if (WORKFLOWS / n).exists()]
    if not out:
        sys.exit("REFUSED: none of the scoped workflows exist — a parity check "
                 "over zero workflows would pass while proving nothing")
    return out


def ci_steps(wf: Path) -> list[tuple[str, str]]:
    """(step name, first line of its run command) for every `run:` step.

    Deliberately regex rather than a YAML parser: this repo has no yaml dependency
    in its CI-time environment, and the shapes here are the two GitHub emits. A
    step whose name cannot be read is reported, never skipped.

    Every list item (`- ...`) starts a NEW step, so `name` is reset there first —
    otherwise an unnamed step inherits the PREVIOUS step's name and map exemption.
    `name:` still requires the leading `-`, which is what tells a step's own name
    apart from a job- or workflow-level `name:` key at the same indent (a bare
    `name:` regex misread `jobs.<job>.name` as a step). `run:` gets an OPTIONAL
    leading `-` so the combined one-line form (`- run: cmd`, no separate name)
    is seen too — the old pattern needed `run:` to start the line, so that form
    was invisible. See `tests/test_gate_parity_lint.py` for both fixtures.
    """
    steps: list[tuple[str, str]] = []
    lines = wf.read_text().split("\n")
    name = ""
    for i, ln in enumerate(lines):
        if re.match(r"\s*-\s", ln):
            name = ""
        m = re.match(r"\s*- name:\s*(.+?)\s*$", ln)
        if m:
            name = m.group(1)
            continue
        m = re.match(r"\s*-?\s*run:\s*(.*)$", ln)
        if not m:
            continue
        cmd = m.group(1).strip()
        if cmd in ("|", ">", "|-", ">-"):
            # Block scalar: take the first non-empty line of the block.
            for nxt in lines[i + 1:]:
                if nxt.strip():
                    cmd = nxt.strip()
                    break
        steps.append((name or "<unnamed step>", cmd))
    return steps


def load_map() -> dict:
    if not MAP_PATH.exists():
        sys.exit(f"REFUSED: {MAP_PATH} is missing — the map IS the check; "
                 f"without it every step would look exempt")
    return json.loads(MAP_PATH.read_text())


def key_for(wf: Path, step_name: str) -> str:
    return f"{wf.name}::{step_name}"


class Buckets(NamedTuple):
    covered: list[tuple[str, str]]
    exempt: list[tuple[str, str]]
    dangling: list[tuple[str, str]]
    unmapped: list[str]


def classify(gates: set[str], entries: dict) -> Buckets:
    """Sort every gating CI step into one of four buckets.

    An unmapped step lands in `unmapped`, never in `exempt`: silence is not an
    exemption, or a step could be excused from local coverage by nobody writing
    it down.
    """
    b = Buckets([], [], [], [])
    for wf in gating_workflows():
        for step_name, cmd in ci_steps(wf):
            key = key_for(wf, step_name)
            entry = entries.get(key)
            if entry is None:
                b.unmapped.append(f"{key}\n      runs: {cmd[:90]}")
                continue
            local = entry.get("local_gate", "")
            if local in (_NEVER_LOCAL, _ENVIRONMENT):
                b.exempt.append((key, f"{local}: {entry.get('reason', '')}"))
            elif local in gates:
                b.covered.append((key, local))
            else:
                b.dangling.append((key, local))
    return b


def print_failures(dangling: list[tuple[str, str]], unmapped: list[str]) -> None:
    for key, local in sorted(dangling):
        print(f"FAIL  {key}: mapped to local gate {local!r}, which handoff-loop.sh "
              f"does not declare. Either the gate was renamed or it was deleted.")
    for item in sorted(unmapped):
        print(f"FAIL  {item}\n      This CI step gates a PR and is not in "
              f"{MAP_PATH.name}. Add it — either name the local gate that covers it, "
              f"or mark it {_NEVER_LOCAL!r} with a reason. An unmapped step is a "
              f"hole in the local gate, so it cannot be treated as a pass.")


def main() -> int:
    report = "--report" in sys.argv
    gates = local_gate_names()
    covered, exempt, dangling, unmapped = classify(gates, load_map().get("steps", {}))

    if report:
        print(f"local gates declared in handoff-loop.sh: {len(gates)}")
        for key, local in sorted(covered):
            print(f"  COVERED  {key}  ->  {local}")
        for key, reason in sorted(exempt):
            print(f"  EXEMPT   {key}  ->  {reason}")

    print_failures(dangling, unmapped)

    bad = len(unmapped) + len(dangling)
    if bad:
        print(f"\ngate-parity FAILED — {len(unmapped)} unmapped, {len(dangling)} dangling. "
              f"handoff-loop.sh exit 0 does NOT currently predict CI green.")
        return 1

    print(f"gate-parity passed — {len(covered)} CI step(s) covered locally, "
          f"{len(exempt)} explicitly exempt, 0 unmapped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
