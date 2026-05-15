"""Daily L4 executive digest.

Per ADR 003 scope-separation: this cron reads pilot_suggestions DIRECTLY and
IGNORES pause_state. STOP / PAUSE 24h halt the interactive stream only — the
daily digest survives any pause-state. DO NOT add a pause_state check here.
"""


def daily_text(memory) -> str:
    counts = memory.daily_counts()
    top = memory.top_pending()
    lines = [
        "Pilot daily digest",
        f"Accepted: {counts.get('accepted', 0)} · "
        f"Rejected: {counts.get('rejected', 0)} · "
        f"Deferred: {counts.get('deferred', 0)} · "
        f"Blocked: {counts.get('blocked', 0)}",
    ]
    if top:
        lines.append("\nTop pending:")
        for sug in top[:5]:
            lines.append(f"  • {sug.get('headline', '?')[:60]}")
    return "\n".join(lines)
