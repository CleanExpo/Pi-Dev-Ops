"""Jev transport with hard budget, deadline, redaction and strict response checks (PLAN.md rev 5).

`post(body, timeout)` is injected: it returns (status, parsed_json_or_None, retry_after_seconds_or_None).
Every failure path returns `signal_unavailable` (or `budget_exhausted`); nothing is ever inferred.
"""
from __future__ import annotations

import json
import re
import threading
import time
import urllib.request

from jev_platform import policy

MAX_REQUEST_BYTES = 64_000
RESERVE_TOKENS = 64_000  # documented per-request limit (docs/vendor/typesafe/llms-full.txt:13008)
USD_PER_TOKEN = 0.042 / 1_000_000
RESERVE_USD = RESERVE_TOKENS * USD_PER_TOKEN
MAX_RETRIES = 2
REQUEST_TIMEOUT = 30.0
REDACTION_VERSION = "redact-1"
# Edges are "not an ASCII letter or digit", never \b: \b is Unicode-aware and counts "_" as a word
# character, so _sk-..._ or a key touching a CJK letter had no boundary (round 23).
_EDGE, _END = r"(?<![A-Za-z0-9])", r"(?![A-Za-z0-9])"
# Rounds 28-29: a logged key hides behind the letters of a written-out escape (\n, \x1b, \u000a, \033, repr()).
# Every escape is replaced by a space and the result screened too; the raw text is screened as well, because a
# key straight after a lone backslash (C:\sk-...) would lose its first letter to the replacement.
_ESCAPE = re.compile(r"\\(?:x[0-9A-Fa-f]{2}|u[0-9A-Fa-f]{4}|U[0-9A-Fa-f]{8}|N\{[^}]*\}|[0-7]{1,3}|.)", re.S)


# Round 30: a nested log doubles its backslashes (\\\\n), so runs collapse to one first; terminal colour codes
# (ESC[31m, real or written out) end in a letter that would touch the key, so they are removed too.
_BACKSLASHES = re.compile(r"\\{2,}")
_ANSI = re.compile(r"(?:\x1b|\x9b|(?<= ))\[[0-9;?]*[ -/]*[@-~]")


def screened(text: str) -> tuple[str, str]:
    """The raw text and its escape-free reading; a screen refuses if either matches."""
    return text, _ANSI.sub(" ", _ESCAPE.sub(" ", _BACKSLASHES.sub("\\\\", text)))
_API_KEYS = re.compile(_EDGE + r"(?:sk-|ts-|ghp_)[\w-]{8,}")
_PATTERNS = [
    re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),
    re.compile(r"\+?\d[\d ()-]{7,}\d"),
    re.compile(r"\d{12,}"),
    _API_KEYS,
    re.compile(_EDGE + r"[0-9a-fA-F]{32,}" + _END),
    re.compile(r"https?://\S*\?\S*"),
]

# Round 22: key material only. The PII patterns above also match dates, so they are not part of this set.
CREDENTIALS = [re.compile(p, re.I | re.ASCII) for p in (  # ASCII: re.I alone folds K-sign, dotted I, long s
    r"-----BEGIN [A-Z ]*(PRIVATE KEY|CERTIFICATE)", _EDGE + r"AKIA[0-9A-Z]{16}" + _END,
    _EDGE + r"eyJ[\w-]{10,}\.[\w-]{10,}\.", _EDGE + r"(sk|rk)_live_\w{8,}", _EDGE + r"xox[bpas]-[\w-]{8,}")] \
    + [_API_KEYS]


def credential(text: str) -> bool:
    return any(p.search(t) for t in screened(text) for p in CREDENTIALS)


def credential_payload(obj) -> bool:
    """Every decoded string key and value of an outbound body, so no escaping can hide a key (round 20's lesson)."""
    if isinstance(obj, str):
        return credential(obj)
    if isinstance(obj, dict):
        return any(credential_payload(k) or credential_payload(v) for k, v in obj.items())
    if isinstance(obj, (list, tuple)):
        return any(credential_payload(v) for v in obj)
    return False


def _no_duplicates(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            raise json.JSONDecodeError(f"duplicate key {k!r}", "", 0)  # malformed, to every caller
        out[k] = v
    return out


def strict_json(raw):
    """Round 26-27: json.loads keeps the LAST of two equal keys, so q=0.01 then q=0.99 read as a pass. Any
    duplicate key raises json.JSONDecodeError instead. Every JSON parse in jev_platform/ and
    evals/jev_constitution/ goes through here (except private json.dumps round-trip snapshots)."""
    return json.loads(raw, object_pairs_hook=_no_duplicates)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # answered as the HTTPError it is


def open_url(req: urllib.request.Request, timeout: float):
    """Round 16: every live transport sends a credential, so none follows a redirect; one could carry it elsewhere."""
    return urllib.request.build_opener(_NoRedirect).open(req, timeout=timeout)


def redact(text: str) -> tuple[str, bool]:
    out = text
    for pat in _PATTERNS:
        out = pat.sub("[redacted]", out)
    return out, out != text


class Budget:
    """Reserve the documented worst case before every attempt; settle down only on reported usage."""

    def __init__(self, max_usd: float, max_seconds: float, clock=time.monotonic):
        self.max_usd, self.clock = max_usd, clock
        self.deadline = clock() + max_seconds
        self.spent, self.attempts = 0.0, 0
        # Fixed at start: settling a cheap answer down never buys extra attempts.
        self.max_attempts = int((max_usd + 1e-12) // RESERVE_USD)
        self._lock = threading.Lock()

    def remaining_seconds(self) -> float:
        return self.deadline - self.clock()

    def reserve(self) -> bool:
        with self._lock:
            if (self.attempts >= self.max_attempts or self.spent + RESERVE_USD > self.max_usd + 1e-12
                    or self.remaining_seconds() <= 0):
                return False
            self.spent += RESERVE_USD
            self.attempts += 1
            return True

    def settle(self, data) -> None:
        usage = (data or {}).get("usage") if isinstance(data, dict) else None
        tokens = usage.get("input_tokens") if isinstance(usage, dict) else None
        if isinstance(tokens, int) and not isinstance(tokens, bool) and 0 <= tokens <= RESERVE_TOKENS:
            with self._lock:
                self.spent -= RESERVE_USD - tokens * USD_PER_TOKEN


def build_request(state: str, rules: list[dict], model: str = "jev-latest") -> dict:
    return {"state": state, "model": model, "questions": {
        r["id"]: {"type": "noul", "instructions": r["question"],
                  "criteria": {"true": r["criteria_true"], "false": r["criteria_false"]}} for r in rules}}


def validate(data, rule_ids: list[str]) -> dict | None:
    """Every requested id answered exactly, as a finite Noul in [0, 1]; else None."""
    if not isinstance(data, dict) or not isinstance(data.get("answers"), dict):
        return None
    answers = data["answers"]
    if set(answers) != set(rule_ids):
        return None
    out = {}
    for rid in rule_ids:
        a = answers[rid]
        if not isinstance(a, dict) or a.get("type") != "noul" or not policy.valid_noul(a.get("noul")):
            return None
        out[rid] = float(a["noul"])
    return out


def send(body: dict, post, budget: Budget, sleep=time.sleep) -> dict:
    """{'data': json} on HTTP 200, else {'error': reason}. Budget reserved before every attempt."""
    body = json.loads(json.dumps(body))  # round 25: screen and send one private snapshot, never the caller's dict
    if credential_payload(body):  # round 22: no key material leaves through any Jev transport
        return {"error": "credential_in_request"}
    if len(json.dumps(body).encode()) > MAX_REQUEST_BYTES:
        return {"error": "request_too_large"}
    for attempt in range(MAX_RETRIES + 1):
        if not budget.reserve():
            return {"error": "budget_exhausted"}
        try:
            status, data, retry_after = post(body, min(REQUEST_TIMEOUT, budget.remaining_seconds()))
        except Exception:  # noqa: BLE001 — any transport failure is signal_unavailable, never a pass
            return {"error": "signal_unavailable:transport"}
        if status == 200:
            budget.settle(data)
            return {"data": data}
        wait = retry_after if isinstance(retry_after, (int, float)) else None
        if status != 429 or attempt == MAX_RETRIES or wait is None or wait >= budget.remaining_seconds():
            return {"error": f"signal_unavailable:http_{status}"}
        sleep(wait)
    return {"error": "signal_unavailable:retries"}


def ask(state: str, rules: list[dict], post, budget: Budget, sleep=time.sleep) -> dict:
    """{'nouls': {...}, 'model': str} or {'error': reason}. Redaction happens before sending."""
    sent = send(build_request(state, rules), post, budget, sleep)
    if "error" in sent:
        return sent
    nouls = validate(sent["data"], [r["id"] for r in rules])
    if nouls is None:
        return {"error": "signal_unavailable:invalid_response"}
    return {"nouls": nouls, "model": str(sent["data"].get("model", "unknown"))}
