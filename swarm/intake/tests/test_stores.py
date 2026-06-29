"""Contract tests for the Supabase CIP data-plane adapters (stores.py).

A fake transport records every PostgREST call and serves canned rows, so
these assert column mapping, tenant scoping, and payload shape without a DB.
"""
from swarm.intake.margot_router import ThreadState
from swarm.intake.stores import (
    SupabaseIntakeBotRegistry,
    SupabaseMessagePersister,
    SupabaseProjectStore,
    SupabaseThreadStore,
)


class FakeSb:
    def __init__(self, *, client_bots=None, threads=None, projects=None):
        self.calls = []
        self._client_bots = client_bots or []
        self._threads = threads if threads is not None else []
        self._projects = projects if projects is not None else []

    def __call__(self, method, path, params=None, body=None, extra_headers=None):
        self.calls.append({"method": method, "path": path, "params": params or {},
                          "body": body, "extra_headers": extra_headers})
        if method == "GET" and path == "/intake_client_bots":
            sel = (params or {}).get("select", "")
            if "bot_username" in sel:          # registry listing
                return self._client_bots
            return [{"client_slug": "duncan-acme", "workspace_slug": "duncan-acme-ws"}]  # tenant
        if method == "GET" and path == "/intake_threads":
            return self._threads
        if method == "GET" and path == "/intake_projects":
            return self._projects
        return None

    def of(self, method, path):
        return [c for c in self.calls if c["method"] == method and c["path"] == path]


def _ID(prefix):
    return f"{prefix}_fixed"


# ── Registry ─────────────────────────────────────────────────────────────────
def test_registry_maps_active_bots():
    sb = FakeSb(client_bots=[{
        "id": "bot-1", "partner_id": "partner_duncan", "workspace_slug": "duncan-ws",
        "authorized_chat_ids": [100, 200], "bot_username": "DuncanIntakeBot",
    }])
    bots = list(SupabaseIntakeBotRegistry(sb_request=sb).list_active_client_intake_bots())
    assert len(bots) == 1
    b = bots[0]
    assert b.bot_id == "bot-1" and b.kind == "client_intake"
    assert b.partner_id == "partner_duncan" and b.bot_username == "DuncanIntakeBot"
    assert b.authorized_chat_ids == ("100", "200")  # coerced to str tuple
    # tenant scoping: only active bots queried
    assert sb.of("GET", "/intake_client_bots")[0]["params"]["status"] == "eq.active"


# ── ThreadStore ──────────────────────────────────────────────────────────────
def test_get_thread_maps_and_scopes_by_bot_and_chat():
    sb = FakeSb(threads=[{"id": "th-1", "project_id": "proj-1", "margot_state": "in_loop",
                          "status": "open", "last_message_at": "2026-06-29T00:00:00Z"}])
    ts = SupabaseThreadStore(sb_request=sb).get_thread_for_chat(bot_id="bot-1", chat_id="100")
    assert ts.thread_id == "th-1" and ts.project_id == "proj-1"
    assert ts.margot_state == "in_loop" and ts.last_inbound_at == "2026-06-29T00:00:00Z"
    p = sb.of("GET", "/intake_threads")[0]["params"]
    assert p["client_bot_id"] == "eq.bot-1" and p["chat_id"] == "eq.100"


def test_get_thread_returns_none_when_absent():
    assert SupabaseThreadStore(sb_request=FakeSb(threads=[])).get_thread_for_chat(
        bot_id="b", chat_id="c") is None


def test_upsert_thread_insert_fills_tenant_from_bot():
    sb = FakeSb()
    store = SupabaseThreadStore(sb_request=sb, id_factory=_ID)
    new = ThreadState(thread_id=None, project_id="proj-1", margot_state="classified")
    out = store.upsert_thread(bot_id="bot-1", chat_id="100", thread=new)
    assert out.thread_id == "it_fixed"
    post = sb.of("POST", "/intake_threads")[0]["body"]
    assert post["client_bot_id"] == "bot-1"
    assert post["client_slug"] == "duncan-acme"           # derived from bot
    assert post["workspace_slug"] == "duncan-acme-ws"
    assert post["margot_state"] == "classified"


def test_upsert_thread_update_patches_by_id():
    sb = FakeSb()
    store = SupabaseThreadStore(sb_request=sb)
    existing = ThreadState(thread_id="th-9", project_id="proj-1", margot_state="in_loop")
    store.upsert_thread(bot_id="bot-1", chat_id="100", thread=existing)
    assert sb.of("POST", "/intake_threads") == []
    patch = sb.of("PATCH", "/intake_threads")[0]
    assert patch["params"]["id"] == "eq.th-9"
    assert patch["body"]["margot_state"] == "in_loop"


# ── ProjectStore ─────────────────────────────────────────────────────────────
def test_list_open_projects_scoped():
    sb = FakeSb(projects=[{"id": "p1", "name": "Acme", "slug": "acme",
                           "owner_partner_id": "partner_duncan", "status": "open"}])
    out = list(SupabaseProjectStore(sb_request=sb).list_open_projects(workspace_slug="duncan-ws"))
    assert out[0].project_id == "p1" and out[0].slug == "acme"
    p = sb.of("GET", "/intake_projects")[0]["params"]
    assert p["workspace_slug"] == "eq.duncan-ws" and p["status"] == "eq.open"


def test_create_project_inserts_open_with_policy():
    sb = FakeSb()
    out = SupabaseProjectStore(sb_request=sb, id_factory=_ID).create_project(
        workspace_slug="duncan-ws", name="Acme", slug="acme",
        owner_partner_id="partner_duncan", first_idea="a portal")
    assert out.project_id == "ip_fixed"
    body = sb.of("POST", "/intake_projects")[0]["body"]
    assert body["status"] == "open" and body["approval_policy"] == "creator_only"
    assert body["description"] == "a portal"


def test_rename_project_patches():
    sb = FakeSb()
    SupabaseProjectStore(sb_request=sb).rename_project(
        project_id="p1", new_name="New", new_slug="new")
    patch = sb.of("PATCH", "/intake_projects")[0]
    assert patch["params"]["id"] == "eq.p1"
    assert patch["body"]["name"] == "New" and patch["body"]["slug"] == "new"


# ── MessagePersister ─────────────────────────────────────────────────────────
def test_record_inbound_persists_with_tenant_and_g3_partner():
    sb = FakeSb()
    SupabaseMessagePersister(sb_request=sb, id_factory=_ID).record_inbound(
        bot_id="bot-1", thread_id="th-1", chat_id="100", body="hi",
        submitted_by_partner_id="partner_duncan", telegram_message_id=5, telegram_update_id=42)
    body = sb.of("POST", "/intake_messages")[0]["body"]
    assert body["direction"] == "inbound" and body["author"] == "client"
    assert body["client_slug"] == "duncan-acme" and body["workspace_slug"] == "duncan-acme-ws"
    assert body["submitted_by_partner_id"] == "partner_duncan"   # G3: trust-derived, persisted as-is
    assert body["telegram_update_id"] == 42


def test_record_outbound_sets_direction_and_author():
    sb = FakeSb()
    SupabaseMessagePersister(sb_request=sb, id_factory=_ID).record_outbound(
        bot_id="bot-1", thread_id="th-1", chat_id="100", body="reply", author="board-summary")
    body = sb.of("POST", "/intake_messages")[0]["body"]
    assert body["direction"] == "outbound" and body["author"] == "board-summary"
    assert body["client_slug"] == "duncan-acme"


def test_missing_bot_tenant_raises():
    import pytest

    def empty_sb(method, path, params=None, body=None, extra_headers=None):
        return []  # tenant lookup finds no bot

    with pytest.raises(ValueError):
        SupabaseMessagePersister(sb_request=empty_sb).record_outbound(
            bot_id="ghost", thread_id="t", chat_id="c", body="x", author="system")
