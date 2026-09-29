"""SKILL_ROUTER off/shadow/on: shadow never changes the brief; on uses only the routed skill."""
import logging
import threading
import time

import pytest

from app.server import skill_routing

BRIEF = "write a session handoff before I stop for the day"


@pytest.fixture(autouse=True)
def no_live_jev(monkeypatch, tmp_path):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.setattr(skill_routing, "LEDGER", tmp_path / "ledger.sqlite")
    monkeypatch.setattr(skill_routing, "_CATALOGUE", None)
    monkeypatch.setattr(skill_routing, "_PINS", None)


def test_off_is_exactly_todays_context(monkeypatch):
    monkeypatch.setenv("SKILL_ROUTER", "off")
    assert skill_routing.skill_context(BRIEF, "feature") == skill_routing.legacy_context("feature")


def test_shadow_keeps_todays_context_and_logs_the_decision(monkeypatch, caplog):
    monkeypatch.setenv("SKILL_ROUTER", "shadow")
    with caplog.at_level(logging.INFO, logger="app.server.skill_routing"):
        out = skill_routing.skill_context(BRIEF, "feature")
        skill_routing.wait_for_shadow()
    assert out == skill_routing.legacy_context("feature")
    line = next(r.getMessage() for r in caplog.records if r.getMessage().startswith("skill_router {"))
    assert '"picked": ["session-handoff"]' in line and '"source": "lexical_fallback"' in line
    assert BRIEF not in line  # the request itself is never logged, only a hash


def test_on_uses_only_the_routed_skill(monkeypatch):
    monkeypatch.setenv("SKILL_ROUTER", "on")
    out = skill_routing.skill_context(BRIEF, "feature")
    assert "### Skill: session-handoff" in out and out.count("### Skill:") == 1


def test_router_error_falls_back_to_todays_context(monkeypatch, caplog):
    monkeypatch.setenv("SKILL_ROUTER", "on")

    def boom(_):
        raise RuntimeError("catalogue broke")

    monkeypatch.setattr(skill_routing, "_decide", boom)
    with caplog.at_level(logging.WARNING, logger="app.server.skill_routing"):
        assert skill_routing.skill_context(BRIEF, "feature") == skill_routing.legacy_context("feature")
    assert any("RuntimeError" in r.getMessage() for r in caplog.records)


def test_daily_cap_blocks_the_call_and_is_visible(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "not-a-real-key")
    monkeypatch.setenv("SKILL_ROUTER_REAL_DATA_EGRESS", "approved")
    monkeypatch.setenv("SKILL_ROUTER_DAILY_CAP_USD", "0")
    called = []
    monkeypatch.setattr("scripts.mission_control_jev_shadow.evaluate", lambda *a, **k: called.append(1))
    d = skill_routing._decide(BRIEF)
    assert called == [] and d.source == "lexical_fallback" and d.reason == "jev_error:CapReached"


def test_shadow_never_waits_for_a_slow_jev(monkeypatch):
    """Review P1-SHADOW-BLOCKS-BRIEF: a keyed shadow brief blocked 0.33 s on a 0.25 s Jev."""
    monkeypatch.setenv("SKILL_ROUTER", "shadow")
    monkeypatch.setenv("TYPESAFE_API_KEY", "not-a-real-key")
    monkeypatch.setenv("SKILL_ROUTER_REAL_DATA_EGRESS", "approved")
    release = threading.Event()

    def slow(*_a, **_k):
        release.wait(5)
        raise TimeoutError("jev slow")

    monkeypatch.setattr("scripts.mission_control_jev_shadow.evaluate", slow)
    started = time.monotonic()
    out = skill_routing.skill_context(BRIEF, "feature")
    elapsed = time.monotonic() - started
    release.set()
    skill_routing.wait_for_shadow()
    assert out == skill_routing.legacy_context("feature")
    assert elapsed < 0.2, f"shadow blocked the brief for {elapsed:.3f}s"


def test_a_busy_shadow_skips_rather_than_queues(monkeypatch, caplog):
    monkeypatch.setenv("SKILL_ROUTER", "shadow")
    release = threading.Event()
    calls = []

    def slow(raw):
        calls.append(raw)
        release.wait(5)
        raise RuntimeError("done")

    monkeypatch.setattr(skill_routing, "_decide", slow)
    with caplog.at_level(logging.INFO, logger="app.server.skill_routing"):
        skill_routing.skill_context(BRIEF, "feature")
        skill_routing.skill_context(BRIEF, "feature")
        release.set()
        skill_routing.wait_for_shadow()
    assert len(calls) == 1
    assert any("shadow_skipped_busy" in r.getMessage() for r in caplog.records)


def test_a_thread_that_cannot_start_neither_breaks_the_brief_nor_jams_shadow(monkeypatch, caplog):
    """Review P1-SHADOW-START-FAILS-BRIEF-AND-LEAKS-LOCK."""
    monkeypatch.setenv("SKILL_ROUTER", "shadow")

    def refuse(self):
        raise RuntimeError("thread unavailable")

    monkeypatch.setattr(threading.Thread, "start", refuse)
    with caplog.at_level(logging.WARNING, logger="app.server.skill_routing"):
        assert skill_routing.skill_context(BRIEF, "feature") == skill_routing.legacy_context("feature")
    assert not skill_routing._SHADOW_BUSY.locked()
    assert any("RuntimeError" in r.getMessage() for r in caplog.records)


def test_each_call_reserves_the_worst_case_before_it_is_sent(monkeypatch):
    """Review P1-JEV-RESERVATION-UNDERSTATES-MAX-COST: a 64k-token answer cost 2.7x a $0.001 cap."""
    from scripts.mission_control_jev_shadow import RESERVED_INPUT_TOKENS_PER_CALL, USD_PER_MILLION_INPUT

    worst = RESERVED_INPUT_TOKENS_PER_CALL * USD_PER_MILLION_INPUT / 1_000_000
    monkeypatch.setenv("TYPESAFE_API_KEY", "not-a-real-key")
    monkeypatch.setenv("SKILL_ROUTER_REAL_DATA_EGRESS", "approved")
    monkeypatch.setenv("SKILL_ROUTER_DAILY_CAP_USD", str(worst * 0.99))
    called = []
    monkeypatch.setattr("scripts.mission_control_jev_shadow.evaluate", lambda *a, **k: called.append(1))
    d = skill_routing._decide(BRIEF)
    assert called == [] and d.reason == "jev_error:CapReached"


@pytest.mark.parametrize("cap", ["nan", "inf", "-1", "lots"])
def test_a_cap_that_is_not_a_finite_amount_means_no_jev(monkeypatch, cap):
    """Review P1-DISPATCH-NAN-BYPASSES-SPEND-CAP: NaN makes every `spent + charge > cap` false."""
    monkeypatch.setenv("TYPESAFE_API_KEY", "not-a-real-key")
    monkeypatch.setenv("SKILL_ROUTER_REAL_DATA_EGRESS", "approved")
    monkeypatch.setenv("SKILL_ROUTER_DAILY_CAP_USD", cap)
    called = []
    monkeypatch.setattr("scripts.mission_control_jev_shadow.evaluate", lambda *a, **k: called.append(1))
    d = skill_routing._decide(BRIEF)
    assert called == [] and d.source == "lexical_fallback"


def test_production_pins_an_exact_router_phrase(monkeypatch, tmp_path):
    """Review P1-PRODUCTION-PIN-NOT-WIRED: only the unit test ever passed pins=."""
    index = tmp_path / "index.md"
    index.write_text('| Intent | Skill |\n|---|---|\n| "wrap up for today" | `session-handoff` |\n')
    monkeypatch.setenv("SKILL_ROUTER_INDEX", str(index))
    d = skill_routing._decide("Wrap up for today")
    assert d.source == "pin" and d.skills == ["session-handoff"]


def test_no_router_index_means_no_pins_not_an_error(monkeypatch, tmp_path):
    monkeypatch.setenv("SKILL_ROUTER_INDEX", str(tmp_path / "absent.md"))
    assert skill_routing._decide("wrap up for today").source != "pin"


REAL_BRIEF = "Write a session handoff for client Alice Brown at 15 Queen Street, Brisbane, claim 987654."


def test_a_real_brief_never_reaches_jev_without_founder_approval(monkeypatch):
    """Review P1-REAL-BRIEF-EGRESS-BYPASSES-SYNTHETIC-GATE: a key alone sent the brief to TypeSafe."""
    monkeypatch.setenv("TYPESAFE_API_KEY", "not-a-real-key")
    monkeypatch.delenv("SKILL_ROUTER_REAL_DATA_EGRESS", raising=False)
    sent = []
    monkeypatch.setattr("scripts.mission_control_jev_shadow.evaluate", lambda payload, *a, **k: sent.append(payload))
    d = skill_routing._decide(REAL_BRIEF)
    assert sent == [] and d.source == "lexical_fallback" and d.reason == "jev_unavailable"


@pytest.mark.parametrize("value", ["", "yes", "true", "1", "Approved "])
def test_only_the_exact_approval_value_opens_egress(monkeypatch, value):
    monkeypatch.setenv("TYPESAFE_API_KEY", "not-a-real-key")
    monkeypatch.setenv("SKILL_ROUTER_REAL_DATA_EGRESS", value)
    assert skill_routing.live_jev() is None


def test_approved_egress_reaches_jev(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "not-a-real-key")
    monkeypatch.setenv("SKILL_ROUTER_REAL_DATA_EGRESS", "approved")
    sent = []

    def fake(payload, *a, **k):
        sent.append(payload)
        raise TimeoutError("offline")

    monkeypatch.setattr("scripts.mission_control_jev_shadow.evaluate", fake)
    skill_routing._decide(REAL_BRIEF)
    assert len(sent) == 1


@pytest.fixture()
def trickle_server():
    """A local server that answers one byte every 0.1 s for 6 s: never silent for 3 s."""
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class Trickle(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            try:
                for _ in range(60):
                    self.wfile.write(b" ")
                    self.wfile.flush()
                    time.sleep(0.1)
            except OSError:
                pass

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Trickle)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}/"
    server.shutdown()


@pytest.fixture()
def header_trickle_server():
    """A raw socket server that sends the status line one byte every 0.1 s: urlopen never returns."""
    import socket as sk

    srv = sk.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen()
    stop = threading.Event()

    def serve():
        srv.settimeout(0.2)
        while not stop.is_set():
            try:
                conn, _ = srv.accept()
            except OSError:
                continue
            try:
                for ch in b"HTTP/1.1 200 OK\r\nX-Slow: " + b"a" * 100:
                    if stop.is_set():
                        break
                    conn.sendall(bytes([ch]))
                    time.sleep(0.1)
            except OSError:
                pass
            finally:
                conn.close()

    threading.Thread(target=serve, daemon=True).start()
    yield f"http://127.0.0.1:{srv.getsockname()[1]}/"
    stop.set()
    srv.close()


def _point_jev_at(monkeypatch, url):
    monkeypatch.setattr("scripts.mission_control_jev_shadow.API_URL", url)
    monkeypatch.setenv("TYPESAFE_API_KEY", "not-a-real-key")
    monkeypatch.setenv("SKILL_ROUTER_REAL_DATA_EGRESS", "approved")


def _jev_workers_stop_within(seconds):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline and any(t.name == "skill-router-jev" for t in threading.enumerate()):
        time.sleep(0.05)
    return not any(t.name == "skill-router-jev" for t in threading.enumerate())


def test_trickled_headers_are_cut_off_and_the_worker_stops(monkeypatch, header_trickle_server):
    """Review P1-JEV-HEADER-TRICKLE-LEAKS-WORKER: urlopen never returned, so nothing was closed."""
    import sqlite3

    _point_jev_at(monkeypatch, header_trickle_server)
    started = time.monotonic()
    d = skill_routing._decide(BRIEF)
    elapsed = time.monotonic() - started
    assert elapsed < skill_routing.JEV_DEADLINE_S + 0.8, f"Jev held the route for {elapsed:.2f}s"
    assert d.reason == "jev_error:TimeoutError"
    assert _jev_workers_stop_within(1.0), "the Jev worker is still reading after the deadline"
    with sqlite3.connect(skill_routing.LEDGER) as db:
        assert [r[0] for r in db.execute("SELECT status FROM calls")] == ["error"]


def test_a_trickling_jev_is_cut_off_at_the_wall_clock_deadline(monkeypatch, trickle_server):
    """Review P1-JEV-SOCKET-TIMEOUT-IS-NOT-WALL-CLOCK-DEADLINE: a byte every 0.1 s held the call 4.6 s."""
    _point_jev_at(monkeypatch, trickle_server)
    started = time.monotonic()
    d = skill_routing._decide(BRIEF)
    elapsed = time.monotonic() - started
    assert elapsed < skill_routing.JEV_DEADLINE_S + 0.8, f"Jev held the route for {elapsed:.2f}s"
    assert d.source == "lexical_fallback" and d.reason == "jev_error:TimeoutError"
    # The abandoned reader must actually stop, not trickle on in the background.
    assert _jev_workers_stop_within(1.0)


def test_a_trickling_jev_does_not_hold_the_shadow_lock(monkeypatch, trickle_server):
    _point_jev_at(monkeypatch, trickle_server)
    monkeypatch.setenv("SKILL_ROUTER", "shadow")
    skill_routing.skill_context(BRIEF, "feature")
    skill_routing.wait_for_shadow(timeout=skill_routing.JEV_DEADLINE_S + 2)
    assert not skill_routing._SHADOW_BUSY.locked()


def test_unknown_mode_means_shadow(monkeypatch):
    monkeypatch.setenv("SKILL_ROUTER", "yes please")
    assert skill_routing.mode() == "shadow"
