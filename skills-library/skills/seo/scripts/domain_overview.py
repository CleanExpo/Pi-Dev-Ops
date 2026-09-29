#!/usr/bin/env python3
"""Domain-level competitive intelligence via DataForSEO Labs.

Usage:
  domain_overview.py overview      --target example.com
  domain_overview.py ranked        --target example.com [--limit 100]
  domain_overview.py competitors   --target example.com [--limit 50]
  domain_overview.py intersect     --you you.com --competitor them.com [--limit 100]
  domain_overview.py content_gap   --you you.com --competitors a.com b.com c.com

Output: JSON to stdout.
"""

from __future__ import annotations

import argparse
import sys

from dataforseo_client import (
    DEFAULT_LANGUAGE,
    DEFAULT_LOCATION,
    all_items,
    call,
    first_result,
    normalize_domain,
    write_json,
)


def _loc_lang(args: argparse.Namespace) -> dict:
    return {"location_name": args.location, "language_code": args.language}


def cmd_overview(args: argparse.Namespace) -> None:
    payload = {"target": normalize_domain(args.target), **_loc_lang(args)}
    data = call("dataforseo_labs/google/domain_rank_overview/live", payload)
    write_json(first_result(data), args.out)


def cmd_ranked(args: argparse.Namespace) -> None:
    payload = {
        "target": normalize_domain(args.target),
        "limit": args.limit,
        "order_by": ["keyword_data.keyword_info.search_volume,desc"],
        **_loc_lang(args),
    }
    data = call("dataforseo_labs/google/ranked_keywords/live", payload)
    write_json({"target": args.target, "items": all_items(data)}, args.out)


def cmd_competitors(args: argparse.Namespace) -> None:
    payload = {
        "target": normalize_domain(args.target),
        "limit": args.limit,
        **_loc_lang(args),
    }
    data = call("dataforseo_labs/google/competitors_domain/live", payload)
    write_json({"target": args.target, "items": all_items(data)}, args.out)


def cmd_intersect(args: argparse.Namespace) -> None:
    """Keywords where BOTH domains rank (head-to-head intersection)."""
    payload = {
        "target1": normalize_domain(args.you),
        "target2": normalize_domain(args.competitor),
        "intersections": True,
        "limit": args.limit,
        **_loc_lang(args),
    }
    data = call("dataforseo_labs/google/domain_intersection/live", payload)
    write_json({
        "you": args.you,
        "competitor": args.competitor,
        "items": all_items(data),
    }, args.out)


def cmd_content_gap(args: argparse.Namespace) -> None:
    """Keywords competitors rank for that you don't — content gap."""
    you = normalize_domain(args.you)
    items_by_competitor = {}
    for comp in args.competitors:
        payload = {
            "target1": normalize_domain(comp),
            "target2": you,
            "intersections": False,
            "limit": args.limit,
            "order_by": ["first_domain_serp_element.keyword_data.keyword_info.search_volume,desc"],
            **_loc_lang(args),
        }
        data = call("dataforseo_labs/google/domain_intersection/live", payload)
        items_by_competitor[comp] = all_items(data)
    write_json({"you": args.you, "gaps": items_by_competitor}, args.out)


def main() -> None:
    parser = argparse.ArgumentParser(description="DataForSEO domain analytics.")
    parser.add_argument("--location", default=DEFAULT_LOCATION)
    parser.add_argument("--language", default=DEFAULT_LANGUAGE)
    parser.add_argument("--out", "-o", default="-")

    sub = parser.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("overview"); p1.add_argument("--target", required=True); p1.set_defaults(func=cmd_overview)

    p2 = sub.add_parser("ranked"); p2.add_argument("--target", required=True)
    p2.add_argument("--limit", type=int, default=100); p2.set_defaults(func=cmd_ranked)

    p3 = sub.add_parser("competitors"); p3.add_argument("--target", required=True)
    p3.add_argument("--limit", type=int, default=50); p3.set_defaults(func=cmd_competitors)

    p4 = sub.add_parser("intersect"); p4.add_argument("--you", required=True)
    p4.add_argument("--competitor", required=True); p4.add_argument("--limit", type=int, default=100)
    p4.set_defaults(func=cmd_intersect)

    p5 = sub.add_parser("content_gap"); p5.add_argument("--you", required=True)
    p5.add_argument("--competitors", nargs="+", required=True)
    p5.add_argument("--limit", type=int, default=100)
    p5.set_defaults(func=cmd_content_gap)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    sys.exit(main() or 0)
