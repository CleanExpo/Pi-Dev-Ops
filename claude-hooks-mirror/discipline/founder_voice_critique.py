"""Founder-voice critique — semantic + structural scanner over a transcript.

Per Pi-CEO Board memo 2026-05-15 (Layer 2 of the four-layer enforcement
loop, NEXT ACTIONS #2). Goes beyond the L3 regex tokens to catch the
broader founder-voice violation patterns Phill identified 2026-05-15:
"asking stupid questions", "so-so efforts", "no top-down control",
question-bouncing, multi-option-without-default, trailing summaries.

This script is the testable artefact the memo demanded:
  "tested against this session's transcript — should flag at least 8
  of the violations from today"

Usage:
    python3 founder_voice_critique.py <transcript.jsonl>
    python3 founder_voice_critique.py --self    # this session
    python3 founder_voice_critique.py --self --json

Stdlib only.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path


# Patterns that mirror L3 regex + semantic extensions
TOKEN_PATTERNS = [
    (re.compile(r"\bwant me to\b", re.I), "want-me-to", "Question-bounce: forbidden token"),
    (re.compile(r"\bshould I\b\??", re.I), "should-i", "Question-bounce: forbidden token"),
    (re.compile(r"\bwould you like me\b", re.I), "would-you-like-me", "Question-bounce: forbidden token"),
    (re.compile(r"\bdo you want me\b", re.I), "do-you-want-me", "Question-bounce: forbidden token"),
    (re.compile(r"\bshall I\b", re.I), "shall-i", "Question-bounce: forbidden token"),
    (re.compile(r"\bplease tell me\b", re.I), "please-tell-me", "Question-bounce: politeness deferral"),
    (re.compile(r"\blet me know if\b", re.I), "let-me-know-if", "Question-bounce: open-ended ask"),
    (re.compile(r"\?\s*$", re.M), "trailing-question", "Sentence ends with question mark instead of decision"),
]


# Semantic / structural patterns
def _detect_structural(text: str) -> list[dict]:
    """Catch patterns the regexes miss: multi-option without default,
    trailing summaries nobody asked for, narration of internal thinking."""
    hits = []

    # Multi-option presentation without an explicit default recommendation
    has_options = bool(re.search(r"^\s*(option\s+[abc]|[123][.)])", text, re.I | re.M))
    has_recommendation = bool(re.search(
        r"(my recommendation|I'll proceed|going with|defaulting to|recommended:|"
        r"\bmy call\b|I'll do|I am doing|I am going)",
        text, re.I))
    if has_options and not has_recommendation:
        hits.append({
            "pattern": "options-without-default",
            "reason": "Multi-option presented to user without explicit default recommendation",
            "snippet": "(structural — see full message)",
        })

    # Trailing summary table when one wasn't asked for
    if re.search(r"^##\s*(summary|status|state|what just (landed|shipped))", text, re.I | re.M):
        if "?" in text[:500]:  # there was a question being answered
            pass  # ok — summarising the answer
        elif len(text) > 1500:
            hits.append({
                "pattern": "unsolicited-summary",
                "reason": "Long trailing summary/status section nobody requested",
                "snippet": "(structural — output > 1500 chars with ## summary heading)",
            })

    # "I can do X" without doing X (deferral language)
    can_do = re.findall(r"I (?:can|could)\s+(?:\w+\s+){0,3}(?:now|today|in \d+ min)", text)
    if len(can_do) >= 2:
        hits.append({
            "pattern": "deferral-language",
            "reason": f"'I can/could do X' phrase used {len(can_do)}× without commitment language ('I am doing', 'I will do now')",
            "snippet": ", ".join(can_do[:3]),
        })

    # Asking permission to update memory/wiki/commit when those should be reflexive
    permission_seeking = re.findall(
        r"\b(should I|do you want me to|want me to)\s+"
        r"(commit|update memory|save to wiki|verify|sync|push|deploy)",
        text, re.I)
    for pm in permission_seeking[:5]:
        hits.append({
            "pattern": "permission-seeking-on-reflexive-action",
            "reason": f"Asking permission for action that should be reflexive: '{pm[0]} {pm[1]}'",
            "snippet": " ".join(pm),
        })

    return hits


def critique(text: str) -> list[dict]:
    hits = []
    for rx, name, reason in TOKEN_PATTERNS:
        for m in rx.finditer(text or ""):
            start = max(0, m.start() - 30)
            end = min(len(text), m.end() + 50)
            hits.append({
                "pattern": name,
                "reason": reason,
                "snippet": text[start:end].replace("\n", " ").strip(),
            })
    hits.extend(_detect_structural(text or ""))
    return hits


def _scan_transcript(path: Path) -> dict:
    if not path.exists():
        return {"error": f"transcript not found: {path}"}
    total_violations = 0
    by_pattern: dict[str, int] = {}
    assistant_turns = 0
    flagged_turns = 0
    per_turn = []
    try:
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if obj.get("type") != "assistant":
                continue
            assistant_turns += 1
            msg = obj.get("message", {})
            text = ""
            for part in msg.get("content", []):
                if part.get("type") == "text":
                    text += part.get("text", "")
            if not text:
                continue
            hits = critique(text)
            if hits:
                flagged_turns += 1
                total_violations += len(hits)
                for h in hits:
                    by_pattern[h["pattern"]] = by_pattern.get(h["pattern"], 0) + 1
                per_turn.append({
                    "turn_index": assistant_turns,
                    "text_len": len(text),
                    "violations": hits[:5],  # cap per turn for output sanity
                    "violation_count": len(hits),
                })
    except OSError as e:
        return {"error": str(e)}
    return {
        "transcript": str(path),
        "assistant_turns": assistant_turns,
        "flagged_turns": flagged_turns,
        "total_violations": total_violations,
        "by_pattern": by_pattern,
        "per_turn": per_turn[-10:],  # last 10 only for output
    }


def _resolve_self_transcript() -> Path | None:
    """Find this session's transcript via env or by scanning the project dir."""
    p = os.environ.get("CLAUDE_TRANSCRIPT_PATH")
    if p and Path(p).exists():
        return Path(p)
    # Fallback: pick most recent .jsonl in the 2nd Brain project dir
    proj = Path.home() / ".claude" / "projects" / "-Users-phill-mac-2nd-Brain"
    if not proj.exists():
        return None
    files = sorted(proj.glob("*.jsonl"), key=lambda f: f.stat().st_mtime, reverse=True)
    return files[0] if files else None


def main(argv: list[str]) -> int:
    as_json = "--json" in argv
    argv = [a for a in argv if a != "--json"]
    if len(argv) < 2:
        print("usage: founder_voice_critique.py <transcript.jsonl> | --self [--json]")
        return 2
    if argv[1] == "--self":
        path = _resolve_self_transcript()
        if not path:
            print("error: could not resolve current session transcript")
            return 1
    else:
        path = Path(argv[1]).expanduser()
    result = _scan_transcript(path)
    if as_json:
        print(json.dumps(result, indent=2))
        return 0
    if "error" in result:
        print(f"ERROR: {result['error']}")
        return 1
    print(f"Transcript:        {result['transcript']}")
    print(f"Assistant turns:   {result['assistant_turns']}")
    print(f"Flagged turns:     {result['flagged_turns']}")
    print(f"Total violations:  {result['total_violations']}")
    print()
    print("By pattern:")
    for k, v in sorted(result['by_pattern'].items(), key=lambda kv: -kv[1]):
        print(f"  {v:4d}  {k}")
    if result['per_turn']:
        print()
        print("Recent flagged turns (last 10):")
        for t in result['per_turn']:
            print(f"  turn {t['turn_index']:4d}  {t['violation_count']:3d} violations  ({t['text_len']} chars)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
