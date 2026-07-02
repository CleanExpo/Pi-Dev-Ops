#!/usr/bin/env python3
"""Snapshot the autonomy queue for daily plan-discovery cron.

Writes `.harness/plan-discovery-backlog/YYYY-MM-DD.json` with ticket
metadata (no secrets). Exit 0 even when the queue is empty.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.server import config  # noqa: E402
from app.server.autonomy import fetch_todo_issues  # noqa: E402

OUT_DIR = REPO_ROOT / ".harness" / "plan-discovery-backlog"


def _issue_row(issue: dict) -> dict[str, Any]:
    return {
        "identifier": issue.get("identifier"),
        "title": issue.get("title"),
        "priority": issue.get("priority"),
        "project": issue.get("_project_name"),
        "repo_url": issue.get("_repo_url"),
        "url": issue.get("url"),
        "description_excerpt": (issue.get("description") or "")[:2000],
    }


def run(*, emit_json: bool) -> dict[str, Any]:
    api_key = config.LINEAR_API_KEY
    if not api_key:
        return {"ok": False, "error": "LINEAR_API_KEY not set", "queue_depth": 0}

    issues = fetch_todo_issues(api_key)
    today = dt.date.today().isoformat()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"{today}.json"

    payload: dict[str, Any] = {
        "ok": True,
        "date": today,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "queue_depth": len(issues),
        "issues": [_issue_row(i) for i in issues],
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    payload["path"] = str(path)
    if emit_json:
        print(json.dumps(payload))
    else:
        print(f"plan_discovery_backlog: {len(issues)} issues → {path}")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Snapshot autonomy queue for plan discovery.")
    parser.add_argument("--json", action="store_true", help="Print summary JSON to stdout.")
    args = parser.parse_args(argv)
    result = run(emit_json=args.json)
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
