#!/usr/bin/env python3
"""Backlink analysis via DataForSEO Backlinks API.

Usage:
  backlinks.py summary --target example.com
  backlinks.py top   --target example.com [--limit 100]
  backlinks.py refdomains --target example.com [--limit 100]
  backlinks.py anchors --target example.com [--limit 100]
  backlinks.py compare --targets domain1.com domain2.com domain3.com

Output: JSON to stdout.
"""

from __future__ import annotations

import argparse
import sys

from dataforseo_client import (
    all_items,
    call,
    first_result,
    normalize_domain,
    write_json,
)


def cmd_summary(args: argparse.Namespace) -> None:
    payload = {"target": normalize_domain(args.target), "internal_list_limit": 10}
    data = call("backlinks/summary/live", payload)
    write_json(first_result(data), args.out)


def cmd_top(args: argparse.Namespace) -> None:
    payload = {
        "target": normalize_domain(args.target),
        "limit": args.limit,
        "mode": "as_is",
        "filters": [["dofollow", "=", True]],
        "order_by": ["rank,desc"],
    }
    data = call("backlinks/backlinks/live", payload)
    items = all_items(data)
    write_json({"target": args.target, "count": len(items), "items": items}, args.out)


def cmd_refdomains(args: argparse.Namespace) -> None:
    payload = {
        "target": normalize_domain(args.target),
        "limit": args.limit,
        "order_by": ["rank,desc"],
    }
    data = call("backlinks/referring_domains/live", payload)
    items = all_items(data)
    write_json({"target": args.target, "count": len(items), "items": items}, args.out)


def cmd_anchors(args: argparse.Namespace) -> None:
    payload = {
        "target": normalize_domain(args.target),
        "limit": args.limit,
        "order_by": ["backlinks,desc"],
    }
    data = call("backlinks/anchors/live", payload)
    items = all_items(data)
    write_json({"target": args.target, "count": len(items), "items": items}, args.out)


def cmd_compare(args: argparse.Namespace) -> None:
    summaries = []
    for target in args.targets:
        payload = {"target": normalize_domain(target), "internal_list_limit": 5}
        data = call("backlinks/summary/live", payload)
        summaries.append({"target": target, "summary": first_result(data)})
    write_json({"comparison": summaries}, args.out)


def cmd_intersect(args: argparse.Namespace) -> None:
    """Domains that link to competitors but not to you — backlink gap."""
    payload = {
        "targets": {
            "1": normalize_domain(args.you),
            "2": normalize_domain(args.competitor),
        },
        "exclude_targets": [normalize_domain(args.you)],
        "limit": args.limit,
        "order_by": ["rank,desc"],
    }
    data = call("backlinks/domain_intersection/live", payload)
    items = all_items(data)
    write_json({
        "you": args.you,
        "competitor": args.competitor,
        "gap_count": len(items),
        "items": items,
    }, args.out)


def main() -> None:
    parser = argparse.ArgumentParser(description="DataForSEO Backlinks helper.")
    parser.add_argument("--out", "-o", default="-")

    sub = parser.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("summary"); p1.add_argument("--target", required=True); p1.set_defaults(func=cmd_summary)

    p2 = sub.add_parser("top"); p2.add_argument("--target", required=True)
    p2.add_argument("--limit", type=int, default=100); p2.set_defaults(func=cmd_top)

    p3 = sub.add_parser("refdomains"); p3.add_argument("--target", required=True)
    p3.add_argument("--limit", type=int, default=100); p3.set_defaults(func=cmd_refdomains)

    p4 = sub.add_parser("anchors"); p4.add_argument("--target", required=True)
    p4.add_argument("--limit", type=int, default=100); p4.set_defaults(func=cmd_anchors)

    p5 = sub.add_parser("compare"); p5.add_argument("--targets", nargs="+", required=True)
    p5.set_defaults(func=cmd_compare)

    p6 = sub.add_parser("intersect", help="Backlink gap between you and a competitor.")
    p6.add_argument("--you", required=True)
    p6.add_argument("--competitor", required=True)
    p6.add_argument("--limit", type=int, default=100)
    p6.set_defaults(func=cmd_intersect)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    sys.exit(main() or 0)
