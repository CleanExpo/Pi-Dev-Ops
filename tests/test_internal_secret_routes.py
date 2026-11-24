"""RA-8408 — every route that takes X-Pi-CEO-Secret accepts the current key and a next key.

HTTP only. The owner module (app/server/internal_secret.py) is never imported at file
level, so this file also runs on the code before the change: there the "next" tests
fail with a refusal, which is the red-first proof (recipes/red_first.py).

Each route is sent one well-formed request three times: a wrong key (401, and no
collaborator reached), the current key and the next key (the route's own success
status, and its stubbed collaborator reached). Collaborators are stubbed through the
consumer's own module reference, and every outbound credential is blanked, so a missed
stub fails closed instead of reaching the network.
"""
from __future__ import annotations

import importlib
import importlib.util
import sys
import types
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

CURRENT = "fake-current-key-aaaaaaaaaaaaaaaaaaaaaa"
NEXT = "fake-next-key-bbbbbbbbbbbbbbbbbbbbbbbbbbbb"
WRONG = "fake-wrong-key-cccccccccccccccccccccccc"
READ_ONLY = "fake-read-only-key-dddddddddddddddddddd"
NEXT_ENV, READ_ENV = "TAO_INTERNAL_WEBHOOK_SECRET_NEXT", "TAO_FLEET_READ_SECRET"
OUTBOUND = ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "LINEAR_API_KEY", "TELEGRAM_BOT_TOKEN")
EVENT = {"session_id": "s1", "seq": 1, "kind": "tool", "at": "2026-11-17T00:00:00Z"}


@pytest.fixture(autouse=True, scope="module")
def _import_neutral():
    """Leave app.server.routes as found: other test files re-import route modules by name."""
    before = {name for name in sys.modules if name.startswith("app.server.routes.")}
    yield
    package = sys.modules.get("app.server.routes")
    for name in [n for n in sys.modules if n.startswith("app.server.routes.") and n not in before]:
        sys.modules.pop(name, None)
        if package is not None and hasattr(package, name.rsplit(".", 1)[1]):
            delattr(package, name.rsplit(".", 1)[1])


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    from app.server import config
    for name in (NEXT_ENV, READ_ENV, "OPENROUTER_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    for name in OUTBOUND:
        monkeypatch.setattr(config, name, "", raising=False)
    if importlib.util.find_spec("app.server.internal_secret") is not None:
        importlib.import_module("app.server.internal_secret")._reset_log_state()


def _spy(calls, ret):
    def stub(*args, **kwargs):
        calls.append(args)
        return ret
    return stub


def _aspy(calls, ret):
    async def stub(*args, **kwargs):
        calls.append(args)
        return ret
    return stub


def _mesh(mp, tmp, calls):
    from app.server import mesh_dispatch_service, mesh_lanes, mesh_queue_cache
    from app.server.routes import mesh, mesh_brief, mesh_lane_events, mesh_ship
    sb = _spy(calls, (200, "[]"))
    for module in (mesh, mesh_ship.mesh_routes, mesh_lane_events._mesh, mesh_lane_events):
        mp.setattr(module, "_sb", sb)
    mp.setattr(mesh, "_reap_stale_claims", _spy(calls, []))
    mp.setattr(mesh, "_reap_sweep_best_effort", _spy(calls, None))
    mp.setattr(mesh_dispatch_service, "run_dispatch_tick", _spy(calls, {"dispatched": []}))
    mp.setattr(mesh_queue_cache, "candidates", _spy(calls, ([], {})))
    mp.setattr(mesh_lanes, "repeat_claimed", _spy(calls, None))
    return [mesh.router, mesh_ship.router, mesh_lane_events.router, mesh_brief.router]


def _conversations(mp, tmp, calls):
    from app.server import conversation_store as store
    from app.server.routes import conversations
    mp.setenv("CONVERSATION_SYNC_ENABLED", "1")
    mp.setattr(conversations, "_REDACTION_BANK_COMPLETE", True)
    mp.setattr(store, "save_conversation_digests", lambda rows: calls.append(rows) or len(rows))
    mp.setattr(store, "search_conversation_digests", _spy(calls, []))
    mp.setattr(store, "recent_conversation_digests", _spy(calls, []))
    return [conversations.router]


def _cost_report(mp, tmp, calls):
    import swarm
    from app.server.routes import cost_report
    fake = types.ModuleType("swarm.budget_tracker")
    fake.by_provider_24h = fake.by_role_24h = _spy(calls, {})
    fake.daily_total_usd = _spy(calls, 0.0)
    mp.setitem(sys.modules, "swarm.budget_tracker", fake)
    mp.setattr(swarm, "budget_tracker", fake, raising=False)
    return [cost_report.router]


def _routing(mp, tmp, calls):
    from app.server.routes import routing
    mp.setattr(routing, "_cost_today_by_role", _spy(calls, (None, "stubbed in test")))
    return [routing.router]


def _delegate(mp, tmp, calls):
    import anthropic
    from app.server import config
    from app.server.routes import delegate
    mp.setattr(delegate, "_require_delegate_transport", lambda: None)
    mp.setattr(config, "ANTHROPIC_API_KEY", "fake-model-key-for-tests", raising=False)
    message = SimpleNamespace(content=[SimpleNamespace(text="done")],
                              usage=SimpleNamespace(input_tokens=1, output_tokens=1))
    client = SimpleNamespace(messages=SimpleNamespace(create=_spy(calls, message)))
    mp.setattr(anthropic, "Anthropic", lambda **kwargs: client)
    return [delegate.router]


def _margot(mp, tmp, calls):
    import swarm
    from app.server.routes import margot
    bot = types.ModuleType("swarm.margot_bot")
    bot.handle_turn = _aspy(calls, SimpleNamespace(margot_text="ok", turn_id="t1"))
    mp.setitem(sys.modules, "swarm.margot_bot", bot)
    mp.setattr(swarm, "margot_bot", bot, raising=False)
    whisper = types.ModuleType("app.server.provider_whisper")
    whisper.transcribe = _aspy(calls, (0, "hello", 0.0, None))
    mp.setitem(sys.modules, "app.server.provider_whisper", whisper)
    mp.setattr(margot, "_download_telegram_file", _aspy(calls, tmp / "voice.ogg"))
    return [margot.router]


def _webhooks(mp, tmp, calls):
    from app.server import config
    from app.server.routes import webhooks
    mp.setattr(config, "DATA_DIR", str(tmp / "data" / "app"))
    real_replace = webhooks.os.replace
    mp.setattr(webhooks.os, "replace", lambda src, dst: calls.append(dst) or real_replace(src, dst))
    seeded = tmp / ".harness" / "workspace-intel"
    seeded.mkdir(parents=True)
    (seeded / "2026-01-01.jsonl").write_text('{"ts": "2026-01-01T00:00:00Z"}\n')
    return [webhooks.router]


def _wiki(mp, tmp, calls):
    from app.server import wiki_source_store as store
    from app.server.routes import wiki_sources
    mp.setenv("WIKI_SOURCES_ENABLED", "1")
    mp.setattr(wiki_sources, "_project_ids", lambda: set())
    for name, ret in (("stage_source", True), ("list_sources", []),
                      ("active_requirements", []), ("save_requirement", True)):
        mp.setattr(store, name, _spy(calls, ret))
    return [wiki_sources.router]


FAMILIES = {"mesh": _mesh, "conversations": _conversations, "cost_report": _cost_report,
            "routing": _routing, "delegate": _delegate, "margot": _margot,
            "webhooks": _webhooks, "wiki": _wiki}

# (id, family, method, path, request kwargs, expected status for an accepted key)
ROUTES = [
    ("conversations-ingest", "conversations", "POST", "/api/conversations/ingest", {"json": {"machine": "m1", "digests": []}}, 200),
    ("conversations-search", "conversations", "GET", "/api/conversations/search", {"params": {"q": "x"}}, 200),
    ("conversations-recent", "conversations", "GET", "/api/conversations/recent", {}, 200),
    ("cost-report", "cost_report", "GET", "/api/cost-report", {}, 200),
    ("routing", "routing", "GET", "/api/routing", {}, 200),
    ("delegate", "delegate", "POST", "/api/margot/delegate", {"json": {"task_type": "docs", "spec": "s", "chat_id": "1"}}, 200),
    ("margot-turn", "margot", "POST", "/api/margot/turn", {"json": {"chat_id": "1", "user_text": "hi"}}, 200),
    ("margot-voice", "margot", "POST", "/api/margot/voice", {"json": {"chat_id": "1", "file_id": "f1"}}, 200),
    ("mesh-heartbeat", "mesh", "POST", "/api/mesh/heartbeat", {"json": {"host": "m1"}}, 200),
    ("mesh-claims", "mesh", "GET", "/api/mesh/claims", {}, 200),
    ("mesh-claim-update", "mesh", "POST", "/api/mesh/claim/update", {"json": {"linear_id": "RA-1", "state": "working"}}, 200),
    ("mesh-claims-reap", "mesh", "POST", "/api/mesh/claims/reap", {}, 200),
    ("mesh-dispatch", "mesh", "POST", "/api/mesh/dispatch", {"json": {}}, 200),
    ("mesh-claim-self", "mesh", "POST", "/api/mesh/claim/self", {"json": {"host": "m1"}}, 200),
    ("mesh-lane-events-post", "mesh", "POST", "/api/mesh/lane-events", {"json": {"host": "m1", "events": [EVENT]}}, 200),
    ("mesh-ship", "mesh", "POST", "/api/mesh/ship", {"json": {"machine": "m1", "repo": "o/r"}}, 200),
    ("mesh-claim-brief", "mesh", "GET", "/api/mesh/claim/brief", {"params": {"linear_id": "RA-1", "host": "m1", "claim_id": "c1"}}, 409),
    ("webhook-morning-intel", "webhooks", "POST", "/api/webhook/morning-intel", {"json": {"date": "2026-11-17"}}, 200),
    ("webhook-routine-complete", "webhooks", "POST", "/api/webhook/routine-complete",
     {"json": {"routine_name": "r", "repo": "o/r", "trigger": "api", "status": "success", "duration_s": 1}}, 200),
    ("webhook-workspace-intel-refresh", "webhooks", "POST", "/api/webhook/workspace-intel-refresh",
     {"json": {"items": [{"title": "t", "link": "https://example.invalid/a"}]}}, 200),
    ("workspace-intel", "webhooks", "GET", "/api/workspace-intel", {}, 200),
    ("wiki-sources-upload", "wiki", "POST", "/api/wiki/sources/upload", {"json": {"filename": "note.md", "body_md": "b"}}, 200),
    ("wiki-sources", "wiki", "GET", "/api/wiki/sources", {}, 200),
    ("wiki-requirements-get", "wiki", "GET", "/api/wiki/requirements", {"params": {"project_key": "p"}}, 200),
    ("wiki-requirements-put", "wiki", "PUT", "/api/wiki/requirements", {"json": {"project_key": "p", "slug": "s", "title": "t"}}, 200),
    ("mesh-fleet", "mesh", "GET", "/api/mesh/fleet", {}, 200),
    ("mesh-lane-events-get", "mesh", "GET", "/api/mesh/lane-events", {}, 200),
]
IDS = [row[0] for row in ROUTES]
BY_ID = {row[0]: row for row in ROUTES}
# One write route per label the owner logs under (routing logs as cost_report).
FAMILY_ROWS = [BY_ID[i] for i in ("mesh-heartbeat", "conversations-ingest", "cost-report", "delegate",
                                  "margot-turn", "webhook-morning-intel", "wiki-sources-upload")]
FAMILY_IDS = [row[0] for row in FAMILY_ROWS]
READ_ROWS = [BY_ID["mesh-fleet"], BY_ID["mesh-lane-events-get"]]


def _send(row, mp, tmp, key, current=CURRENT):
    from app.server import config
    from app.server.auth import require_rate_limit
    mp.setattr(config, "INTERNAL_WEBHOOK_SECRET", current)
    calls: list = []
    app = FastAPI()
    for router in FAMILIES[row[1]](mp, tmp, calls):
        app.include_router(router)
    app.dependency_overrides[require_rate_limit] = lambda: True
    headers = {} if key is None else {"X-Pi-CEO-Secret": key}
    resp = TestClient(app).request(row[2], row[3], headers=headers, **row[4])
    return resp, calls


def _reached(resp, calls) -> bool:
    """A collaborator ran; for the workspace-intel read, the seeded batch came back."""
    body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
    return bool(calls) or (isinstance(body, dict) and body.get("total") == 1)


def _assert_accepted(row, resp, calls):
    assert resp.status_code == row[5], resp.text
    assert _reached(resp, calls)
    if row[1] == "delegate":
        assert resp.json()["status"] == "complete"


@pytest.mark.parametrize("row", ROUTES, ids=IDS)
def test_ac01_wrong_key_is_refused(row, monkeypatch, tmp_path):
    resp, calls = _send(row, monkeypatch, tmp_path, WRONG)
    assert resp.status_code == 401, resp.text
    assert not _reached(resp, calls)


@pytest.mark.parametrize("row", ROUTES, ids=IDS)
def test_ac01_current_key_is_accepted(row, monkeypatch, tmp_path):
    resp, calls = _send(row, monkeypatch, tmp_path, CURRENT)
    _assert_accepted(row, resp, calls)


@pytest.mark.parametrize("row", ROUTES, ids=IDS)
def test_ac01_next_key_is_accepted(row, monkeypatch, tmp_path):
    monkeypatch.setenv(NEXT_ENV, NEXT)
    resp, calls = _send(row, monkeypatch, tmp_path, NEXT)
    _assert_accepted(row, resp, calls)


@pytest.mark.parametrize("next_value", [None, "", "   "], ids=["unset", "empty", "blank"])
@pytest.mark.parametrize("header", [None, "", "   "], ids=["absent", "empty", "blank"])
@pytest.mark.parametrize("row", FAMILY_ROWS, ids=FAMILY_IDS)
def test_ac05_empty_or_blank_header_is_refused(row, header, next_value, monkeypatch, tmp_path):
    if next_value is not None:
        monkeypatch.setenv(NEXT_ENV, next_value)
    resp, calls = _send(row, monkeypatch, tmp_path, header)
    assert resp.status_code == 401, resp.text
    assert not _reached(resp, calls)


@pytest.mark.parametrize("row", FAMILY_ROWS + READ_ROWS, ids=FAMILY_IDS + ["mesh-fleet", "lane-events-get"])
def test_ac05_next_alone_with_current_empty_is_503(row, monkeypatch, tmp_path):
    monkeypatch.setenv(NEXT_ENV, NEXT)
    resp, calls = _send(row, monkeypatch, tmp_path, NEXT, current="")
    assert resp.status_code == 503, resp.text
    assert not calls


@pytest.mark.parametrize("row", ROUTES, ids=IDS)
def test_ac05_non_ascii_header_is_401(row, monkeypatch, tmp_path):
    monkeypatch.setenv(NEXT_ENV, NEXT)
    resp, calls = _send(row, monkeypatch, tmp_path, "fake-key-éé".encode("utf-8"))
    assert resp.status_code == 401, resp.text
    assert not calls


@pytest.mark.parametrize("row", [BY_ID["mesh-heartbeat"], BY_ID["cost-report"]], ids=["mesh-heartbeat", "cost-report"])
def test_ac07_read_only_key_is_refused_on_write_routes(row, monkeypatch, tmp_path):
    monkeypatch.setenv(READ_ENV, READ_ONLY)
    resp, calls = _send(row, monkeypatch, tmp_path, READ_ONLY)
    assert resp.status_code == 401, resp.text
    assert not calls


@pytest.mark.parametrize("current", [CURRENT, ""], ids=["with-current", "read-only-alone"])
@pytest.mark.parametrize("row", READ_ROWS, ids=["mesh-fleet", "lane-events-get"])
def test_ac07_read_only_key_opens_the_two_read_routes(row, current, monkeypatch, tmp_path):
    monkeypatch.setenv(READ_ENV, READ_ONLY)
    resp, calls = _send(row, monkeypatch, tmp_path, READ_ONLY, current=current)
    assert resp.status_code == 200, resp.text
    assert calls
