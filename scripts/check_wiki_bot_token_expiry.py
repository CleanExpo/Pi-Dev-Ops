#!/usr/bin/env python3
"""RA-6905 — surface WIKI_BOT_TOKEN expiry before a protected-branch push fails silently.

Reads WIKI_BOT_TOKEN_EXPIRES_AT (ISO date YYYY-MM-DD). When unset, emits a workflow
warning reminding operators to set it. When expired or within warn_days, exits non-zero
so CI surfaces rotation before the bot push step.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime, timezone


def parse_expiry(raw: str) -> date:
    text = raw.strip()
    if not text:
        raise ValueError("empty expiry")
    if "T" in text:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    return date.fromisoformat(text)


def check_expiry(
    expires_at: str | None,
    *,
    today: date | None = None,
    warn_days: int = 14,
) -> tuple[int, list[str]]:
    """Return (exit_code, log_lines). 0 = ok, 1 = warn soon, 2 = expired/missing policy."""
    lines: list[str] = []
    now = today or datetime.now(timezone.utc).date()

    if not expires_at or not expires_at.strip():
        lines.append(
            "::warning::WIKI_BOT_TOKEN_EXPIRES_AT is unset — set a repo secret "
            "(ISO date, ≤30-day PAT rotation policy per RA-6905) so stale-token "
            "failures surface before the wiki push step."
        )
        return 0, lines

    try:
        expiry = parse_expiry(expires_at)
    except ValueError as exc:
        lines.append(
            f"::error::WIKI_BOT_TOKEN_EXPIRES_AT invalid ({exc!s}) — use YYYY-MM-DD"
        )
        return 2, lines

    days_left = (expiry - now).days
    lines.append(f"WIKI_BOT_TOKEN expires {expiry.isoformat()} ({days_left} day(s) remaining)")

    if days_left < 0:
        lines.append(
            "::error::WIKI_BOT_TOKEN is expired — rotate the fine-grained PAT, update "
            "secrets.WIKI_BOT_TOKEN + WIKI_BOT_TOKEN_EXPIRES_AT, then re-run."
        )
        return 2, lines

    if days_left <= warn_days:
        lines.append(
            f"::warning::WIKI_BOT_TOKEN expires in {days_left} day(s) — rotate before expiry "
            f"(RA-6905 ≤30-day policy)."
        )
        return 1, lines

    lines.append("WIKI_BOT_TOKEN expiry check passed.")
    return 0, lines


def main() -> int:
    parser = argparse.ArgumentParser(description="Check WIKI_BOT_TOKEN expiry secret")
    parser.add_argument(
        "--expires-at",
        default=os.environ.get("WIKI_BOT_TOKEN_EXPIRES_AT", ""),
        help="ISO expiry date (default: env WIKI_BOT_TOKEN_EXPIRES_AT)",
    )
    parser.add_argument(
        "--warn-days",
        type=int,
        default=int(os.environ.get("WIKI_BOT_TOKEN_WARN_DAYS", "14")),
    )
    parser.add_argument(
        "--fail-on-warn",
        action="store_true",
        help="Exit 1 when within warn window (default: warn only)",
    )
    args = parser.parse_args()

    code, lines = check_expiry(args.expires_at, warn_days=args.warn_days)
    for line in lines:
        print(line)

    if code == 1 and not args.fail_on_warn:
        return 0
    return code


if __name__ == "__main__":
    sys.exit(main())
