from __future__ import annotations

import json
from pathlib import Path

from scripts import marathon_telegram_inbox, marathon_watchdog


def test_telegram_inbox_accepts_phone_chat_and_writes_heartbeat(
    tmp_path: Path,
    monkeypatch,
):
    inbox_dir = tmp_path / "telegram-inbox"
    heartbeat = tmp_path / "telegram-poll-heartbeat"
    monkeypatch.setattr(marathon_telegram_inbox, "INBOX_DIR", inbox_dir)
    monkeypatch.setattr(marathon_telegram_inbox, "OFFSET_FILE", inbox_dir / ".offset")
    monkeypatch.setattr(marathon_telegram_inbox, "HEARTBEAT_FILE", heartbeat)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.delenv("ALLOWED_USERS", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.setenv("PHONE_COMPANION_CHAT_ID", "12345")

    def fake_get_updates(token: str, offset: int, timeout_sec: int = 0) -> list[dict]:
        assert token == "test-token"
        assert offset == 0
        return [
            {
                "update_id": 42,
                "message": {
                    "message_id": 7,
                    "date": 1_718_000_000,
                    "chat": {"id": 12345},
                    "from": {"first_name": "Phill"},
                    "text": "idea: tighten Telegram Linear loop",
                },
            }
        ]

    monkeypatch.setattr(marathon_telegram_inbox, "_get_updates", fake_get_updates)

    assert marathon_telegram_inbox.main() == 0

    inbox_files = list(inbox_dir.glob("*.json"))
    assert len(inbox_files) == 1
    payload = json.loads(inbox_files[0].read_text(encoding="utf-8"))
    assert payload["chat_id"] == "12345"
    assert payload["processed"] is False

    heartbeat_payload = json.loads(heartbeat.read_text(encoding="utf-8"))
    assert heartbeat_payload["polled"] == 1
    assert heartbeat_payload["ingested"] == 1
    assert heartbeat_payload["dropped"] == 0
    assert heartbeat_payload["offset"] == 43


def test_watchdog_queues_telegram_idea_for_linear_jsonl(tmp_path: Path, monkeypatch):
    inbox_dir = tmp_path / "telegram-inbox"
    ideas_dir = tmp_path / "ideas-from-phone"
    inbox_dir.mkdir()
    monkeypatch.setattr(marathon_watchdog, "INBOX_DIR", inbox_dir)
    monkeypatch.setattr(marathon_watchdog, "IDEAS_DIR", ideas_dir)
    monkeypatch.delenv("LINEAR_API_KEY", raising=False)
    inbox_file = inbox_dir / "000000000042.json"
    inbox_file.write_text(
        json.dumps(
            {
                "update_id": 42,
                "message_id": 7,
                "chat_id": "12345",
                "from": "Phill",
                "text": "idea: build continuous Linear intake",
                "processed": False,
                "received_at": "2026-06-17T02:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )

    processed_count, replies = marathon_watchdog._drain_inbox()

    assert processed_count == 1
    assert replies == [
        "+ idea queued for Linear: 'build continuous Linear intake' -> 2026-06-17.jsonl "
        "(queued; LINEAR_API_KEY not available to watchdog)"
    ]
    routed = json.loads(inbox_file.read_text(encoding="utf-8"))
    assert routed["processed"] is True
    assert routed["route"] == "idea"

    jsonl_file = ideas_dir / "2026-06-17.jsonl"
    queued = json.loads(jsonl_file.read_text(encoding="utf-8").strip())
    assert queued["processed"] is False
    assert queued["source"] == "telegram"
    assert queued["text"] == "build continuous Linear intake"
    assert queued["telegram"]["update_id"] == 42
    assert (ideas_dir / "000000000042.md").exists()


def test_watchdog_auto_promotes_telegram_ideas_when_linear_key_exists(
    tmp_path: Path,
    monkeypatch,
):
    jsonl_file = tmp_path / "ideas.jsonl"
    jsonl_file.write_text(
        json.dumps(
            {
                "ts": "2026-06-17T02:00:00+00:00",
                "user_name": "Phill",
                "text": "build continuous Linear intake",
                "processed": False,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("LINEAR_API_KEY", "lin_test")

    calls: list[tuple[Path, str, bool]] = []

    from scripts import process_ideas_inbox

    def fake_process_file(path: Path, api_key: str, *, dry_run: bool):
        calls.append((path, api_key, dry_run))
        return (0, 1, 0)

    monkeypatch.setattr(process_ideas_inbox, "process_file", fake_process_file)

    result = marathon_watchdog._auto_promote_phone_ideas(jsonl_file)

    assert result == "Linear promoted now (1 created)"
    assert calls == [(jsonl_file, "lin_test", False)]
