"""Board section renderer extracted from the daily six-pager."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def render_board_section(repo_root: Path) -> str:
    try:
        from . import board
    except Exception:  # noqa: BLE001
        return "🏛 Board — module unavailable."
    pending = board.get_pending(repo_root=repo_root)
    sessions_dir = repo_root / board.SESSIONS_DIR_REL
    recent: list[dict[str, Any]] = []
    if sessions_dir.exists():
        for path in sorted(sessions_dir.glob("*.json"))[-5:]:
            try:
                recent.append(json.loads(path.read_text(encoding="utf-8")))
            except Exception:  # noqa: BLE001
                continue
    open_hitl = [row for row in recent if row.get("hitl_required")]
    directive_count = sum(len(row.get("directives") or []) for row in recent)
    lines = [
        f"🏛 Board — {len(pending)} pending · {len(recent)} recent sessions · "
        f"{directive_count} directives · {len(open_hitl)} HITL"
    ]
    if pending:
        lines.extend(["", "Pending deliberations:"])
        lines.extend(f"- {session_id}" for session_id in pending[:5])
    if open_hitl:
        lines.extend(["", "⏳ Awaiting founder decision:"])
        for row in open_hitl[:3]:
            question = row.get("hitl_question") or "(no question)"
            topic = (row.get("brief") or {}).get("topic", "")[:60]
            lines.append(f"- [{row.get('session_id', '?')}] {topic}: {question}")
    if recent and not open_hitl and not pending:
        lines.extend(["", "Recent decisions:"])
        for row in recent[-2:]:
            topic = (row.get("brief") or {}).get("topic", "")[:60]
            count = len(row.get("directives") or [])
            lines.append(
                f"- [{row.get('session_id', '?')}] {topic} → {count} "
                f"directive{'s' if count != 1 else ''}"
            )
    return "\n".join(lines)
