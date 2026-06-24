#!/usr/bin/env python3
"""Route noisy project asks into one NorthStar ShipIt lane."""
from __future__ import annotations

import argparse
from pathlib import Path

_NOISE_WORDS = {
    "vendor": "new vendor/platform change without approval",
    "vendors": "new vendor/platform change without approval",
    "redesign": "secondary design branch unless launch-blocking",
    "maybe": "speculative branch without evidence",
    "investigate": "research branch deferred unless it gates launch",
    "docs": "documentation-only branch deferred unless it unblocks ShipIt",
}


def route_priority(brief: str) -> dict[str, object]:
    lower = brief.lower()
    deferred = [reason for word, reason in _NOISE_WORDS.items() if word in lower]
    if any(word in lower for word in ["tests unknown", "build unknown", "unknown build", "ci unknown"]):
        lane = "launch-project-audit"
        next_artifact = ".harness/audits/launch-project-audit.md"
        status = "LOCAL_SAFE"
    elif any(word in lower for word in ["bloat", "cleanup", "clean up", "dead code"]):
        lane = "launch-enhance-debloat"
        next_artifact = ".harness/audits/enhance-latest.md"
        status = "LOCAL_SAFE"
    elif any(word in lower for word in ["ship", "launch", "production"]):
        lane = "ship-it"
        next_artifact = ".harness/ship-it/latest.md"
        status = "LOCAL_SAFE"
    else:
        lane = "launch-charter"
        next_artifact = ".harness/northstar/default-path.md"
        status = "LOCAL_SAFE"
    return {
        "northstar_outcome": "Choose one governed lane and defer non-launch noise.",
        "lane": lane,
        "status": status,
        "deferred_noise": sorted(set(deferred)),
        "next_skill": lane,
        "next_artifact": next_artifact,
    }


def write_route(output_path: str | Path, route: dict[str, object]) -> None:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    noise = route.get("deferred_noise", [])
    lines = [
        "# Priority path route",
        "",
        f"- Lane: `{route['lane']}`",
        f"- Status: `{route['status']}`",
        f"- Next skill: `{route['next_skill']}`",
        f"- Next artifact: `{route['next_artifact']}`",
        "",
        "## Deferred noise",
    ]
    if isinstance(noise, list) and noise:
        lines.extend(f"- {item}" for item in noise)
    else:
        lines.append("- none")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Route a brief to one ShipIt lane.")
    parser.add_argument("brief")
    parser.add_argument("--output", default="")
    args = parser.parse_args(argv)
    route = route_priority(args.brief)
    if args.output:
        write_route(args.output, route)
    else:
        print(route)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
