"""Tests for bubus-typed wiring (DORMANT — BUBUS_ENABLED=0 by default)."""
import asyncio

import pytest

from swarm.board.wiring import (
    BoardDispatchEvent,
    PersonaOpinionEvent,
    build_board_bus,
    handle_dispatch,
)


def test_event_types_are_bubus_events():
    """BoardDispatchEvent + PersonaOpinionEvent are bubus BaseEvent subclasses."""
    from bubus import BaseEvent
    assert issubclass(BoardDispatchEvent, BaseEvent)
    assert issubclass(PersonaOpinionEvent, BaseEvent)


def test_event_construction():
    """Typed events validate their payload at construction time."""
    evt = BoardDispatchEvent(strategic_ask="ship the bubus surface")
    assert evt.strategic_ask == "ship the bubus surface"

    opin = PersonaOpinionEvent(persona="Contrarian", opinion="push back")
    assert opin.persona == "Contrarian"
    assert opin.opinion == "push back"


def test_build_board_bus_writes_wal(tmp_path):
    """build_board_bus() returns an EventBus with WAL persistence wired."""
    wal = tmp_path / "wal.jsonl"
    bus = build_board_bus(wal_path=wal)
    assert bus is not None
    # bubus normalises wal_path to a Path-like value.
    assert str(bus.wal_path).endswith("wal.jsonl")


def test_typed_event_roundtrip(tmp_path):
    """A BoardDispatchEvent flows through bubus with a registered handler."""
    wal = tmp_path / "wal.jsonl"
    bus = build_board_bus(wal_path=wal)

    async def _ack(evt: BoardDispatchEvent):
        return f"ack:{evt.strategic_ask}"

    bus.on(BoardDispatchEvent, _ack)
    evt = BoardDispatchEvent(strategic_ask="test dispatch")
    result = handle_dispatch(evt, bus=bus)
    assert result is not None
    assert "ack:test dispatch" in result
    assert wal.exists()


def test_handle_dispatch_no_bus_is_noop():
    """handle_dispatch() with no bus is a safe no-op (dormancy guard)."""
    evt = BoardDispatchEvent(strategic_ask="dormant cycle")
    assert handle_dispatch(evt, bus=None) is None


def test_legacy_dispatch_module_imports():
    """Legacy sentinel-string dispatch entrypoint still resolves."""
    from swarm.board import wiring
    assert callable(wiring.dispatch)
