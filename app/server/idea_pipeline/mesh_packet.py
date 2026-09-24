"""Attach a mesh plan-lane Board packet to the idea it reviewed.

A node running an ``idea:plan`` ticket returns one markdown packet. It lands on the
idea-pipeline item for that ticket so the Board panel shows it, matched in this order:

1. the item already carrying this ``linear_id`` (a re-review replaces the packet);
2. the item whose text is the ticket title (same words, same idea) — only while it is
   linked to no ticket or to this one; another ticket's card is never taken over;
3. otherwise a new item, built by ``build_packet`` so the panel has every field it reads.

Stored in the existing JSON store under ``.harness/idea-pipeline/`` — no new table.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .intake import RawIdea, idea_id_for
from .packet import build_packet
from .store import default_store_dir, list_packets, read_packet, write_packet

PACKET_MAX_CHARS = 20_000
TITLE_MAX_CHARS = 500


def _idea_text(linear_id: str, title: str) -> str:
    return " ".join(title.split())[:TITLE_MAX_CHARS] or f"Linear {linear_id}"


def _find(store: Path, linear_id: str, text: str) -> dict[str, Any] | None:
    for row in list_packets(store):
        if row.get("linear_id") == linear_id:
            return row
    row = read_packet(store, idea_id_for(text))
    return row if row and row.get("linear_id") in (None, "", linear_id) else None


def _new(store: Path, linear_id: str, text: str) -> dict[str, Any]:
    """A fresh card. Its id is the title's, unless that id belongs to another ticket's
    card — then the Linear id joins the key, so the two never share a file."""
    idea_id = idea_id_for(text)
    if read_packet(store, idea_id) is not None:
        idea_id = idea_id_for(f"{linear_id} {text}")
    idea = RawIdea(idea_id=idea_id, text=text, source="mesh",
                   intake_path=f"linear:{linear_id}")
    return build_packet(idea)


def attach_plan_packet(
    repo_root: Path, linear_id: str, packet_md: str, *, title: str = ""
) -> dict[str, Any]:
    store = default_store_dir(repo_root)
    text = _idea_text(linear_id, title)
    packet = _find(store, linear_id, text) or _new(store, linear_id, text)
    packet.update(
        linear_id=linear_id,
        plan_packet_md=packet_md[:PACKET_MAX_CHARS],
        plan_packet_at=datetime.now(timezone.utc).isoformat(),
    )
    write_packet(store, packet)
    return packet
