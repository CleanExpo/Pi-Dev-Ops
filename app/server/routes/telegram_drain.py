"""Telegram inbox drain — extracted from webhooks.py (RA-7530).

Pure relocation, no logic change: webhooks.py is a baselined file (grew
past its file-length ratchet entry when RA-7530 added callback_query
handling), so this self-contained, single-call-site function moved here to
make room. webhooks.py keeps a module-level alias so existing monkeypatches
(tests, continuation_bridge.py) still work unchanged.
"""
from __future__ import annotations

import logging

log = logging.getLogger("pi-ceo.main")


def drain_telegram_update(data: dict) -> dict:
    """Route a Telegram webhook update through the same inbox path as polling."""
    try:
        from scripts import marathon_telegram_inbox, marathon_watchdog  # noqa: PLC0415

        _, allowed_chat_ids = marathon_telegram_inbox._resolve_config()
        ingested_path = marathon_telegram_inbox._ingest_update(
            data,
            allowed_chat_ids,
            dry_run=False,
        )
        ingested = 1 if ingested_path is not None else 0
        dropped = 0 if ingested else 1
        offset = int(data.get("update_id") or 0) + 1
        marathon_telegram_inbox._write_heartbeat(
            polled=1,
            ingested=ingested,
            dropped=dropped,
            gc_count=0,
            offset=offset,
        )
        processed = 0
        replies: list[str] = []
        if ingested:
            processed, replies = marathon_watchdog._drain_inbox()
        return {
            "ok": True,
            "ingested": ingested,
            "dropped": dropped,
            "processed": processed,
            "replies": replies[:3],
        }
    except SystemExit as exc:
        return {"ok": False, "error": f"telegram_config_exit:{exc.code}"}
    except Exception as exc:
        log.warning("Telegram webhook intake failed: %s", exc, exc_info=True)
        return {"ok": False, "error": str(exc)[:160]}
