"""Weekly reviewer-weight recalibration.

Per Pi-CEO Board memo 2026-05-15 (Layer 6 / NEXT ACTIONS #3).
First firing Mon 2026-05-25 06:00 AEST (Sun 20:00 UTC) via Hermes cron.

Reads:
  - ~/Pi-CEO/.harness/swarm/calibration-corpus.jsonl (PASS/FAIL auto-labels
    mined from Phill's natural corrections by calibration_corpus_miner.py)
  - ~/Pi-CEO/.harness/swarm/reviewer-verdict.jsonl (the actual gate verdicts
    written by reviewer.py subprocess wrappers)

Computes per-reviewer agreement rate against auto-labels (a simplified
Spearman proxy — exact match rate, since labels are binary), updates
weights, writes:
  - ~/Pi-CEO/.harness/swarm/reviewer-weights.json (used by the panel
    aggregator on next run)

Posts a single-shot Telegram summary to chat 8792816988 via Pi-CEO
UniteGroup bot.

Stdlib only. Per [[feedback-no-repeating-alerts]] single-shot only.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

SWARM_DIR = Path.home() / "Pi-CEO" / ".harness" / "swarm"
CORPUS_PATH = SWARM_DIR / "calibration-corpus.jsonl"
VERDICT_PATH = SWARM_DIR / "reviewer-verdict.jsonl"
WEIGHTS_PATH = SWARM_DIR / "reviewer-weights.json"
HERMES_ENV = Path.home() / ".hermes" / ".env"
HOME_CHAT_ID = 8792816988


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    try:
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    except OSError:
        return []
    return out


def _bot_token() -> str:
    if not HERMES_ENV.exists():
        return ""
    try:
        for line in HERMES_ENV.read_text().splitlines():
            for key in ("TELEGRAM_BOT_TOKEN_PICEO=", "TELEGRAM_BOT_TOKEN_UNITEGROUP="):
                if line.startswith(key):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError:
        return ""
    return ""


def _telegram(text: str) -> bool:
    token = _bot_token()
    if not token:
        return False
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = json.dumps({"chat_id": HOME_CHAT_ID, "text": text, "parse_mode": "Markdown"}).encode()
        req = urllib.request.Request(url, data=payload, method="POST",
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except (urllib.error.URLError, urllib.error.HTTPError, OSError):
        return False


def compute_weights() -> dict:
    corpus = _load_jsonl(CORPUS_PATH)
    verdicts = _load_jsonl(VERDICT_PATH)

    # No verdicts yet — emit baseline weights (equal across reviewers)
    if not verdicts:
        return {
            "computed_at": datetime.now(timezone.utc).isoformat(),
            "status": "baseline",
            "reason": "no verdicts yet — baseline equal weights",
            "weights": {"qa-lead": 1.0, "brand-guardian": 1.0, "contrarian": 1.0},
            "corpus_size": len(corpus),
            "verdict_count": 0,
        }

    # Join verdicts to corpus by draft_path → emit_preview match (best-effort
    # since the gate runs on live emits and corpus is from transcripts;
    # exact matching only works on overlap).
    by_reviewer = defaultdict(lambda: {"agree": 0, "disagree": 0, "n": 0})
    for v in verdicts:
        reviewer = v.get("reviewer")
        if reviewer not in ("qa-lead", "brand-guardian", "contrarian"):
            continue
        by_reviewer[reviewer]["n"] += 1
        # Map reviewer verdict (PASS/NO) to corpus label (PASS/FAIL)
        rv = v.get("verdict")
        gate_label = "PASS" if rv == "PASS" else "FAIL"
        # Look up corresponding corpus entry — match by draft_path stem
        draft = v.get("draft_path", "")
        match = next((c for c in corpus if c.get("emit_preview", "")[:120] in draft), None)
        if not match:
            continue
        if gate_label == match["label"]:
            by_reviewer[reviewer]["agree"] += 1
        else:
            by_reviewer[reviewer]["disagree"] += 1

    weights = {}
    for r in ("qa-lead", "brand-guardian", "contrarian"):
        stats = by_reviewer[r]
        evaluated = stats["agree"] + stats["disagree"]
        if evaluated == 0:
            weights[r] = 1.0
        else:
            agreement = stats["agree"] / evaluated
            # Map [0.5, 1.0] → [0.5, 1.5]; below 0.5 floors at 0.5 (still consulted but de-weighted)
            weights[r] = max(0.5, min(1.5, 0.5 + agreement))

    return {
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "status": "calibrated",
        "weights": weights,
        "per_reviewer_stats": dict(by_reviewer),
        "corpus_size": len(corpus),
        "verdict_count": len(verdicts),
    }


def format_brief(result: dict) -> str:
    lines = [
        "# Reviewer-Weight Weekly Recalibration",
        "",
        f"**Status:** `{result['status']}`",
        f"**Corpus:** {result['corpus_size']} samples · Verdicts: {result['verdict_count']}",
        "",
        "## Weights (capped 0.5 – 1.5):",
    ]
    for k, v in result["weights"].items():
        lines.append(f"  - **{k}**: `{v:.2f}`")
    if "per_reviewer_stats" in result:
        lines.append("")
        lines.append("## Per-reviewer agreement vs auto-labels:")
        for r, s in result["per_reviewer_stats"].items():
            n = s["agree"] + s["disagree"]
            rate = f"{s['agree']/n:.1%}" if n else "n/a"
            lines.append(f"  - {r}: agree {s['agree']} / disagree {s['disagree']} / n {s['n']} → **{rate}**")
    if result["status"] == "baseline":
        lines.append("")
        lines.append("⚠️ No reviewer verdicts yet — equal weights. First gate-fire will start populating.")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--post", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    result = compute_weights()
    SWARM_DIR.mkdir(parents=True, exist_ok=True)
    WEIGHTS_PATH.write_text(json.dumps(result, indent=2))

    if args.json:
        print(json.dumps(result, indent=2))
        return 0

    brief = format_brief(result)
    print(brief)
    if args.post:
        ok = _telegram(brief)
        print(f"\nTelegram post: {'OK' if ok else 'FAILED'}", file=sys.stderr)
        return 0 if ok else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
