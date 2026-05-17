"""Calibration corpus miner — auto-label PASS/FAIL from Phill's natural
corrections in existing session transcripts.

Per Pi-CEO Board memo 2026-05-15 (Layer 6 / NEXT ACTIONS #2). Mines
~/.claude/projects/-Users-phill-mac-2nd-Brain/*.jsonl for cases where
Phill expressed dissatisfaction in the next 3 user turns following an
assistant emit. The preceding emit is auto-labelled:

  FAIL = Phill corrected, expressed frustration, or directly rewrote
         within next 3 user turns
  PASS = no correction signal in next 3 user turns

Outputs to ~/Pi-CEO/.harness/swarm/calibration-corpus.jsonl. Used by
the weekly reviewer-weight recalibration cron to compute per-reviewer
Spearman correlation vs auto-labels (finding Q5: regression
calibration halves residual TNR error).

Stdlib only. Default-safe: skip malformed lines, never crash.

Usage:
    python3 calibration_corpus_miner.py [--limit N] [--rebuild]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

TRANSCRIPT_DIR = Path.home() / ".claude" / "projects" / "-Users-phill-mac-2nd-Brain"
OUTPUT_PATH = Path.home() / "Pi-CEO" / ".harness" / "swarm" / "calibration-corpus.jsonl"
WINDOW_TURNS = 3
MIN_EMIT_LEN = 200  # ignore trivial emits

CORRECTION_PATTERNS = [
    (re.compile(r"\b(rediculous|ridiculous|stupid|wrong|incorrect|nope)\b", re.I), "explicit-frustration"),
    (re.compile(r"\b(thats? not|that is not|that's wrong|that's incorrect|you got it wrong|that won't work)\b", re.I), "direct-contradiction"),
    (re.compile(r"\b(no,? that's|actually,?|no — |no, )\b", re.I), "corrective-pivot"),
    (re.compile(r"\b(stop asking|stop doing|please stop|enough)\b", re.I), "behavioural-correction"),
    (re.compile(r"\b(so[- ]?so|sub[- ]?par|low quality|poor quality|not (good|great|enough))\b", re.I), "quality-complaint"),
    (re.compile(r"\b(I am getting tired|I'm tired|frustrat(ed|ing)|annoying)\b", re.I), "fatigue-signal"),
    (re.compile(r"\bquan?ity\b", re.I), "quality-misspelled"),  # Phill's "quanity" typo when frustrated
]


def _classify_user_msg(text: str) -> list[str]:
    hits = []
    for rx, label in CORRECTION_PATTERNS:
        if rx.search(text or ""):
            hits.append(label)
    return hits


def _extract_text(msg: dict) -> str:
    """Pull plain-text content out of either a user or assistant message."""
    content = msg.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        out = []
        for part in content:
            if not isinstance(part, dict):
                continue
            if part.get("type") == "text":
                out.append(part.get("text", ""))
        return "\n".join(out)
    return ""


def mine_transcript(path: Path) -> list[dict]:
    """Walk one transcript, emitting (assistant_emit, label, reason) per
    qualifying assistant turn."""
    out: list[dict] = []
    turns: list[dict] = []
    try:
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if obj.get("type") in ("user", "assistant"):
                msg = obj.get("message", {})
                turns.append({
                    "type": obj["type"],
                    "ts": obj.get("timestamp") or obj.get("ts") or "",
                    "text": _extract_text(msg),
                })
    except OSError as e:
        print(f"skip {path.name}: {e}", file=sys.stderr)
        return out

    # Walk turns: for each assistant turn, look at next WINDOW_TURNS user turns
    for i, turn in enumerate(turns):
        if turn["type"] != "assistant":
            continue
        if len(turn["text"]) < MIN_EMIT_LEN:
            continue
        # Find next 3 user turns
        next_user_turns = []
        for j in range(i + 1, min(i + 1 + WINDOW_TURNS * 2, len(turns))):
            if turns[j]["type"] == "user":
                next_user_turns.append(turns[j])
                if len(next_user_turns) >= WINDOW_TURNS:
                    break
        if not next_user_turns:
            continue
        # Classify
        hits: list[str] = []
        for ut in next_user_turns:
            hits.extend(_classify_user_msg(ut["text"]))
        if hits:
            label = "FAIL"
            reason = ", ".join(sorted(set(hits)))
        else:
            label = "PASS"
            reason = "no correction-signal in next-3-user-turns"
        out.append({
            "transcript": path.name,
            "turn_index": i,
            "label": label,
            "reason": reason,
            "emit_len": len(turn["text"]),
            "emit_preview": turn["text"][:280].replace("\n", " "),
        })
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="Stop after N labelled samples (0=all)")
    ap.add_argument("--rebuild", action="store_true", help="Overwrite existing corpus")
    args = ap.parse_args()

    if not TRANSCRIPT_DIR.exists():
        print(f"transcript dir not found: {TRANSCRIPT_DIR}", file=sys.stderr)
        return 1
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    if args.rebuild and OUTPUT_PATH.exists():
        OUTPUT_PATH.unlink()

    transcripts = sorted(TRANSCRIPT_DIR.glob("*.jsonl"), key=lambda f: f.stat().st_mtime, reverse=True)
    if not transcripts:
        print("no transcripts found", file=sys.stderr)
        return 1

    samples: list[dict] = []
    for tp in transcripts:
        rows = mine_transcript(tp)
        samples.extend(rows)
        if args.limit and len(samples) >= args.limit:
            samples = samples[: args.limit]
            break

    pass_n = sum(1 for s in samples if s["label"] == "PASS")
    fail_n = sum(1 for s in samples if s["label"] == "FAIL")

    with OUTPUT_PATH.open("a") as f:
        for s in samples:
            f.write(json.dumps(s) + "\n")

    print(json.dumps({
        "mined_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "transcripts_scanned": len(transcripts),
        "samples_emitted": len(samples),
        "pass": pass_n,
        "fail": fail_n,
        "fail_rate": round(fail_n / max(1, len(samples)), 3),
        "output_path": str(OUTPUT_PATH),
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
