"""Gemini transport with a prepaid, provider-counted reservation (PLAN-scale.md rev 5).

Before every generateContent attempt the IDENTICAL request bytes go to countTokens as
`generateContentRequest`; its `totalTokens` is the input reservation, and output (thinking included)
is hard-bounded by maxOutputTokens. Reservation = totalTokens x in + 2048 x out, taken under a lock.
Reported usageMetadata settles down; missing usage, a timeout or a 5xx keeps the full reservation.
`http_post(url, payload_bytes, headers, timeout)` is injected and returns (status, parsed_json_or_None).
The key travels only in the `x-goog-api-key` header and is never logged or returned.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import threading
import time
import urllib.error
import urllib.request

from jev_platform import ask

MODEL = "gemini-3.8-flash"
BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models/"
GENERATE_URL = f"{BASE_URL}{MODEL}:generateContent"
COUNT_URL = f"{BASE_URL}{MODEL}:countTokens"
# ai.google.dev/gemini-api/docs/pricing, fetched 29/09/2026; countTokens is documented as free.
PRICES = {MODEL: {"in": 0.75e-6, "out": 3.75e-6, "count": 0.0, "valid_until": "2026-12-31"}}
MAX_OUTPUT_TOKENS = 2048
THINKING_LEVEL = "low"
TURN_CAP = 12
COUNT_CAP = 2 * TURN_CAP
MAX_RETRIES = 2
RETRY_STATUSES = (429, 503)
RUN_CAP_USD = 0.10
WRITER_CAP_USD = 1.00
REQUEST_TIMEOUT = 60.0
KEY_ROUTE = "cd ~/Pi-Dev-Ops/dashboard && vercel env run -e production -- <command>"


def api_key() -> str:
    return os.environ.get("GEMINI_API_KEY", "").strip()


def today() -> dt.date:
    return dt.date.today()


def price_table(on: dt.date, model: str = MODEL) -> dict | None:
    """The price row for `model`, or None once it has expired (then nothing may be sent)."""
    p = PRICES.get(model)
    if p is None or on > dt.date.fromisoformat(p["valid_until"]):
        return None
    return dict(p)


class GeminiBudget:
    """A lock plus a fixed attempt cap, as client.Budget; count calls are capped per batch."""

    def __init__(self, max_usd: float, price: dict, max_count_calls: int = COUNT_CAP):
        self.max_usd, self.price, self.max_count_calls = max_usd, price, max_count_calls
        self.spent = self.count_usd = 0.0
        self.attempts = self.count_calls = self.count_ok = self.batch_count_calls = 0
        self.tokens = {"counted": 0, "reserved_in": 0, "reserved_out": 0, "reported_prompt": 0, "reported_output": 0}
        # Fixed at start: settling a cheap reply down never buys extra attempts.
        self.max_attempts = int((max_usd + 1e-12) // (MAX_OUTPUT_TOKENS * price["out"]))
        self._lock = threading.Lock()

    def start_batch(self) -> None:
        with self._lock:
            self.batch_count_calls = 0

    def reserve_count(self, nbytes: int) -> str | None:
        """None when a count call may be made; else the refusal. Reserved before the call is made."""
        with self._lock:
            if self.batch_count_calls >= self.max_count_calls:
                return "count cap"
            cost = nbytes * self.price["count"]
            if self.spent + cost > self.max_usd + 1e-12:
                return "cap: count reservation over the cap"
            self.spent, self.count_usd = self.spent + cost, self.count_usd + cost
            self.count_calls, self.batch_count_calls = self.count_calls + 1, self.batch_count_calls + 1
            return None

    def count_succeeded(self, total: int) -> None:
        with self._lock:
            self.count_ok += 1
            self.tokens["counted"] += total

    def reserve_generate(self, counted: int) -> float | None:
        cost = counted * self.price["in"] + MAX_OUTPUT_TOKENS * self.price["out"]
        with self._lock:
            if self.attempts >= self.max_attempts or self.spent + cost > self.max_usd + 1e-12:
                return None
            self.spent, self.attempts = self.spent + cost, self.attempts + 1
            self.tokens["reserved_in"] += counted
            self.tokens["reserved_out"] += MAX_OUTPUT_TOKENS
            return cost

    def settle(self, reserved: float, usage, counted: int) -> None:
        """Reported usage settles the spend down; missing usage keeps the full reservation.

        On an overrun (reported prompt above the counted total) the larger of the two figures is kept."""
        prompt, output = _usage(usage)
        if prompt is None:
            return
        actual = prompt * self.price["in"] + output * self.price["out"]
        with self._lock:
            self.tokens["reported_prompt"] += prompt
            self.tokens["reported_output"] += output
            self.spent += max(actual, reserved) - reserved if prompt > counted else actual - reserved

    def snapshot(self) -> dict:
        with self._lock:
            return {"attempts": self.attempts, "count_calls": self.count_calls, "count_ok": self.count_ok,
                    "count_reserved_usd": round(self.count_usd, 6), "tokens": dict(self.tokens),
                    "spent_usd": round(self.spent, 6)}


def _usage(usage) -> tuple[int | None, int]:
    if not isinstance(usage, dict):
        return None, 0
    prompt, cands, thoughts = (usage.get(k) for k in ("promptTokenCount", "candidatesTokenCount", "thoughtsTokenCount"))
    ok = all(isinstance(v, int) and not isinstance(v, bool) and v >= 0 for v in (prompt, cands))
    thoughts = thoughts if isinstance(thoughts, int) and not isinstance(thoughts, bool) and thoughts >= 0 else 0
    return (prompt, cands + thoughts) if ok else (None, 0)


def request_body(contents: list, system: str | None = None, tools: list | None = None,
                 max_output_tokens: int = MAX_OUTPUT_TOKENS) -> dict:
    """One dict serves both calls; `model` is required inside countTokens' generateContentRequest."""
    body = {"model": f"models/{MODEL}", "contents": contents,
            "generationConfig": {"maxOutputTokens": max_output_tokens,
                                 "thinkingConfig": {"thinkingLevel": THINKING_LEVEL}}}
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    if tools:
        body["tools"] = tools
    return body


def _post(http_post, url: str, payload: bytes, headers: dict) -> tuple[int | None, object]:
    try:
        return http_post(url, payload, headers, REQUEST_TIMEOUT)
    except Exception:  # noqa: BLE001 — any transport failure is a failed attempt, never a pass
        return None, None


def _count(payload: bytes, headers: dict, budget: GeminiBudget, http_post) -> tuple[int | None, str | None, bool]:
    """(totalTokens, problem, retryable). The count body wraps the exact generateContent bytes."""
    refusal = budget.reserve_count(len(payload))
    if refusal:
        return None, refusal, False
    status, data = _post(http_post, COUNT_URL, b'{"generateContentRequest": ' + payload + b"}", headers)
    if status != 200:
        return None, f"countTokens {'http_' + str(status) if status else 'transport failure'}", status in RETRY_STATUSES
    total = data.get("totalTokens") if isinstance(data, dict) else None
    if not isinstance(total, int) or isinstance(total, bool) or total < 0:
        return None, "countTokens malformed", False
    budget.count_succeeded(total)
    return total, None, False


def _settled(data, reserved: float, counted: int, budget: GeminiBudget) -> dict:
    usage = data.get("usageMetadata") if isinstance(data, dict) else None
    budget.settle(reserved, usage, counted)
    prompt = usage.get("promptTokenCount") if isinstance(usage, dict) else None
    if isinstance(prompt, int) and prompt > counted:
        return {"error": "overrun", "counted": counted}
    return {"data": data, "counted": counted}


def call(body: dict, key: str, budget: GeminiBudget, http_post, sleep=time.sleep) -> dict:
    """{'data': reply, 'counted': n} or {'error': reason}. Count, reserve, send; 429/503 retried at most twice."""
    payload = json.dumps(body).encode()
    if ask.sensitive(payload.decode()):
        return {"error": "refused: sensitive payload"}
    headers = {"x-goog-api-key": key, "Content-Type": "application/json"}
    for attempt in range(MAX_RETRIES + 1):
        counted, problem, retry = _count(payload, headers, budget, http_post)
        if problem:
            if retry and attempt < MAX_RETRIES:
                sleep(2.0 * (attempt + 1))
                continue
            return {"error": problem}
        reserved = budget.reserve_generate(counted)
        if reserved is None:
            return {"error": "cap: reservation over the run cap"}
        status, data = _post(http_post, GENERATE_URL, payload, headers)
        if status == 200:
            return _settled(data, reserved, counted, budget)
        if status in RETRY_STATUSES and attempt < MAX_RETRIES:
            sleep(2.0 * (attempt + 1))
            continue
        return {"error": f"gemini {'http_' + str(status) if status else 'transport failure'}"}
    return {"error": "retries exhausted"}


def urllib_post(url: str, payload: bytes, headers: dict, timeout: float) -> tuple[int, object]:
    """The live transport. Error bodies are never read, so none can be logged or shown."""
    req = urllib.request.Request(url, data=payload, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, None
