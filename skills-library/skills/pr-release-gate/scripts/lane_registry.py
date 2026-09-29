#!/usr/bin/env python3
"""The single source of truth for review lanes: what each one IS, not how it is called.

WHY THIS EXISTS
    Until 2026-09-23 a lane was described in three places that could disagree:
    `independent_review.py:685` (the LANES tuple list), a second hand-maintained
    credential map twenty lines below it, and `bin/lane-status`'s own `rows` dict.
    The LANES block already carried a comment recording that a hardcoded display had
    survived the ollama removal and gone on advertising a banned lane. The fix for that
    was to derive the display from LANES — and then a second hardcoded map was written
    directly underneath, which is the same defect one level down.

    So this file holds DATA and the rules that read it. It deliberately does not import
    the lane functions: the callable lives with the transport, the description lives
    here, and `independent_review.py` binds the two together at the bottom of its module.
    That is also why credential probes are declared as {kind, ...} rather than as
    lambdas — a probe needs `resolve_secret`, which lives in the caller, and importing
    it here would make the cycle this file exists to break.

TWO RULES THE MACHINE ENFORCES, so they stop depending on a reviewer remembering them:

  1. mutation needs a shell. Only a lane with a repo, a shell and tools can construct a
     mutant and watch it fail. Gemini and OpenRouter cannot, and on 2026-09-23 a gemini
     PASS on 5147cf93 sat beside a cursor FAIL on the same commit: cursor RAN the code
     and found a P0 that gemini had reasoned past. `refuse_route` makes recording that
     kind of PASS as mutation evidence a structural impossibility rather than a matter
     of discipline.

  2. a vendor's usage policy is data, not prose. BytePlus ModelArk's subscription terms
     say the Coding Plan is "Only available in AI coding tools… Not available for API
     calls", and that using its base URL outside a coding tool "may be identified as
     abuse… which could result in subscription deactivation or account suspension".
     A rule that only exists in a markdown file gets broken by the next agent that does
     not read it, so it is carried here as `api_calls_forbidden` and checked.
"""
from __future__ import annotations

import argparse
import sys

# capability vocabulary — a task asks for these, a lane offers them
SHELL = "shell"                      # has a repo, a shell and tools
MUTATION = "mutation"                # can build a mutant and watch a control fail
CORROBORATION = "corroboration"      # a second opinion; reasoning only
LONG_CONTEXT = "long_context"        # whole-repo sized input

# cost_class drives order: owned subscriptions and free before anything metered.
# Founder cost law, 29/08/2026 — OpenRouter's key is uncapped, so it is reached
# deliberately and last, never by default.
COST_ORDER = {"owned_subscription": 0, "free": 1, "prepaid": 2, "metered": 3}

LANES: list[dict] = [
    {
        "id": "cursor",
        "transport": "cli",
        "capabilities": [SHELL, MUTATION, CORROBORATION],
        "cost_class": "owned_subscription",
        "enabled": True,
        "credential": {"kind": "binary", "bin": "cursor-agent",
                       "also": "~/.local/bin/cursor-agent"},
        "usage_policy": {},
        "note": "Being cancelled (founder, 18/09/2026). One of only two shell lanes, so "
                "it must not lapse before a replacement is proven.",
    },
    {
        "id": "codex",
        "transport": "cli",
        "capabilities": [SHELL, MUTATION, CORROBORATION],
        "cost_class": "owned_subscription",
        "enabled": True,
        "credential": {"kind": "binary", "bin": "codex"},
        "usage_policy": {},
        "note": "ChatGPT subscription, never API credits. Exits 0 on quota exhaustion, so "
                "it is judged on the report file and never on its exit code.",
    },
    {
        "id": "deepseek",
        "transport": "cli",
        "capabilities": [SHELL, MUTATION, CORROBORATION, LONG_CONTEXT],
        "cost_class": "owned_subscription",
        # Registered but NOT routed: no subscription and no driver yet. Declaring it
        # disabled is the honest state — it means lane-status reports it as a known lane
        # that is not live, rather than a future session "discovering" it is missing.
        "enabled": False,
        "credential": {"kind": "secret", "env": "BYTEPLUS_CODING_KEY"},
        "usage_policy": {
            "api_calls_forbidden": True,
            "must_drive_tool": True,
            "reason": "BytePlus ModelArk Coding Plan: 'Only available in AI coding tools… "
                      "Not available for API calls.' Using its base URL outside a coding "
                      "tool risks subscription deactivation or account suspension.",
        },
        "note": "DeepSeek-V4 via BytePlus ModelArk. NOT the same as DeepSeek direct "
                "(api.deepseek.com, prepaid key in ~/.hermes/.env) — different host, auth "
                "header and model ids. Do not reuse that connections.md row for this.",
    },
    {
        "id": "gemini",
        "transport": "http",
        "capabilities": [CORROBORATION],
        "cost_class": "free",
        "enabled": True,
        "credential": {"kind": "secret", "env": "GEMINI_API_KEY"},
        "usage_policy": {},
        "note": "No shell. Cannot discharge mutation-control, by construction.",
    },
    {
        "id": "openrouter",
        "transport": "http",
        "capabilities": [CORROBORATION],
        "cost_class": "metered",
        "enabled": True,
        "credential": {"kind": "secret", "env": "OPENROUTER_API_KEY"},
        "usage_policy": {"free_models_only": True},
        "note": "Uncapped metered key; reached deliberately and last. Free-model harness "
                "only — a non ':free' model is refused by the lane itself.",
    },
]


def lane(lane_id: str) -> dict | None:
    return next((l for l in LANES if l["id"] == lane_id), None)


def ordered(enabled_only: bool = True) -> list[dict]:
    """Lanes in cost-law order. Ties keep their declared order, so a deliberate
    ordering inside one cost class is preserved rather than sorted arbitrarily."""
    rows = [l for l in LANES if l["enabled"] or not enabled_only]
    return sorted(rows, key=lambda l: COST_ORDER[l["cost_class"]])


def refuse_route(lane_id: str, needs: list[str], via_tool: bool = False) -> str | None:
    """Return a refusal reason, or None if the route is allowed.

    A refusal is a REASON, never a silent downgrade to a weaker lane. Quietly picking a
    shell-less lane for a mutation task is exactly how a review that could not run gets
    recorded as a review that found nothing.
    """
    row = lane(lane_id)
    if row is None:
        return f"unknown lane {lane_id!r}; known: {', '.join(l['id'] for l in LANES)}"
    missing = [c for c in needs if c not in row["capabilities"]]
    if missing:
        return (f"lane {lane_id!r} cannot supply {', '.join(missing)} — it offers "
                f"{', '.join(row['capabilities'])}")
    if row["usage_policy"].get("api_calls_forbidden") and not via_tool:
        return (f"lane {lane_id!r} forbids direct API calls: "
                f"{row['usage_policy']['reason']}")
    return None


def _self_test(require_refusal_control: bool) -> int:
    failed = 0

    def check(ok: bool, name: str, detail: str = "") -> None:
        nonlocal failed
        print(f"{'ok  ' if ok else 'FAIL'}  {name}{(' — ' + detail) if detail else ''}")
        failed += 0 if ok else 1

    ids = [l["id"] for l in LANES]
    check(len(ids) == len(set(ids)), "lane ids are unique")
    check(all(l["cost_class"] in COST_ORDER for l in LANES), "every cost_class is known")
    check(all(MUTATION not in l["capabilities"] or SHELL in l["capabilities"]
              for l in LANES),
          "no lane claims mutation without a shell",
          "a shell-less lane claiming mutation would defeat the guard")

    order = [l["id"] for l in ordered()]
    check(order.index("openrouter") == len(order) - 1,
          "metered OpenRouter is ordered last", f"order={order}")

    if require_refusal_control:
        # The guard has to be watched REFUSING, not merely allowing. A guard only ever
        # exercised on the happy path is indistinguishable from `return None`.
        got = refuse_route("gemini", [MUTATION])
        check(got is not None and "cannot supply" in got,
              "REFUSAL: shell-less gemini is refused a mutation task", str(got))

        got = refuse_route("cursor", [MUTATION])
        check(got is None, "shell lane cursor is allowed a mutation task", str(got))

        got = refuse_route("deepseek", [CORROBORATION])
        check(got is not None and "forbids direct API calls" in got,
              "REFUSAL: a policy-restricted lane is refused the direct API route", str(got))

        got = refuse_route("deepseek", [CORROBORATION], via_tool=True)
        check(got is None, "the same lane is allowed when driven through its tool", str(got))

        got = refuse_route("nosuchlane", [CORROBORATION])
        check(got is not None and "unknown lane" in got,
              "REFUSAL: an unknown lane name is named, not silently ignored", str(got))

    print("\nself-test: " + ("all controls held" if not failed else f"{failed} BROKEN"))
    return 1 if failed else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--require-refusal-control", action="store_true",
                    help="also prove the guard REFUSES, not just that it allows")
    ap.add_argument("--assert-policy", nargs=2, metavar=("LANE", "FLAG"),
                    help="exit 0 only if LANE declares FLAG true in usage_policy")
    ap.add_argument("--list", action="store_true", help="print the registry, in order")
    args = ap.parse_args()

    if args.assert_policy:
        lane_id, flag = args.assert_policy
        row = lane(lane_id)
        if row is None:
            print(f"unknown lane {lane_id!r}")
            return 1
        if not row["usage_policy"].get(flag):
            print(f"lane {lane_id!r} does not declare {flag!r}")
            return 1
        print(f"{lane_id}: {flag}=True — {row['usage_policy'].get('reason', '')}")
        return 0

    if args.list:
        for i, l in enumerate(ordered(enabled_only=False), 1):
            state = "live" if l["enabled"] else "registered, not routed"
            print(f"{i}  {l['id']:<11} {l['transport']:<4} {l['cost_class']:<19} "
                  f"{state:<24} {','.join(l['capabilities'])}")
        return 0

    if args.self_test:
        return _self_test(args.require_refusal_control)

    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
