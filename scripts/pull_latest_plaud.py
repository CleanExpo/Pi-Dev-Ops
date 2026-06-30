"""One-off: pull the single most recent Plaud recording into brain/plaud/.

No side effects beyond writing the markdown file — no Telegram, no Linear,
no Supabase sync, no state mutation. Reuses plaud_ingest's MCP client and
page formatter.
"""
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from plaud_ingest import connect_real_plaud, format_page, slug_from_name

BRAIN_PLAUD = Path.home() / "Pi-CEO" / "brain" / "plaud"


async def main():
    date_from = sys.argv[1] if len(sys.argv) > 1 else "2026-05-01T00:00:00Z"
    async with connect_real_plaud() as client:
        files = await client.list_files_since(date_from)
        if not files:
            print(json.dumps({"status": "empty", "date_from": date_from}))
            return
        files.sort(key=lambda f: f.get("created_at") or f.get("start_time") or "", reverse=True)
        latest = files[0]
        plaud_id = latest.get("id") or latest.get("file_id")
        title = latest.get("name", str(plaud_id))
        recorded_at = str(latest.get("created_at", ""))
        duration_ms = int(latest.get("duration", 0))
        audio_url = latest.get("presigned_url", "")

        summary = await client.get_note(plaud_id)
        segments = await client.get_transcript(plaud_id)

        page = format_page(
            plaud_id=str(plaud_id), title=title, recorded_at=recorded_at,
            duration_ms=duration_ms,
            ingested_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            audio_url=audio_url, summary_md=summary or None, segments=segments,
        )
        date_prefix = recorded_at[:10] if recorded_at else "undated"
        out = BRAIN_PLAUD / f"{date_prefix}-{slug_from_name(title, str(plaud_id))}.md"
        BRAIN_PLAUD.mkdir(parents=True, exist_ok=True)
        out.write_text(page)
        print(json.dumps({
            "status": "ok", "file": str(out), "title": title,
            "recorded_at": recorded_at, "duration_ms": duration_ms,
            "segments": len(segments), "has_summary": bool(summary),
            "total_listed": len(files),
        }))


if __name__ == "__main__":
    asyncio.run(main())
