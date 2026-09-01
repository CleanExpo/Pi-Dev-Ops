#!/usr/bin/env python3
"""Baseline parsers for `baseline_ratchet.py` — one per baseline format.

Split out of that script when it crossed the 300-line convention. The boundary
is a real one rather than an arbitrary cut: everything here turns FILE TEXT
into a `{key: limit}` mapping, and knows nothing about git, directions, or
what makes a change a weakening. The ratchet holds all of that.

Extracted rather than baselining the over-length file, per CLAUDE.md: "Extract
when you edit one... Never raise an entry to get green."
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import re

REPO = pathlib.Path(__file__).resolve().parents[2]
SURFACE_GATE = REPO / ".github" / "scripts" / "smoke_surface_gate.py"

# key -> numeric limit, or None where the baseline lists bare keys with no value.
Baseline = dict[str, "int | None"]


def parse_tsv(text: str) -> Baseline:
    """`count \\t fingerprint \\t key` — both length baselines."""
    out: Baseline = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = stripped.split("\t")
        if len(parts) < 3:
            continue
        try:
            out[parts[2]] = int(parts[0])
        except ValueError:
            continue
    return out


def parse_kv(text: str) -> Baseline:
    """`key=value` — the design-md lint baseline."""
    out: Baseline = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        try:
            out[key.strip()] = int(value.strip())
        except ValueError:
            out[key.strip()] = None
    return out


def parse_rls(text: str) -> Baseline:
    """Table names from the `_rls_baseline` INSERT in rls_coverage.sql.

    Comments are stripped FIRST, and that is load-bearing. One of them contains
    an apostrophe ("Supabase's advisor"); a naive quote scan reads it as an
    opening quote and swallows the rest of the block, returning 5 entries where
    there are 9. A parser that under-reports here would report "no additions" on
    a diff that added four -- this guard becoming the thing it guards.
    """
    body = "\n".join(
        line for line in text.splitlines() if not line.strip().startswith("--")
    )
    match = re.search(r"insert\s+into\s+_rls_baseline.*?;", body, re.S | re.I)
    if not match:
        return {}
    return {t: None for t in re.findall(r"\(\s*'([a-z0-9_]+)'\s*,", match.group(0), re.I)}


def parse_names(text: str) -> Baseline:
    """`name \\t why` — the schema-drift baseline, which carries no numbers."""
    out: Baseline = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        out[stripped.split("\t")[0].strip()] = None
    return out


def parse_surfaces(text: str) -> Baseline:
    """Entry keys from `.github/smoke-surfaces.json` — the coverage direction.

    This one ratchets the OPPOSITE way to every other entry below. The length
    and RLS baselines are lists of exemptions, so they weaken by GROWING. This
    is a list of what the e2e suite probes, so it weakens by SHRINKING: delete
    an entry and `scripts/smoke_test_e2e.py` exercises less against the live
    deploy, while the suite still reports the same green (RA-7402).

    The horizontal half reuses `parse_manifest()` from the surface gate rather
    than parsing this file a third time. That function already gets the subtle
    part right — an unparseable manifest yields `{}` rather than "no entries",
    which `check_one`'s `if not before` guard then treats as unverifiable
    instead of reporting every entry as removed. `.get("names", ...)` because
    that failure path returns a bare dict with no `names` key at all.

    Vertical steps are keyed on action + path because they carry no `name`.
    They are covered deliberately: RA-7402 named only `horizontal`, but a
    deleted build-lifecycle step shrinks coverage exactly the same way.
    """
    spec = importlib.util.spec_from_file_location("smoke_surface_gate", SURFACE_GATE)
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)

    out: Baseline = {name: None for name in gate.parse_manifest(text).get("names", set())}
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return out
    for step in ((data.get("vertical") or {}).get("steps") or []):
        if not isinstance(step, dict):
            continue
        target = step.get("path") or step.get("path_template")
        if target:
            out[f"vertical:{step.get('action', '?')}:{target}"] = None
    return out
