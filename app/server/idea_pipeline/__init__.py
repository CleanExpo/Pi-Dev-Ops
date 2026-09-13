"""WS2 idea pipeline: IDEAS.md → Board packet → one-word dispose → GO."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .constants import INTAKE_FILENAME, NORTH_STAR, VERDICTS
from .dispose import (
    PipelineGateError,
    authorize_go,
    dispose,
    start_spec_pipeline,
    try_execute,
)
from .intake import append_idea, default_intake_path, read_ideas
from .packet import build_packet
from .store import default_store_dir, read_packet, write_packet

__all__ = [
    "INTAKE_FILENAME",
    "NORTH_STAR",
    "PipelineGateError",
    "VERDICTS",
    "append_and_examine",
    "authorize_go_for",
    "daily_snapshot",
    "dispose_idea",
    "examine_intake",
    "start_spec_pipeline",
    "try_execute_idea",
]


def _paths(repo_root: Path) -> tuple[Path, Path]:
    return default_intake_path(repo_root), default_store_dir(repo_root)


def examine_intake(repo_root: Path) -> list[dict[str, Any]]:
    intake, store = _paths(repo_root)
    ideas = read_ideas(intake)
    packets: list[dict[str, Any]] = []
    for idea in ideas:
        existing = read_packet(store, idea.idea_id)
        if existing and existing.get("status") == "disposed":
            packets.append(existing)
            continue
        packet = existing or build_packet(idea, ideas)
        if existing is None:
            write_packet(store, packet)
        packets.append(packet)
    return packets


def append_and_examine(
    repo_root: Path, text: str, *, source: str = "phill"
) -> dict[str, Any]:
    intake, store = _paths(repo_root)
    idea = append_idea(intake, text, source=source)
    ideas = read_ideas(intake)
    packet = build_packet(idea, ideas)
    write_packet(store, packet)
    return packet


def _require_packet(repo_root: Path, idea_id: str) -> tuple[Path, dict[str, Any]]:
    store = default_store_dir(repo_root)
    packet = read_packet(store, idea_id)
    if packet is None:
        raise PipelineGateError("No Board packet for that idea.")
    return store, packet


def dispose_idea(repo_root: Path, idea_id: str, word: str) -> dict[str, Any]:
    store, packet = _require_packet(repo_root, idea_id)
    updated = dispose(packet, word)
    write_packet(store, updated)
    return updated


def authorize_go_for(repo_root: Path, idea_id: str) -> dict[str, Any]:
    store, packet = _require_packet(repo_root, idea_id)
    updated = authorize_go(packet)
    write_packet(store, updated)
    return updated


def try_execute_idea(repo_root: Path, idea_id: str) -> dict[str, Any]:
    store, packet = _require_packet(repo_root, idea_id)
    updated = try_execute(packet)
    write_packet(store, updated)
    return updated


def _awaiting(packets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in packets if row.get("status") == "awaiting_dispose"]


def _pending_go(packets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        row
        for row in packets
        if row.get("verdict") == "PROMOTE" and not row.get("go_at")
    ]


def daily_snapshot(repo_root: Path) -> dict[str, Any]:
    packets = examine_intake(repo_root)
    waiting = _awaiting(packets)
    pending_go = _pending_go(packets)
    current = waiting[0] if waiting else (pending_go[0] if pending_go else None)
    return {
        "intake": INTAKE_FILENAME,
        "north_star": NORTH_STAR,
        "awaiting": len(waiting),
        "packet": current,
        "verdicts": sorted(VERDICTS),
        "go_required": True,
        "executed": False,
    }
