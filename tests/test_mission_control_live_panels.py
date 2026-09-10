"""Mission Control live panels — the fields the panels actually read.

The existing observability test covers the action ledger's triage logic. Nothing
covered the four panels that read session and pulse state, and every one of them
read a field no code ever writes:

  B  throughput / recent completions read `completed_at`; BuildSession had no
     such field and nothing set one, so both were permanently empty.
  C  the pulse reader resolved <repo>/app/.harness/... while linear_pulse writes
     <repo>/.harness/..., so the heartbeat was permanently empty.
  D  `started_at` is a float epoch, parsed as an ISO string inside a swallowed
     except, so elapsed_s was always 0; `last_log_line` does not exist on the
     dataclass (the field is `output_lines`), so the tail was always "".
  E  the action ledger instructs an operator to repair `supabase_log.health_check`,
     a symbol that did not exist.

The smoke gate passed throughout, because it asserted key NAMES only.

These tests are written to FAIL against the pre-fix code.
"""

from __future__ import annotations

import importlib
import re
import time
from datetime import datetime, timezone, timedelta

import pytest

from app.server import linear_pulse, session_model
from app.server.routes import mission_control
from app.server.session_model import BuildSession, _sessions


@pytest.fixture(autouse=True)
def _clean_session_store():
    """The session store is process-global; leave it exactly as found."""
    before = dict(_sessions)
    _sessions.clear()
    yield
    _sessions.clear()
    _sessions.update(before)


# ── B: a completed session must be countable ──────────────────────────────────

def test_build_session_records_when_it_completed():
    """Without a completed_at field there is nothing for throughput to read."""
    assert "completed_at" in BuildSession.__dataclass_fields__, (
        "BuildSession has no completed_at field, so every throughput bucket and "
        "every recent completion is empty by construction"
    )


def test_marking_a_session_complete_stamps_the_completion_time():
    """The one place a session goes terminal must record when."""
    sess = BuildSession(repo_url="https://github.com/CleanExpo/Pi-Dev-Ops")
    session_model.mark_complete(sess)
    assert sess.status == "complete"
    assert isinstance(sess.completed_at, float)
    assert abs(sess.completed_at - time.time()) < 5


def test_completed_sessions_appear_in_throughput_and_recent_completions():
    for i in range(2):
        sess = BuildSession(repo_url="https://github.com/CleanExpo/Pi-Dev-Ops")
        session_model.mark_complete(sess)
        _sessions[f"session-{i}"] = sess

    buckets = mission_control._hourly_throughput_24h()
    assert len(buckets) == 24
    assert sum(buckets) == 2, f"two sessions completed just now, got {sum(buckets)}"
    assert buckets[-1] == 2, "both completions belong in the current hour bucket"

    recent = mission_control._recent_completions()
    assert len(recent) == 2
    assert all(r["completed_at"] for r in recent), "completed_at must reach the panel"


def test_a_completion_older_than_24h_is_not_counted():
    """Negative control: the bucket window must actually exclude things."""
    sess = BuildSession(repo_url="https://github.com/CleanExpo/Pi-Dev-Ops")
    session_model.mark_complete(sess)
    sess.completed_at = (datetime.now(timezone.utc) - timedelta(hours=30)).timestamp()
    _sessions["old"] = sess
    assert sum(mission_control._hourly_throughput_24h()) == 0


# ── D: a running session must report real elapsed time and a real log tail ────

def test_active_session_reports_real_elapsed_seconds_and_log_tail():
    sess = BuildSession(repo_url="https://github.com/CleanExpo/Pi-Dev-Ops")
    sess.status = "building"
    sess.started_at = time.time() - 90          # epoch float, as the app writes it
    sess.output_lines = ["cloning…", "installing…", "running the build"]
    _sessions["live-one"] = sess

    active = mission_control._active_sessions()
    assert len(active) == 1
    row = active[0]
    assert row["elapsed_s"] >= 90, (
        f"started 90s ago, panel says {row['elapsed_s']}s — started_at is an epoch "
        "float and was being parsed as an ISO string inside a swallowed except"
    )
    assert row["last_log_tail"] == "running the build", (
        "the tail reads last_log_line, which does not exist; the field is output_lines"
    )


def test_active_session_with_no_output_has_an_empty_tail_not_a_crash():
    sess = BuildSession(repo_url="https://github.com/CleanExpo/Pi-Dev-Ops")
    sess.status = "building"
    sess.started_at = time.time()
    _sessions["quiet"] = sess
    assert mission_control._active_sessions()[0]["last_log_tail"] == ""


# ── Timestamp coercion (independent review round 1, P1) ──────────────────────

def test_all_digit_iso_dates_are_not_read_as_epoch_seconds():
    """`float("20260910")` succeeds, so trying epoch-first turned the basic ISO
    spelling into 1970-08-23. Found by independent review; reproduced before
    this test existed."""
    from app.server.routes.mission_control_sessions import as_datetime

    assert as_datetime("20260910").date().isoformat() == "2026-09-10"
    assert as_datetime("20260910T120000").date().isoformat() == "2026-09-10"
    assert as_datetime("2026-09-10T12:00:00+00:00").date().isoformat() == "2026-09-10"


def test_a_number_too_small_to_be_a_timestamp_is_unknown_not_1970():
    """A bare "2026" is not a valid ISO date and is not a plausible epoch either.
    Guessing 1970 puts a wrong date on the panel; None says "unknown", which is
    what it is."""
    from app.server.routes.mission_control_sessions import as_datetime

    assert as_datetime("2026") is None
    assert as_datetime(2026) is None


def test_an_unset_timestamp_is_unknown_not_1970():
    """BuildSession.started_at defaults to 0.0 meaning "never started". The old
    code guarded this with a falsy check; coercion must keep that, or every
    unstarted session reports ~56 years of elapsed time."""
    from app.server.routes.mission_control_sessions import as_datetime

    assert as_datetime(0.0) is None
    assert as_datetime(0) is None


def test_unstarted_session_reports_zero_elapsed_not_five_decades():
    sess = BuildSession(repo_url="https://github.com/CleanExpo/Pi-Dev-Ops")
    sess.status = "created"  # started_at is still the 0.0 default
    _sessions["unstarted"] = sess
    assert mission_control._active_sessions()[0]["elapsed_s"] == 0


def test_epoch_values_still_parse_as_epochs():
    """Negative control for the fixes above: the epoch path must still work."""
    from app.server.routes.mission_control_sessions import as_datetime

    assert as_datetime("1757483000.5").year == 2025
    assert as_datetime(1757483000.5).year == 2025
    assert as_datetime("not-a-time") is None
    assert as_datetime(None) is None


# ── Terminal statuses other than 'complete' (review round 1, P1) ─────────────

def test_a_failed_session_also_records_when_it_ended():
    """mark_complete hardcoded 'complete', so nothing else that ends a session
    could record a timestamp without lying about its status."""
    sess = BuildSession(repo_url="https://github.com/CleanExpo/Pi-Dev-Ops")
    session_model.mark_terminal(sess, "failed")
    assert sess.status == "failed"
    assert isinstance(sess.completed_at, float)


def test_a_failed_session_is_not_counted_as_throughput():
    """Negative control: recording WHEN it ended must not make it look shipped."""
    sess = BuildSession(repo_url="https://github.com/CleanExpo/Pi-Dev-Ops")
    session_model.mark_terminal(sess, "failed")
    _sessions["failed-one"] = sess
    assert sum(mission_control._hourly_throughput_24h()) == 0
    assert mission_control._recent_completions() == []


# ── C: the pulse reader must read the file the pulse writer writes ────────────

def test_pulse_reads_the_path_the_writer_writes(tmp_path, monkeypatch):
    state_dir = tmp_path / ".harness"
    state_dir.mkdir()
    state_file = state_dir / "linear-pulse-state.json"
    state_file.write_text('{"pulse_issue_id": "PULSE-1", "last_at": "2026-09-10T00:00:00+00:00"}')

    # Point both sides at the same fake repo root. The writer derives its path
    # from the repo root; the reader must derive it the same way.
    monkeypatch.setattr(mission_control, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(linear_pulse, "_STATE_FILE", state_file, raising=False)

    pulse = mission_control._pulse_status()
    assert pulse["pulse_issue_id"] == "PULSE-1", (
        "the reader resolved <repo>/app/.harness/ (parents[2]) while the writer "
        "uses <repo>/.harness/ — _repo_root() in the same file already gets this right"
    )


def test_pulse_writer_and_reader_agree_on_the_real_repo_path():
    """No monkeypatching: the two real paths must be the same file."""
    assert linear_pulse._STATE_FILE == mission_control._repo_root() / ".harness" / "linear-pulse-state.json"


# ── E: the ledger must not prescribe a repair to a symbol that does not exist ──

_SYMBOL = re.compile(r"\b([a-z_][a-z0-9_]*)\.([a-z_][a-z0-9_]*)\b")


def test_every_prescribed_next_action_names_a_symbol_that_resolves():
    """The ledger is the operator's instruction sheet. An instruction pointing at
    a symbol that does not exist is worse than no instruction."""
    unresolved = []
    for component, meta in mission_control._OBSERVABILITY_ACTIONS.items():
        for module_name, attr in _SYMBOL.findall(meta["next_action"]):
            try:
                module = importlib.import_module(f"app.server.{module_name}")
            except ModuleNotFoundError:
                continue  # not one of ours — a filename, a path fragment
            if not hasattr(module, attr):
                unresolved.append(f"{component}: app.server.{module_name}.{attr}")
    assert not unresolved, f"ledger prescribes symbols that do not exist: {unresolved}"


def test_supabase_health_check_exists_and_reports_without_credentials():
    from app.server import supabase_health

    assert hasattr(supabase_health, "health_check")
    result = supabase_health.health_check()
    assert set(result) >= {"ok", "observed", "detail"}
    assert isinstance(result["ok"], bool)
