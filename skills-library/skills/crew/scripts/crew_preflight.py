#!/usr/bin/env python3
"""Preflight for a /crew dispatch: grounding stamp and the risk-tier gate.

Grounding. The vault index is checked, not assumed. `brain.js check` currently reports 619
drift issues on this estate, and an agent that grounds against a lying index looks grounded
and is not. Rather than block every dispatch on a vault-wide reindex, the run carries the
number: OK, or DEGRADED with the drift count, recorded in the evidence log and printed at the
top of the render. The estate already stamps a weaker reviewer DEGRADED rather than
substituting it silently; this is the same rule applied to grounding.

Risk tier. Every role declares a `risk_tier_ceiling` in the registry. The gate answers one
question -- may this role be dispatched at the requested tier -- and answers it by ALLOWLIST:
a role is dispatchable only if the registry names it and its ceiling covers the request.
An unknown role, an unparseable registry, or a missing ceiling all refuse. Detecting
disallowed roles instead would be the losing direction; the estate has lost that argument
before.
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REGISTRY = Path.home() / "Pi-CEO" / ".harness" / "agents" / "registry.yaml"


# The vault is checked out as `2nd Brain` on one machine and `2nd-brain` on another, so the
# name cannot be hardcoded. It is also not a free glob: `~/2nd*` would execute brain.js from
# any directory that happens to start with those characters. Naming both known checkouts keeps
# the cross-machine property without widening what may be run.
VAULT_DIRS = ("2nd Brain", "2nd-brain")


def find_brain_js():
    """Resolve brain.js on either known vault checkout. Never hardcode one machine's path."""
    for name in VAULT_DIRS:
        cand = Path.home() / name / "2nd Brain" / "_system" / "brain.js"
        if cand.exists():
            return cand
    return None


def grounding_status():
    """Return (stamp, detail). Never raises: preflight reports, it does not crash a run."""
    brain = find_brain_js()
    if brain is None:
        return "UNAVAILABLE", "brain.js not found on this machine"
    try:
        proc = subprocess.run(["node", str(brain), "check"],
                              capture_output=True, text=True, timeout=180)
    except (OSError, subprocess.SubprocessError) as exc:
        return "UNAVAILABLE", f"brain.js check did not run: {exc}"

    if proc.returncode == 0:
        return "OK", "index clean"
    m = re.search(r"(\d+)\s+drift issue", proc.stdout + proc.stderr)
    count = m.group(1) if m else "unknown"
    return "DEGRADED", f"{count} drift issue(s) in the vault index"


def load_registry(path=REGISTRY):
    """Parse the roles out of registry.yaml.

    Deliberately a narrow line parser rather than a YAML dependency: the estate's gates are
    stdlib-only, and this reads two fields from a file whose shape is fixed. A role only
    enters the allowlist when BOTH its id and an integer ceiling were read.
    """
    roles = {}
    if not path.exists():
        return roles
    current = None
    in_agents = False
    for raw in path.read_text(encoding="utf-8").splitlines():
        if re.match(r"^agents:\s*$", raw):
            in_agents = True
            continue
        # Any other top-level key ends the agents block -- accepted_projection_drift also
        # carries `- id:` entries and must not be read as dispatchable roles.
        if in_agents and re.match(r"^[A-Za-z_]", raw):
            in_agents = False
        if not in_agents:
            continue
        m = re.match(r"^\s*-\s*id:\s*(\S+)\s*$", raw)
        if m:
            # YAML permits `id: "scout"`. Captured raw, the quotes become part of the key and
            # every lookup misses, which fails closed but silently makes the whole crew
            # undispatchable. Strip one matched pair; an unbalanced quote is left alone so it
            # still misses rather than resolving to something unintended.
            current = m.group(1)
            for q in ('"', "'"):
                if len(current) >= 2 and current[0] == q and current[-1] == q:
                    current = current[1:-1]
                    break
            current = current or None
            continue
        m = re.match(r"^\s*risk_tier_ceiling:\s*(\d+)\s*$", raw)
        if m and current:
            roles[current] = int(m.group(1))
            current = None
    return roles


def check_role(role, tier, roles):
    """Allow only what the registry positively permits."""
    if not roles:
        return False, "registry unreadable or empty — refusing every role"
    if role not in roles:
        return False, f"role '{role}' is not in the registry"
    ceiling = roles[role]
    if tier > ceiling:
        return False, f"tier {tier} exceeds '{role}' ceiling {ceiling}"
    return True, f"tier {tier} within '{role}' ceiling {ceiling}"


def main() -> int:
    ap = argparse.ArgumentParser(description="/crew preflight")
    ap.add_argument("--role", default=None, help="check one role's dispatchability")
    ap.add_argument("--tier", type=int, default=0)
    ap.add_argument("--registry", default=str(REGISTRY))
    ap.add_argument("--skip-grounding", action="store_true",
                    help="skip the vault index check (used by the test harness)")
    args = ap.parse_args()

    roles = load_registry(Path(args.registry))

    if args.role:
        ok, why = check_role(args.role, args.tier, roles)
        print(json.dumps({"role": args.role, "tier": args.tier,
                          "allowed": ok, "reason": why}, sort_keys=True))
        return 0 if ok else 1

    if args.skip_grounding:
        stamp, detail = "SKIPPED", "grounding check skipped by flag"
    else:
        stamp, detail = grounding_status()
    print(json.dumps({"grounding": stamp, "detail": detail,
                      "roles": roles}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
