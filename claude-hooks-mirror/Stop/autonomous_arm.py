"""Utility: arm / disarm / status / queue / halt — operator interface
for the autonomous-continue hook.

Usage:
    python3 autonomous_arm.py arm [--session-id ID] [--max-count N]
                                  [--max-wall-s S] [--max-tokens N]
    python3 autonomous_arm.py disarm
    python3 autonomous_arm.py status
    python3 autonomous_arm.py queue --add "<prompt text>"
    python3 autonomous_arm.py queue --list
    python3 autonomous_arm.py queue --clear
    python3 autonomous_arm.py halt [--reason "..."]
    python3 autonomous_arm.py unhalt

Used by the controller agent when Phill types "autonomous mode: <queue>"
or "continue agentically". Also callable from Hermes Telegram intake
when Phill posts "HALT" or "STOP" to chat 8792816988.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

STATE_PATH = Path.home() / ".claude" / "state" / "autonomous.json"
QUEUE_PATH = Path.home() / "Pi-CEO" / ".harness" / "swarm" / "autonomous-queue.jsonl"
HALT_PATH = Path.home() / "Pi-CEO" / ".harness" / "swarm" / "HALT"


def _read_state() -> dict:
    if not STATE_PATH.exists():
        return {}
    try:
        return json.loads(STATE_PATH.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def _write_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2))


def cmd_arm(args) -> int:
    state = {
        "armed": True,
        "session_id": args.session_id,
        "armed_at": datetime.now(timezone.utc).isoformat(),
        "armed_at_epoch": time.time(),
        "max_count": args.max_count,
        "max_wall_s": args.max_wall_s,
        "max_tokens_est": args.max_tokens,
        "count": 0,
    }
    _write_state(state)
    print(json.dumps(state, indent=2))
    return 0


def cmd_disarm(_args) -> int:
    state = _read_state()
    state["armed"] = False
    state["disarmed_at"] = datetime.now(timezone.utc).isoformat()
    _write_state(state)
    print(json.dumps(state, indent=2))
    return 0


def cmd_status(_args) -> int:
    state = _read_state()
    queue_len = 0
    if QUEUE_PATH.exists():
        try:
            queue_len = sum(1 for line in QUEUE_PATH.read_text().splitlines() if line.strip())
        except OSError:
            queue_len = -1
    state["queue_remaining"] = queue_len
    state["halt_sentinel_present"] = HALT_PATH.exists()
    print(json.dumps(state, indent=2))
    return 0


def cmd_queue(args) -> int:
    QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if args.list:
        if not QUEUE_PATH.exists():
            print("[]")
            return 0
        print(QUEUE_PATH.read_text())
        return 0
    if args.clear:
        QUEUE_PATH.write_text("")
        print("queue cleared")
        return 0
    if args.add:
        item = {
            "id": f"q-{int(time.time())}",
            "added_at": datetime.now(timezone.utc).isoformat(),
            "prompt": args.add,
        }
        with QUEUE_PATH.open("a") as f:
            f.write(json.dumps(item) + "\n")
        print(json.dumps(item))
        return 0
    print("usage: queue --add <prompt> | --list | --clear", file=sys.stderr)
    return 2


def cmd_halt(args) -> int:
    HALT_PATH.parent.mkdir(parents=True, exist_ok=True)
    reason = args.reason or "operator-halt"
    HALT_PATH.write_text(f"{datetime.now(timezone.utc).isoformat()} | {reason}\n")
    print(f"HALT sentinel written: {HALT_PATH}")
    return 0


def cmd_unhalt(_args) -> int:
    if HALT_PATH.exists():
        HALT_PATH.unlink()
        print(f"HALT sentinel removed: {HALT_PATH}")
    else:
        print("no HALT sentinel present")
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    arm = sub.add_parser("arm")
    arm.add_argument("--session-id", default=None)
    arm.add_argument("--max-count", type=int, default=10)
    arm.add_argument("--max-wall-s", type=int, default=7200)
    arm.add_argument("--max-tokens", type=int, default=200_000)
    arm.set_defaults(func=cmd_arm)

    dis = sub.add_parser("disarm")
    dis.set_defaults(func=cmd_disarm)

    st = sub.add_parser("status")
    st.set_defaults(func=cmd_status)

    q = sub.add_parser("queue")
    q.add_argument("--add", default=None)
    q.add_argument("--list", action="store_true")
    q.add_argument("--clear", action="store_true")
    q.set_defaults(func=cmd_queue)

    h = sub.add_parser("halt")
    h.add_argument("--reason", default=None)
    h.set_defaults(func=cmd_halt)

    u = sub.add_parser("unhalt")
    u.set_defaults(func=cmd_unhalt)

    ns = ap.parse_args(argv[1:])
    return ns.func(ns)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
