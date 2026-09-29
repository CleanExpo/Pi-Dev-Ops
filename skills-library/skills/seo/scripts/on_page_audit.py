#!/usr/bin/env python3
"""Technical SEO audit via DataForSEO On-Page API.

This uses the *instant_pages* endpoint for single-page audits (synchronous,
returns in seconds) and the full crawl endpoints for multi-page audits.

Usage:
  on_page_audit.py page  --url https://example.com/path
  on_page_audit.py site  --target example.com --max-crawl-pages 100

Output: JSON to stdout.
"""

from __future__ import annotations

import argparse
import sys
import time

from dataforseo_client import (
    DataForSEOError,
    all_items,
    call,
    first_result,
    normalize_domain,
    poll_task,
    write_json,
)


def cmd_page(args: argparse.Namespace) -> None:
    payload = {
        "url": args.url,
        "enable_javascript": True,
        "enable_browser_rendering": True,
        "load_resources": True,
        "custom_user_agent": "Mozilla/5.0 (compatible; DataForSEOBot/1.0)",
    }
    data = call("on_page/instant_pages", payload)
    result = first_result(data)
    items = result.get("items") or []
    page = items[0] if items else {}
    write_json({
        "url": args.url,
        "status_code": page.get("status_code"),
        "page_timing": page.get("page_timing"),
        "meta": page.get("meta"),
        "checks": page.get("checks"),
        "content": {
            "plain_text_word_count": page.get("meta", {}).get("content", {}).get("plain_text_word_count"),
            "plain_text_rate": page.get("meta", {}).get("content", {}).get("plain_text_rate"),
            "automated_readability_index": page.get("meta", {}).get("content", {}).get("automated_readability_index"),
        },
        "resource_errors": page.get("resource_errors"),
        "fetch_time": page.get("fetch_time"),
    }, args.out)


def cmd_site(args: argparse.Namespace) -> None:
    """Kick off a full-site crawl, wait for it, then summarize the issues."""
    target = normalize_domain(args.target)
    start_payload = {
        "target": target,
        "max_crawl_pages": args.max_crawl_pages,
        "load_resources": True,
        "enable_javascript": True,
        "custom_user_agent": "Mozilla/5.0 (compatible; DataForSEOBot/1.0)",
    }
    start = call("on_page/task_post", start_payload)
    task = (start.get("tasks") or [{}])[0]
    task_id = task.get("id")
    if not task_id:
        raise DataForSEOError(f"Failed to start crawl: {start}")

    deadline = time.time() + args.max_wait
    while time.time() < deadline:
        time.sleep(args.poll_interval)
        status = call(f"on_page/tasks_ready", {})
        ready_ids = []
        for r in (status.get("tasks") or [{}])[0].get("result") or []:
            if r.get("id"):
                ready_ids.append(r["id"])
        if task_id in ready_ids:
            break
    else:
        raise DataForSEOError(f"Crawl {task_id} not ready within {args.max_wait}s")

    summary = call(f"on_page/summary/{task_id}", [])
    pages = call(f"on_page/pages", {"id": task_id, "limit": 100})

    write_json({
        "target": target,
        "task_id": task_id,
        "summary": first_result(summary),
        "page_sample": all_items(pages)[:100],
    }, args.out)


def main() -> None:
    parser = argparse.ArgumentParser(description="DataForSEO On-Page audit.")
    parser.add_argument("--out", "-o", default="-")

    sub = parser.add_subparsers(dest="cmd", required=True)

    p_page = sub.add_parser("page", help="Single-page instant audit.")
    p_page.add_argument("--url", required=True)
    p_page.set_defaults(func=cmd_page)

    p_site = sub.add_parser("site", help="Full-site crawl + summary.")
    p_site.add_argument("--target", required=True)
    p_site.add_argument("--max-crawl-pages", type=int, default=100)
    p_site.add_argument("--max-wait", type=int, default=600)
    p_site.add_argument("--poll-interval", type=int, default=15)
    p_site.set_defaults(func=cmd_site)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    sys.exit(main() or 0)
