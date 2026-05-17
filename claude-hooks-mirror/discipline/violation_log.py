"""Stop-hook: scan last assistant turn for discipline violations + log.

Per Pi-CEO Board directive 2026-05-15 (Supabase board_directives id
6298d52f-a1c9-49bb-9180-0c1a48b9cd96). Layer 3+4 of the four-layer
enforcement loop: pattern-detect on emit, log to a JSONL that becomes
the input for Margot's Monday-morning controller-violation-trend
section.

Hooks fire AT message boundaries, so this cannot BLOCK in real-time —
it logs, and the violations get reflected back into the controller's
next turn via the UserPromptSubmit hook (decision_rights_matrix.py).
The feedback loop is async-by-one-turn; that is still sharper than
the read-only-memory baseline that demonstrably fails to change
behaviour.

Stdlib only.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

LOG_PATH = Path.home() / "Pi-CEO" / ".harness" / "swarm" / "controller-violations.jsonl"
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


PATTERNS = [
    (re.compile(r"\bwant me to\b", re.I), "want-me-to"),
    (re.compile(r"\bshould I\b\??", re.I), "should-i"),
    (re.compile(r"\bwould you like me\b", re.I), "would-you-like-me"),
    (re.compile(r"\bdo you want me\b", re.I), "do-you-want-me"),
    (re.compile(r"\bshall I\b", re.I), "shall-i"),
    (re.compile(r"option\s+[abc]\b", re.I), "options-without-default"),
]


def _read_session_input() -> dict:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"_raw": raw[:500]}


def _transcript_path(session: dict) -> Path | None:
    tp = session.get("transcript_path") or os.environ.get("CLAUDE_TRANSCRIPT_PATH")
    if tp:
        p = Path(tp).expanduser()
        if p.exists():
            return p
    return None


def _last_assistant_text(transcript: Path) -> str:
    if not transcript or not transcript.exists():
        return ""
    last = ""
    try:
        for line in transcript.read_text().splitlines():
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if obj.get("type") == "assistant":
                msg = obj.get("message", {})
                for part in msg.get("content", []):
                    if part.get("type") == "text":
                        last = part.get("text", "")
    except OSError:
        return ""
    return last


def _scan(text: str) -> list[dict]:
    hits = []
    for rx, name in PATTERNS:
        for m in rx.finditer(text or ""):
            start = max(0, m.start() - 40)
            end = min(len(text), m.end() + 60)
            hits.append({
                "pattern": name,
                "snippet": text[start:end].replace("\n", " ").strip(),
            })
    # options-without-default: heuristic — if the assistant offered "1. A 2. B 3. C"
    # without "my recommendation" / "I'll proceed with" / "going with"
    if re.search(r"\b(option\s+[abc]|^\s*[123][.)])", text, re.I | re.M):
        if not re.search(r"\b(my recommendation|I'll proceed|going with|defaulting to)\b", text, re.I):
            hits.append({"pattern": "options-without-recommendation", "snippet": "(structural)"})
    return hits


def main() -> int:
    session = _read_session_input()
    tp = _transcript_path(session)
    text = _last_assistant_text(tp) if tp else session.get("last_assistant_text", "")
    if not text:
        return 0
    violations = _scan(text)
    if not violations:
        return 0
    record = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "session_id": session.get("session_id"),
        "transcript": str(tp) if tp else None,
        "violations": violations,
        "text_len": len(text),
    }
    try:
        with LOG_PATH.open("a") as f:
            f.write(json.dumps(record) + "\n")
    except OSError:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
