# tests/swarm/pilot/test_memory.py
from unittest.mock import MagicMock, patch
from swarm.pilot import memory as m


# --- pause_state helpers ---

def test_get_pause_state_returns_active_default_when_no_row():
    c = MagicMock()
    c.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
    with patch.object(m, "_client", return_value=c):
        assert m.Memory().get_pause_state("phill") == "active"


def test_get_pause_state_returns_paused_hard_when_stored():
    c = MagicMock()
    c.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        {"pause_state": "paused-hard"}
    ]
    with patch.object(m, "_client", return_value=c):
        assert m.Memory().get_pause_state("phill") == "paused-hard"


def test_set_pause_state_calls_upsert():
    c = MagicMock()
    with patch.object(m, "_client", return_value=c):
        m.Memory().set_pause_state("phill", "paused-hard")
    c.table.return_value.upsert.assert_called_once()
    args, kwargs = c.table.return_value.upsert.call_args
    payload = args[0]
    assert payload["tenant_slug"] == "phill"
    assert payload["pause_state"] == "paused-hard"


# --- message-link helpers ---

def test_record_message_inserts_into_messages_table():
    c = MagicMock()
    c.table.return_value.insert.return_value.execute.return_value.data = [{"id": 1}]
    with patch.object(m, "_client", return_value=c):
        m.Memory().record_message(
            suggestion_id=42, chat_id=999, message_id=7, tenant_slug="phill"
        )
    c.table.assert_any_call("pilot_suggestion_messages")
    payload = c.table.return_value.insert.call_args.args[0]
    assert payload["suggestion_id"] == 42
    assert payload["chat_id"] == 999
    assert payload["message_id"] == 7
    assert payload["tenant_slug"] == "phill"


def test_get_message_for_suggestion_returns_row_or_none():
    c = MagicMock()
    c.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        {"chat_id": 999, "message_id": 7}
    ]
    with patch.object(m, "_client", return_value=c):
        r = m.Memory().get_message_for_suggestion(42)
    assert r == {"chat_id": 999, "message_id": 7}


def test_get_message_returns_none_when_no_row():
    c = MagicMock()
    c.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
    with patch.object(m, "_client", return_value=c):
        assert m.Memory().get_message_for_suggestion(99) is None


# --- is_blocked (ADR 004 §2) ---

def test_is_blocked_returns_true_when_never_rule_exists():
    c = MagicMock()
    c.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        {"rule": "never"}
    ]
    with patch.object(m, "_client", return_value=c):
        assert m.Memory().is_blocked("linear:RA-1234", "phill") is True


def test_is_blocked_returns_false_when_no_rule():
    c = MagicMock()
    c.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
    with patch.object(m, "_client", return_value=c):
        assert m.Memory().is_blocked("linear:RA-1234", "phill") is False


# --- has_pending_fingerprint (Task 5.2) ---

def test_has_pending_fingerprint_returns_true_when_row_exists():
    c = MagicMock()
    c.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        {"id": 1}
    ]
    with patch.object(m, "_client", return_value=c):
        assert m.Memory().has_pending_fingerprint("linear:stale_epic:abc") is True


def test_has_pending_fingerprint_returns_false_when_no_row():
    c = MagicMock()
    c.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
    with patch.object(m, "_client", return_value=c):
        assert m.Memory().has_pending_fingerprint("linear:stale_epic:abc") is False


# --- set_app_tenant RPC (ADR 004 §1) ---

def test_init_calls_set_app_tenant_rpc():
    c = MagicMock()
    with patch.object(m, "_client", return_value=c):
        m.Memory("phill")
    c.rpc.assert_called_with("set_app_tenant", {"slug": "phill"})
