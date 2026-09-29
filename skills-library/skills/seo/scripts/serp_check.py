#!/usr/bin/env python3
"""SERP rank checks via DataForSEO SERP API (live, organic).

Usage:
  serp_check.py rank --domain example.com --keywords kw1 kw2 ...
  serp_check.py serp --keyword "best running shoes" [--depth 100]
  serp_check.py featured --keyword "what is geo"   # featured snippet / AIO check

Output: JSON to stdout.
"""

from __future__ import annotations

import argparse
import sys

from dataforseo_client import (
    DEFAULT_LANGUAGE,
    DEFAULT_LOCATION,
    call,
    first_result,
    normalize_domain,
    write_json,
)


def _serp_payload(keyword: str, args: argparse.Namespace) -> dict:
    return {
        "keyword": keyword,
        "location_name": args.location,
        "language_code": args.language,
        "device": args.device,
        "os": "windows" if args.device == "desktop" else "ios",
        "depth": args.depth,
    }


def cmd_serp(args: argparse.Namespace) -> None:
    data = call(
        "serp/google/organic/live/advanced",
        _serp_payload(args.keyword, args),
    )
    result = first_result(data)
    write_json(
        {
            "keyword": args.keyword,
            "location": args.location,
            "items": result.get("items") or [],
            "se_results_count": result.get("se_results_count"),
            "spell": result.get("spell"),
        },
        args.out,
    )


def cmd_rank(args: argparse.Namespace) -> None:
    """For each keyword, find the target domain's organic position (1..100)."""
    domain = normalize_domain(args.domain)
    rankings = []
    for kw in args.keywords:
        data = call("serp/google/organic/live/advanced", _serp_payload(kw, args))
        result = first_result(data)
        items = result.get("items") or []
        position = None
        url_found = None
        title_found = None
        for item in items:
            if item.get("type") != "organic":
                continue
            item_domain = normalize_domain(item.get("domain") or "")
            if domain in item_domain or item_domain.endswith(domain):
                position = item.get("rank_absolute") or item.get("rank_group")
                url_found = item.get("url")
                title_found = item.get("title")
                break
        rankings.append({
            "keyword": kw,
            "position": position,
            "url": url_found,
            "title": title_found,
        })
    write_json({"domain": domain, "rankings": rankings}, args.out)


def cmd_featured(args: argparse.Namespace) -> None:
    """Detect featured snippet, AI overview, PAA, and other SERP features."""
    data = call(
        "serp/google/organic/live/advanced",
        _serp_payload(args.keyword, args),
    )
    result = first_result(data)
    items = result.get("items") or []
    features: dict[str, list[dict]] = {}
    for item in items:
        t = item.get("type")
        if t and t != "organic":
            features.setdefault(t, []).append({
                "rank_absolute": item.get("rank_absolute"),
                "title": item.get("title"),
                "domain": item.get("domain"),
                "url": item.get("url"),
            })
    write_json({
        "keyword": args.keyword,
        "item_types_present": result.get("item_types"),
        "features": features,
    }, args.out)


def main() -> None:
    parser = argparse.ArgumentParser(description="DataForSEO SERP checks.")
    parser.add_argument("--location", default=DEFAULT_LOCATION)
    parser.add_argument("--language", default=DEFAULT_LANGUAGE)
    parser.add_argument("--device", default="desktop", choices=["desktop", "mobile"])
    parser.add_argument("--depth", type=int, default=100)
    parser.add_argument("--out", "-o", default="-")

    sub = parser.add_subparsers(dest="cmd", required=True)

    p_serp = sub.add_parser("serp", help="Full organic SERP for a keyword.")
    p_serp.add_argument("--keyword", required=True)
    p_serp.set_defaults(func=cmd_serp)

    p_rank = sub.add_parser("rank", help="Rank check for a domain across keywords.")
    p_rank.add_argument("--domain", required=True)
    p_rank.add_argument("--keywords", nargs="+", required=True)
    p_rank.set_defaults(func=cmd_rank)

    p_feat = sub.add_parser("featured", help="SERP feature breakdown for a keyword.")
    p_feat.add_argument("--keyword", required=True)
    p_feat.set_defaults(func=cmd_featured)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    sys.exit(main() or 0)
