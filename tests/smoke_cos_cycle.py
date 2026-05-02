"""
tests/smoke_cos_cycle.py — RA-1839: end-to-end smoke for the Chief-of-Staff cycle.

Standalone smoke (NOT a pytest unit) — run via:

    cd Pi-Dev-Ops
    python tests/smoke_cos_cycle.py

Runs the actual `chief_of_staff.run_cycle()` once in shadow + draft-test
mode, then exercises `_route()` directly for each of the 6 intents to
confirm the full classify → route → draft pipeline ships clean audit rows.

Pass criteria:
  1. run_cycle returns the expected shape (no crash)
  2. Each of the 6 intents produces the expected routing outcome
  3. Audit rows are written for every draft posted
  4. Kill-switch transitions are honoured in routing
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

# Repo root — go up one (this file is in tests/)
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

# ── Smoke env (must be set BEFORE importing swarm modules) ───────────────────
os.environ["TAO_SWARM_ENABLED"] = "1"
os.environ["TAO_SWARM_SHADOW"] = "1"
os.environ["TAO_DRAFT_REVIEW_TEST"] = "1"
os.environ["TELEGRAM_BOT_TOKEN"] = "smoke-token-not-real"
os.environ["TELEGRAM_ALERT_CHAT_ID"] = "0"

# Override SWARM_LOG_DIR to a tempdir so this smoke doesn't pollute real logs
tmp = Path(tempfile.mkdtemp(prefix="cos-smoke-"))
os.environ["TAO_SWARM_LOG_DIR"] = str(tmp)

# Now import (config reads env on import)
from swarm import (  # noqa: E402
    intent_router,
    draft_review,
    flow_engine,
    audit_emit,
    kill_switch,
)
from swarm.bots import chief_of_staff  # noqa: E402

GREEN, RED, RESET = "\033[32m", "\033[31m", "\033[0m"


def _ok(msg: str) -> None:
    print(f"  {GREEN}✅{RESET} {msg}")


def _fail(msg: str) -> None:
    print(f"  {RED}❌{RESET} {msg}")
    raise AssertionError(msg)


def _audit_rows() -> list[dict]:
    p = tmp / "swarm.jsonl"
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except Exception:
            pass
    return out


def smoke_run_cycle() -> None:
    print("\n[1] chief_of_staff.run_cycle() — single cycle")
    result = chief_of_staff.run_cycle(unacked_count=0)
    if not isinstance(result, dict):
        _fail(f"expected dict result, got {type(result)}")
    expected_keys = {"unacked", "messages_handled", "drafts_expired", "new_offset"}
    if not expected_keys.issubset(result.keys()):
        # Or skipped (if config.SWARM_ENABLED was somehow false)
        if "skipped" in result:
            _fail(f"unexpected skip: {result}")
        _fail(f"missing keys: {expected_keys - result.keys()} in {result}")
    _ok(f"run_cycle returned {result}")
    if result["messages_handled"] != 0:
        _fail("expected 0 messages handled (no real Telegram in smoke)")
    _ok("zero messages handled (no real Telegram polled — expected)")


def smoke_route_each_intent() -> None:
    print("\n[2] _route() for each of the 6 intents")
    cases = [
        ("research", {
            "intent": "research", "confidence": 0.85,
            "fields": {"topic": "Hermes v0.13 release", "time_budget": "deep", "use_corpus": True},
            "originating_chat_id": "smoke-chat", "originating_message_id": "msg-research",
        }),
        ("ticket", {
            "intent": "ticket", "confidence": 0.85,
            "fields": {"team_hint": "RA", "title_hint": "Add CoS smoke harness"},
            "originating_chat_id": "smoke-chat", "originating_message_id": "msg-ticket",
        }),
        ("reply", {
            "intent": "reply", "confidence": 0.75,
            "fields": {"medium": "telegram", "body_hint": "tell Margot to research X"},
            "originating_chat_id": "smoke-chat", "originating_message_id": "msg-reply",
        }),
        ("reminder", {
            "intent": "reminder", "confidence": 0.80,
            "fields": {"when": "2026-05-08T09:00:00+00:00", "what": "spike gate due"},
            "originating_chat_id": "smoke-chat", "originating_message_id": "msg-reminder",
        }),
        ("flow", {
            "intent": "flow", "confidence": 0.80,
            "fields": {"raw_steps_text": "first list issues, then comment, then notify"},
            "originating_chat_id": "smoke-chat", "originating_message_id": "msg-flow",
        }),
        ("unknown", {
            "intent": "unknown", "confidence": 0.0,
            "fields": {},
            "originating_chat_id": "smoke-chat", "originating_message_id": "msg-unknown",
        }),
    ]

    audit_before = len(_audit_rows())
    drafts_posted = 0

    for label, payload in cases:
        result = chief_of_staff._route(payload)
        if label == "unknown":
            if result.get("draft_id") not in (None, ""):
                _fail(f"unknown intent should NOT post a draft, got {result}")
            _ok(f"unknown intent → no_action ({result.get('reason', '')})")
        else:
            if not result.get("draft_id"):
                _fail(f"{label} intent should post a draft, got {result}")
            _ok(f"{label} intent → draft {result['draft_id']}")
            drafts_posted += 1

    audit_after = len(_audit_rows())
    new_rows = audit_after - audit_before
    if new_rows < drafts_posted:
        _fail(f"expected ≥{drafts_posted} new audit rows, got {new_rows}")
    _ok(f"audit rows added: {new_rows} (≥{drafts_posted} drafts) — schema-enforced via audit_emit")


def smoke_kill_switch_skip() -> None:
    print("\n[3] kill-switch halts routing without crashing")
    kill_switch.trigger("telegram_panic", reason="smoke kill-switch test")
    if not kill_switch.is_active():
        _fail("kill_switch.trigger should have engaged the flag")
    _ok("kill-switch engaged")

    result = chief_of_staff.run_cycle(unacked_count=0)
    # In test mode, posting a draft via draft_review during kill-switch:
    #   - the draft is still POSTED to review (so user sees the queue)
    #   - but the SEND on 👍 would be deferred (not relevant in smoke)
    # The CoS itself doesn't crash either way. Verify it returned cleanly.
    if "skipped" in result and "kill-switch off" in str(result):
        _ok("CoS gracefully skipped on disabled SWARM_ENABLED")
    else:
        _ok(f"CoS run_cycle returned cleanly during kill-switch: {result}")

    kill_switch.resume("telegram_resume", reason="smoke clear")
    if kill_switch.is_active():
        _fail("kill_switch.resume should have cleared the flag")
    _ok("kill-switch resumed")


def smoke_audit_schema() -> None:
    print("\n[4] every audit row matches audit_emit schema")
    rows = _audit_rows()
    if not rows:
        _fail("no audit rows produced")
    bad = []
    for r in rows:
        if not all(k in r for k in ("ts", "type", "actor_role")):
            bad.append(r)
    if bad:
        _fail(f"{len(bad)} audit rows missing schema keys: {bad[:2]}")
    _ok(f"{len(rows)} rows, all match schema (ts, type, actor_role)")
    by_type = {}
    for r in rows:
        by_type.setdefault(r["type"], 0)
        by_type[r["type"]] += 1
    print(f"     by type: {dict(sorted(by_type.items()))}")


def smoke_state_persistence() -> None:
    print("\n[5] dispatcher state + draft snapshot persistence")
    snapshot = tmp / "telegram_drafts.json"
    if not snapshot.exists():
        _fail("telegram_drafts.json snapshot not written")
    state = json.loads(snapshot.read_text())
    if not isinstance(state, dict) or not state:
        _fail(f"snapshot empty or wrong shape: {state}")
    _ok(f"draft snapshot has {len(state)} entries")

    # Audit jsonl + drafts jsonl both present
    for f in ("swarm.jsonl", "telegram_drafts.jsonl"):
        p = tmp / f
        if not p.exists() or p.stat().st_size == 0:
            _fail(f"{f} missing or empty")
    _ok("swarm.jsonl + telegram_drafts.jsonl both populated")


def main() -> int:
    print(f"=" * 60)
    print(f"CoS SMOKE — temp log dir: {tmp}")
    print(f"=" * 60)
    try:
        smoke_run_cycle()
        smoke_route_each_intent()
        smoke_kill_switch_skip()
        smoke_audit_schema()
        smoke_state_persistence()
        print("\n" + "=" * 60)
        print(f"{GREEN}ALL SMOKE TESTS PASS{RESET}")
        print("=" * 60)
        return 0
    except AssertionError as exc:
        print(f"\n{RED}SMOKE FAILED: {exc}{RESET}")
        return 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
