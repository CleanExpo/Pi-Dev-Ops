#!/usr/bin/env python3
"""Keyword research via DataForSEO Keywords Data + Labs APIs.

Usage:
  keyword_research.py seed "<seed keyword>" [--location "United States"] [--language en]
  keyword_research.py related "<seed keyword>" [--depth 1] [--limit 200]
  keyword_research.py suggestions "<seed keyword>" [--limit 200]
  keyword_research.py volume kw1 kw2 kw3 ...

Output: JSON to stdout. Claude reads this and produces analysis.
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
    write_json,
)


def cmd_seed(args: argparse.Namespace) -> None:
    """Pull search volume + CPC + competition for a single seed keyword."""
    payload = {
        "keywords": [args.keyword],
        "location_name": args.location,
        "language_code": args.language,
    }
    data = call("keywords_data/google_ads/search_volume/live", payload)
    items = all_items(data)
    write_json({"keyword": args.keyword, "metrics": items}, args.out)


def cmd_related(args: argparse.Namespace) -> None:
    """Related keywords with full SEO metrics."""
    payload = {
        "keyword": args.keyword,
        "location_name": args.location,
        "language_code": args.language,
        "depth": args.depth,
        "limit": args.limit,
        "include_seed_keyword": True,
    }
    data = call("dataforseo_labs/google/related_keywords/live", payload)
    write_json({"seed": args.keyword, "items": all_items(data)}, args.out)


def cmd_suggestions(args: argparse.Namespace) -> None:
    """Long-tail suggestions ranked by search volume."""
    payload = {
        "keyword": args.keyword,
        "location_name": args.location,
        "language_code": args.language,
        "limit": args.limit,
        "include_serp_info": False,
        "order_by": ["keyword_info.search_volume,desc"],
    }
    data = call("dataforseo_labs/google/keyword_suggestions/live", payload)
    write_json({"seed": args.keyword, "items": all_items(data)}, args.out)


def cmd_volume(args: argparse.Namespace) -> None:
    """Bulk volume + CPC for an arbitrary list of keywords."""
    payload = {
        "keywords": args.keywords,
        "location_name": args.location,
        "language_code": args.language,
    }
    data = call("keywords_data/google_ads/search_volume/live", payload)
    write_json({"items": all_items(data)}, args.out)


def cmd_difficulty(args: argparse.Namespace) -> None:
    payload = {
        "keywords": args.keywords,
        "location_name": args.location,
        "language_code": args.language,
    }
    data = call("dataforseo_labs/google/bulk_keyword_difficulty/live", payload)
    write_json({"items": all_items(data)}, args.out)


def main() -> None:
    parser = argparse.ArgumentParser(description="DataForSEO keyword research.")
    parser.add_argument("--location", default=DEFAULT_LOCATION)
    parser.add_argument("--language", default=DEFAULT_LANGUAGE)
    parser.add_argument("--out", "-o", default="-", help="Output file (default stdout).")

    sub = parser.add_subparsers(dest="cmd", required=True)

    p_seed = sub.add_parser("seed", help="Volume/CPC for a single keyword.")
    p_seed.add_argument("keyword")
    p_seed.set_defaults(func=cmd_seed)

    p_related = sub.add_parser("related", help="Related keywords with metrics.")
    p_related.add_argument("keyword")
    p_related.add_argument("--depth", type=int, default=1, choices=[0, 1, 2, 3, 4])
    p_related.add_argument("--limit", type=int, default=200)
    p_related.set_defaults(func=cmd_related)

    p_sugg = sub.add_parser("suggestions", help="Long-tail suggestions.")
    p_sugg.add_argument("keyword")
    p_sugg.add_argument("--limit", type=int, default=200)
    p_sugg.set_defaults(func=cmd_suggestions)

    p_vol = sub.add_parser("volume", help="Bulk search volume + CPC.")
    p_vol.add_argument("keywords", nargs="+")
    p_vol.set_defaults(func=cmd_volume)

    p_diff = sub.add_parser("difficulty", help="Bulk keyword difficulty.")
    p_diff.add_argument("keywords", nargs="+")
    p_diff.set_defaults(func=cmd_difficulty)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    sys.exit(main() or 0)
