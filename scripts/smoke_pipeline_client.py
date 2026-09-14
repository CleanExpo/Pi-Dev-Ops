"""Cookie-aware HTTP client used by Pipeline Smoke and the golden journey."""
from __future__ import annotations

import http.client
import json
import urllib.error
import urllib.request
from http.cookiejar import CookieJar


class Session:
    def __init__(self, base: str):
        self.base = base
        self.jar = CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
        self.opener = opener

    def login(self, password: str) -> bool:
        data = json.dumps({"password": password}).encode()
        req = urllib.request.Request(
            f"{self.base}/api/login",
            data=data,
            headers={"Content-Type": "application/json"},
        )
        try:
            with self.opener.open(req, timeout=10) as resp:
                return resp.status == 200
        except Exception as exc:
            print(f"[login] failed: {exc}")
            return False

    def post(self, path: str, body: dict) -> tuple[int, str]:
        data = json.dumps(body).encode()
        req = urllib.request.Request(
            f"{self.base}{path}",
            data=data,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with self.opener.open(req, timeout=15) as resp:
                return resp.status, resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode("utf-8", errors="replace")

    def get(self, path: str) -> tuple[int, str]:
        req = urllib.request.Request(f"{self.base}{path}")
        try:
            with self.opener.open(req, timeout=15) as resp:
                return resp.status, resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode("utf-8", errors="replace")
        except Exception as exc:
            return 0, str(exc)

    def stream(self, path: str, timeout_s: int):
        """Yield event dicts from an SSE stream.

        urllib raises ``IncompleteRead`` when a proxy closes a chunked SSE
        body. The already-received bytes live on ``exc.partial`` and are
        otherwise discarded — that is how run 34790637141 lost the planner
        block event (RA-7546). Drain the partial before re-raising.
        """
        req = urllib.request.Request(f"{self.base}{path}")
        buf = ""
        try:
            with self.opener.open(req, timeout=timeout_s) as resp:
                for chunk in iter(lambda: resp.read(4096), b""):
                    buf += chunk.decode("utf-8", errors="replace")
                    events, buf = drain_sse(buf)
                    yield from events
        except http.client.IncompleteRead as exc:
            buf += (exc.partial or b"").decode("utf-8", errors="replace")
            events, _rest = drain_sse(buf)
            yield from events
            raise


def drain_sse(buf: str) -> tuple[list[dict], str]:
    """Split complete SSE events out of ``buf``. Returns (events, remainder)."""
    events: list[dict] = []
    while "\n\n" in buf:
        event_raw, buf = buf.split("\n\n", 1)
        data_lines = [ln[6:] for ln in event_raw.splitlines() if ln.startswith("data: ")]
        if not data_lines:
            continue
        try:
            events.append(json.loads("\n".join(data_lines)))
        except json.JSONDecodeError:
            continue
    return events, buf
