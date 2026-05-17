"""Stop-hook L5: autonomous-continue — block agent loop while queue
is non-empty, under triple-cap, and HALT sentinel absent.

Per Pi-CEO Board memo 2026-05-15 (Supabase board_directives id
e0a59b1e-9df2-4594-84f0-2b23b029fc8b). Closes the "stops after one
task" failure mode Phill surfaced. Wires into existing Stop chain at
~/.claude/settings.json after 01_violation_log.

Mechanism:
  1. Read arm-state from ~/.claude/state/autonomous.json. If not armed
     for the current session → exit 0 (cleanly hands off to user).
  2. Read queue from ~/Pi-CEO/.harness/swarm/autonomous-queue.jsonl.
     If empty → emit Telegram digest + exit 0.
  3. Check triple-cap: count + wall-clock + estimated tokens. If any
     exceeded → emit Telegram digest + exit 0 (clean halt).
  4. Check HALT: ~/Pi-CEO/.harness/swarm/HALT sentinel OR recent
     Telegram HALT message within the last 60s. If present → emit
     Telegram halt confirmation + exit 0.
  5. Otherwise → pop next queue item, increment counters, log trace
     to ~/Pi-CEO/.harness/swarm/autonomous-trace.jsonl, and emit
     Claude Code Stop-hook block-decision JSON to keep the loop alive.

Stdlib only. Never raises — any unexpected failure falls back to
clean exit (default-safe: stop the loop, hand back to user).
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

STATE_PATH = Path.home() / ".claude" / "state" / "autonomous.json"
QUEUE_PATH = Path.home() / "Pi-CEO" / ".harness" / "swarm" / "autonomous-queue.jsonl"
TRACE_PATH = Path.home() / "Pi-CEO" / ".harness" / "swarm" / "autonomous-trace.jsonl"
HALT_PATH = Path.home() / "Pi-CEO" / ".harness" / "swarm" / "HALT"
TG_HALT_PATH = Path.home() / "Pi-CEO" / ".harness" / "swarm" / "telegram-halt.jsonl"
HERMES_ENV = Path.home() / ".hermes" / ".env"
HOME_CHAT_ID = 8792816988

# Defaults if not specified in state file
DEFAULT_MAX_COUNT = 10
DEFAULT_MAX_WALL_S = 7200  # 2h
DEFAULT_MAX_TOKENS_EST = 200_000
CHARS_PER_TOKEN = 4.0  # rough estimate for usage cap


def _read_stdin_json() -> dict:
    raw = sys.stdin.read() if not sys.stdin.isatty() else ""
    if not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"_raw": raw[:200]}


def _load_state() -> dict:
    if not STATE_PATH.exists():
        return {}
    try:
        return json.loads(STATE_PATH.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def _write_state(state: dict) -> None:
    try:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(json.dumps(state, indent=2))
    except OSError:
        pass


def _load_queue() -> list[dict]:
    if not QUEUE_PATH.exists():
        return []
    out: list[dict] = []
    try:
        for line in QUEUE_PATH.read_text().splitlines():
            if not line.strip():
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    except OSError:
        return []
    return out


def _save_queue(items: list[dict]) -> None:
    try:
        QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
        QUEUE_PATH.write_text("\n".join(json.dumps(i) for i in items) + ("\n" if items else ""))
    except OSError:
        pass


def _check_halt() -> str | None:
    """Returns halt reason if a halt signal is active, else None."""
    if HALT_PATH.exists():
        try:
            return f"sentinel-file: {HALT_PATH.read_text().strip()[:120] or 'no-msg'}"
        except OSError:
            return "sentinel-file"
    # Recent telegram HALT (last 60s)
    if TG_HALT_PATH.exists():
        try:
            now = time.time()
            for line in reversed(TG_HALT_PATH.read_text().splitlines()):
                if not line.strip():
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts = rec.get("ts_epoch", 0)
                if now - ts < 60:
                    return f"telegram-halt: {rec.get('from', '?')}"
        except OSError:
            pass
    return None


def _estimate_tokens_used(transcript_path: str | None) -> int:
    if not transcript_path:
        return 0
    p = Path(transcript_path).expanduser()
    if not p.exists():
        return 0
    try:
        size = p.stat().st_size
        return int(size / CHARS_PER_TOKEN)
    except OSError:
        return 0


def _bot_token() -> str:
    if not HERMES_ENV.exists():
        return ""
    try:
        for line in HERMES_ENV.read_text().splitlines():
            if line.startswith("TELEGRAM_BOT_TOKEN_PICEO=") or line.startswith("TELEGRAM_BOT_TOKEN_UNITEGROUP="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError:
        return ""
    return ""


def _telegram_notify(text: str) -> bool:
    token = _bot_token()
    if not token:
        return False
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = json.dumps({"chat_id": HOME_CHAT_ID, "text": text, "parse_mode": "Markdown"}).encode()
        req = urllib.request.Request(url, data=payload, method="POST",
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            return resp.status == 200
    except (urllib.error.URLError, urllib.error.HTTPError, OSError):
        return False


def _trace(event: str, **fields) -> None:
    rec = {"ts": datetime.now(timezone.utc).isoformat(), "event": event, **fields}
    try:
        TRACE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with TRACE_PATH.open("a") as f:
            f.write(json.dumps(rec) + "\n")
    except OSError:
        pass


def _emit_block(prompt: str) -> int:
    """Return Stop-hook block-decision JSON to keep the agent loop alive."""
    out = {
        "decision": "block",
        "reason": prompt,
    }
    sys.stdout.write(json.dumps(out))
    sys.stdout.flush()
    return 0


def main() -> int:
    try:
        session = _read_stdin_json()
        state = _load_state()

        # Step 1 — armed?
        if not state.get("armed"):
            return 0
        session_id = session.get("session_id")
        if session_id and state.get("session_id") not in (None, "", session_id):
            return 0  # armed for a different session

        # Step 4 — HALT check (before queue check so halt is always honoured)
        halt_reason = _check_halt()
        if halt_reason:
            state["armed"] = False
            state["halted_at"] = datetime.now(timezone.utc).isoformat()
            state["halted_reason"] = halt_reason
            _write_state(state)
            _trace("halted", reason=halt_reason, count=state.get("count", 0))
            _telegram_notify(
                f"🛑 Autonomous mode HALTED\n"
                f"reason: `{halt_reason}`\n"
                f"completed: {state.get('count', 0)} tasks\n"
                f"queue remaining: {len(_load_queue())} items"
            )
            return 0

        # Step 2 — queue?
        queue = _load_queue()
        if not queue:
            state["armed"] = False
            state["completed_at"] = datetime.now(timezone.utc).isoformat()
            _write_state(state)
            _trace("queue_empty", count=state.get("count", 0))
            _telegram_notify(
                f"✅ Autonomous queue exhausted\n"
                f"completed: {state.get('count', 0)} tasks\n"
                f"wall-clock: {int(time.time() - state.get('armed_at_epoch', time.time()))}s"
            )
            return 0

        # Step 3 — triple-cap
        count = state.get("count", 0)
        max_count = state.get("max_count", DEFAULT_MAX_COUNT)
        if count >= max_count:
            state["armed"] = False
            state["halted_at"] = datetime.now(timezone.utc).isoformat()
            state["halted_reason"] = f"max_count {max_count} reached"
            _write_state(state)
            _trace("cap_hit_count", count=count, max=max_count)
            _telegram_notify(
                f"🟡 Autonomous mode hit count cap\n"
                f"completed: {count} / {max_count}\n"
                f"queue remaining: {len(queue)} items"
            )
            return 0

        armed_at = state.get("armed_at_epoch", time.time())
        wall = time.time() - armed_at
        max_wall = state.get("max_wall_s", DEFAULT_MAX_WALL_S)
        if wall >= max_wall:
            state["armed"] = False
            state["halted_at"] = datetime.now(timezone.utc).isoformat()
            state["halted_reason"] = f"max_wall_s {max_wall} reached"
            _write_state(state)
            _trace("cap_hit_wall", wall_s=int(wall), max=max_wall)
            _telegram_notify(
                f"🟡 Autonomous mode hit wall-clock cap\n"
                f"elapsed: {int(wall)}s / {max_wall}s\n"
                f"completed: {count}; queue remaining: {len(queue)}"
            )
            return 0

        tokens_used = _estimate_tokens_used(session.get("transcript_path"))
        max_tokens = state.get("max_tokens_est", DEFAULT_MAX_TOKENS_EST)
        if tokens_used >= max_tokens:
            state["armed"] = False
            state["halted_at"] = datetime.now(timezone.utc).isoformat()
            state["halted_reason"] = f"max_tokens_est {max_tokens} reached"
            _write_state(state)
            _trace("cap_hit_tokens", tokens_used=tokens_used, max=max_tokens)
            _telegram_notify(
                f"🟡 Autonomous mode hit token-estimate cap\n"
                f"used (est): {tokens_used} / {max_tokens}\n"
                f"completed: {count}; queue remaining: {len(queue)}"
            )
            return 0

        # Step 5 — pop next item, increment, log, block
        next_item = queue[0]
        remaining = queue[1:]
        _save_queue(remaining)

        state["count"] = count + 1
        state["last_dispatched_at"] = datetime.now(timezone.utc).isoformat()
        state["last_item"] = next_item.get("id") or next_item.get("title")
        _write_state(state)
        _trace("dispatched", item_id=state["last_item"], remaining=len(remaining),
               count=state["count"], wall_s=int(wall), tokens_est=tokens_used)

        prompt = next_item.get("prompt") or next_item.get("description") or next_item.get("title")
        if not prompt:
            return 0
        return _emit_block(prompt)
    except Exception as e:  # noqa: BLE001 — default-safe on any unexpected fault
        _trace("hook_error", error=str(e)[:200])
        return 0


if __name__ == "__main__":
    sys.exit(main())
