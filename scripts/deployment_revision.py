"""Poll immutable deployment identity before running potentially mutating smoke checks."""
from __future__ import annotations

import json
import re
import time
from collections.abc import Callable


def wait_for_revision(
    fetch: Callable[[], tuple[int, object]],
    expected: str,
    *,
    timeout: float = 180,
    interval: float = 5,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> str:
    """Require a healthy response with the full expected commit; never accept a prefix."""
    if not re.fullmatch(r"[0-9a-fA-F]{40}", expected):
        raise ValueError("expected revision must be a full 40-character git SHA")
    if timeout <= 0 or interval <= 0:
        raise ValueError("deployment timeout and polling interval must be positive")
    expected = expected.lower()
    deadline = monotonic() + timeout
    observed = "not observed"
    while True:
        try:
            status, payload = fetch()
            if isinstance(payload, str):
                payload = json.loads(payload)
            revision = payload.get("revision") if isinstance(payload, dict) else None
            observed = f"HTTP {status}; revision unavailable"
            if isinstance(revision, str) and re.fullmatch(r"[0-9a-fA-F]{40}", revision):
                observed = f"HTTP {status}; revision {revision.lower()}"
                if status == 200 and revision.lower() == expected:
                    return expected
        except (OSError, ValueError):
            # Do not include untrusted response bodies or transport URLs in CI logs.
            observed = "request failed or response was not valid JSON"
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise TimeoutError(f"Deployment did not reach expected revision {expected}: {observed}")
        sleep(min(interval, remaining))


def current_revision(fetch: Callable[[], tuple[int, object]]) -> str | None:
    """One read of /api/revision: the deployed full commit SHA, or None when not observed."""
    try:
        status, payload = fetch()
        if isinstance(payload, str):
            payload = json.loads(payload)
    except (OSError, ValueError):
        return None
    revision = payload.get("revision") if isinstance(payload, dict) else None
    if status == 200 and isinstance(revision, str) and re.fullmatch(r"[0-9a-fA-F]{40}", revision):
        return revision.lower()
    return None


def _http_fetch(url: str) -> Callable[[], tuple[int, object]]:
    import urllib.request

    def fetch() -> tuple[int, object]:
        with urllib.request.urlopen(url, timeout=15) as resp:  # noqa: S310 — https URL from the workflow
            return resp.status, resp.read().decode("utf-8")
    return fetch


def main(argv: list[str] | None = None) -> int:
    """`--current <base-url>` prints the deployed SHA (nothing when unobserved); always exits 0."""
    import sys

    args = sys.argv[1:] if argv is None else argv
    if len(args) != 2 or args[0] != "--current":
        print("usage: deployment_revision.py --current <base-url>", file=sys.stderr)
        return 2
    sha = current_revision(_http_fetch(args[1].rstrip("/") + "/api/revision"))
    if sha:
        print(sha)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
