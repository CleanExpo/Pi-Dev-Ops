"""RA-7546 — a wiped in-flight session respawns instead of failing A4."""
from __future__ import annotations

import json

from scripts.smoke_test_pipeline import (
    PipelineAssertions,
    poll_terminal,
    run_attempts,
    spawn_session,
)


class _ScriptedSession:
    def __init__(self, gets: list[tuple[int, str]], posts: list[tuple[int, str]]):
        self._gets = list(gets)
        self._posts = list(posts)
        self.streams = 0

    def login(self, _password: str) -> bool:
        return True

    def get(self, path: str) -> tuple[int, str]:
        if not self._gets:
            raise AssertionError(f"unexpected GET {path}")
        return self._gets.pop(0)

    def post(self, path: str, _body: dict) -> tuple[int, str]:
        if not self._posts:
            raise AssertionError(f"unexpected POST {path}")
        return self._posts.pop(0)

    def stream(self, _path: str, timeout_s: int):
        self.streams += 1
        yield {"type": "done"}


def _sessions_body(*rows: dict) -> str:
    return json.dumps(list(rows))


def _health(uptime: int) -> tuple[int, str]:
    return 200, json.dumps({"status": "ok", "uptime_s": uptime})


def test_spawn_502_is_bounce_not_a1_fail():
    s = _ScriptedSession(gets=[], posts=[(502, "Bad Gateway")])
    pa = PipelineAssertions()
    sid, kind = spawn_session(s, pa)
    assert sid is None
    assert kind == "bouncing"
    assert pa.errors == []


def test_poll_empty_healthy_list_is_wiped_not_lost_to_gc():
    s = _ScriptedSession(
        gets=[_health(200), (200, _sessions_body())],
        posts=[],
    )
    pa = PipelineAssertions()
    assert poll_terminal(s, "082af05e1ed7", pa, start=10**12) == "wiped"
    assert pa.errors == []
    assert not any("lost to GC" in err for err in pa.errors)


def test_run_attempts_respawns_after_wipe(monkeypatch):
    monkeypatch.setattr("scripts.smoke_test_pipeline.wait_until_settled", lambda *a, **k: True)
    monkeypatch.setattr("scripts.smoke_test_pipeline.max_respawns", lambda: 1)
    monkeypatch.setattr("scripts.smoke_test_pipeline.watch_stream", lambda *a, **k: None)
    monkeypatch.setattr("scripts.smoke_pipeline_resilience.wall_clock_s", lambda: 600)
    monkeypatch.setattr("scripts.smoke_test_pipeline.wall_clock_s", lambda: 600)

    complete = {"id": "cafebabe99", "status": "complete", "files_modified": 2}
    session = _ScriptedSession(
        gets=[
            _health(200), (200, _sessions_body()),  # first poll: wiped
            _health(200), (200, _sessions_body(complete)),  # second poll: done
        ],
        posts=[
            (200, json.dumps({"session_id": "082af05e1ed7"})),
            (200, json.dumps({"session_id": "cafebabe99"})),
        ],
    )
    pa, sid = run_attempts(session)
    assert sid == "cafebabe99"
    assert pa.reached_complete is True
    assert pa.errors == []
