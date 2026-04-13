#!/usr/bin/env python3
"""
scripts/fallback_dryrun.py — Quarterly ANTHROPIC_API_KEY fallback dry-run (RA-634)

Tests that the direct Anthropic Python SDK path is working correctly, independently of
the claude CLI / Claude Max subscription. This is the contingency path that activates
when TAO_USE_FALLBACK=1.

Runs a minimal test prompt via anthropic.Anthropic(), asserts a known sentinel in the
response, and appends a result row to .harness/fallback-dryrun-log.jsonl.

Exit codes:
  0 — fallback path is healthy
  1 — fallback path is broken (creates an Urgent Linear ticket if LINEAR_API_KEY is set)

Usage:
  python scripts/fallback_dryrun.py [--model sonnet] [--dry-run]

Schedule: Quarterly on the 1st of Jan/Apr/Jul/Oct at 17:00 UTC (cron trigger in
.harness/cron-triggers.json, id=fallback-dryrun-quarterly).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# ─── paths ────────────────────────────────────────────────────────────────────

_REPO_ROOT = Path(__file__).parent.parent
_LOG_FILE = _REPO_ROOT / ".harness" / "fallback-dryrun-log.jsonl"
_LINEAR_ENDPOINT = "https://api.linear.app/graphql"
_LINEAR_TEAM_ID = os.environ.get("LINEAR_TEAM_ID", "a8a52f07-63cf-4ece-9ad2-3e3bd3c15673")
_LINEAR_PROJECT_ID = "f45212be-3259-4bfb-89b1-54c122c939a7"

# ─── test prompt ──────────────────────────────────────────────────────────────

_TEST_PROMPT = (
    "This is an automated fallback path verification test for Pi-CEO. "
    "Reply with exactly this string and nothing else: FALLBACK_OK"
)
_EXPECTED_SENTINEL = "FALLBACK_OK"

# ─── helpers ──────────────────────────────────────────────────────────────────


def _write_log(entry: dict) -> None:
    """Append a JSON line to .harness/fallback-dryrun-log.jsonl."""
    _LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def _raise_linear_ticket(error_msg: str, linear_api_key: str) -> str | None:
    """Create an Urgent Linear ticket when the dry-run fails. Returns identifier or None."""
    mutation = """
    mutation CreateIssue($input: IssueCreateInput!) {
        issueCreate(input: $input) { success issue { identifier } }
    }
    """
    variables = {
        "input": {
            "teamId": _LINEAR_TEAM_ID,
            "projectId": _LINEAR_PROJECT_ID,
            "title": "[FALLBACK-DRYRUN] ANTHROPIC_API_KEY direct path FAILED — quarterly test",
            "description": (
                "The quarterly `scripts/fallback_dryrun.py` test failed.\n\n"
                f"**Error:** {error_msg}\n\n"
                "**Action required:**\n"
                "1. Verify `ANTHROPIC_API_KEY` is set and valid in Railway env vars\n"
                "2. Check that the `anthropic` Python package is installed (`anthropic>=0.90`)\n"
                "3. Run `python scripts/fallback_dryrun.py` manually and observe the error\n"
                "4. Fix and re-run until exit code 0 is achieved\n\n"
                "See DEPLOYMENT.md → *Contingency: API Fallback* for full procedures.\n\n"
                "**Risk Register:** R-02 — this is why we test quarterly."
            ),
            "priority": 1,  # Urgent
            "stateId": None,
        }
    }
    payload = json.dumps({"query": mutation, "variables": variables}).encode()
    req = urllib.request.Request(
        _LINEAR_ENDPOINT, data=payload, method="POST",
        headers={"Content-Type": "application/json", "Authorization": linear_api_key},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        return (data.get("data", {}).get("issueCreate", {}).get("issue") or {}).get("identifier")
    except Exception as exc:
        print(f"[WARNING] Could not create Linear ticket: {exc}", file=sys.stderr)
        return None


def run_dryrun(model: str = "claude-sonnet-4-5", dry_run: bool = False) -> bool:
    """
    Execute the fallback path test. Returns True on success, False on failure.

    When dry_run=True: validates configuration but does NOT make an API call.
    """
    ts = datetime.now(timezone.utc).isoformat()
    t0 = time.monotonic()

    # Load env vars (support running from root directory with .env)
    try:
        from dotenv import load_dotenv  # type: ignore
        load_dotenv(_REPO_ROOT / ".env", override=True)
        load_dotenv(_REPO_ROOT / ".env.local", override=True)
    except ImportError:
        pass  # dotenv optional in this script

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        entry = {
            "ts": ts, "success": False, "model": model, "latency_s": None,
            "error": "ANTHROPIC_API_KEY is not set",
            "dry_run": dry_run,
        }
        _write_log(entry)
        print("FAIL — ANTHROPIC_API_KEY is not set", file=sys.stderr)
        return False

    if dry_run:
        print(f"DRY RUN — ANTHROPIC_API_KEY present (len={len(api_key)}), model={model}")
        print("DRY RUN — Skipping actual API call. Configuration looks valid.")
        entry = {
            "ts": ts, "success": True, "model": model, "latency_s": 0.0,
            "error": None, "dry_run": True,
            "note": "config-only check (no API call made)",
        }
        _write_log(entry)
        return True

    # ── Live API call ────────────────────────────────────────────────────────
    try:
        import anthropic  # type: ignore  # anthropic>=0.90 in pyproject.toml
    except ImportError:
        entry = {
            "ts": ts, "success": False, "model": model, "latency_s": None,
            "error": "anthropic package not installed — run: pip install anthropic",
            "dry_run": False,
        }
        _write_log(entry)
        print("FAIL — anthropic package not installed", file=sys.stderr)
        return False

    error_msg: str | None = None
    response_text = ""
    success = False

    try:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model=model,
            max_tokens=32,
            messages=[{"role": "user", "content": _TEST_PROMPT}],
        )
        response_text = message.content[0].text if message.content else ""
        if _EXPECTED_SENTINEL in response_text:
            success = True
        else:
            error_msg = f"Sentinel '{_EXPECTED_SENTINEL}' not found in response: {response_text[:200]!r}"
    except anthropic.AuthenticationError:
        error_msg = "AuthenticationError — ANTHROPIC_API_KEY is invalid or expired"
    except anthropic.RateLimitError:
        error_msg = "RateLimitError — API rate limited (try again in a few minutes)"
    except anthropic.APIConnectionError as exc:
        error_msg = f"APIConnectionError — cannot reach api.anthropic.com: {exc}"
    except Exception as exc:
        error_msg = f"{type(exc).__name__}: {exc}"

    latency_s = round(time.monotonic() - t0, 2)

    entry = {
        "ts": ts,
        "success": success,
        "model": model,
        "latency_s": latency_s,
        "response_preview": response_text[:100] if response_text else None,
        "error": error_msg,
        "dry_run": False,
    }
    _write_log(entry)

    if success:
        print(f"PASS — Fallback path healthy. Model: {model}, latency: {latency_s}s")
        print(f"Response: {response_text.strip()!r}")
        return True
    else:
        print(f"FAIL — {error_msg}", file=sys.stderr)

        # Raise Linear ticket if API key is available
        linear_key = os.environ.get("LINEAR_API_KEY", "")
        if linear_key:
            identifier = _raise_linear_ticket(error_msg or "Unknown error", linear_key)
            if identifier:
                print(f"[INFO] Created Linear ticket: {identifier}")
        return False


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Quarterly ANTHROPIC_API_KEY fallback dry-run (RA-634 / Risk Register R-02)"
    )
    parser.add_argument(
        "--model",
        default="claude-haiku-4-5-20251001",
        help="Model to test against (default: haiku — cheapest). Use claude-haiku-4-5-20251001.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate configuration only — do NOT make an API call (no tokens consumed).",
    )
    args = parser.parse_args()

    ok = run_dryrun(model=args.model, dry_run=args.dry_run)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
