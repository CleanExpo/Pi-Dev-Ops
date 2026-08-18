"""The 15-min pulse must not claim it reached Linear when the post was refused.

Same defect class as the daily digest (commit ff0587b8): `_post_comment()` returns a
bool that the caller discarded, and success was reported anyway.

Two distinct instances, both fixed here:

  * `pulse_posted` was `bool(pulse_id)` — whether a pulse ISSUE ID was resolvable, not
    whether the comment posted. During a Linear outage the heartbeat logged
    `pulse_posted: True` while the single-pane-of-glass never updated.
  * The stuck-phase alert set `state["...:alerted"] = True` unconditionally, so a 🚨
    alert Linear refused was suppressed permanently — the flag says "already told them"
    forever and no later tick retries.

Mutation controls for these tests, both of which must make them fail:
  * restore `"pulse_posted": bool(pulse_id)`
  * move `state[f"{key}:alerted"] = True` out of the success branch
"""

from __future__ import annotations

import logging
from unittest.mock import patch

from app.server import linear_pulse


def _session(sid: str = "sess-abcdef12", phase: str = "build") -> dict:
    return {
        "id": sid,
        "issue_id": "issue-123",
        "phase": phase,
        "started_at": None,
        "last_log": "working",
    }


def _run(post_result: bool, state: dict | None = None, sessions: list | None = None):
    """Drive one `run_pulse()` tick with `_post_comment` forced to a known outcome."""
    saved: dict = {}

    def fake_save(s: dict) -> None:
        saved.clear()
        saved.update(s)

    with (
        patch.object(linear_pulse, "_post_comment", return_value=post_result),
        patch.object(linear_pulse, "_active_sessions", return_value=sessions or []),
        patch.object(linear_pulse, "_load_state", return_value=dict(state or {})),
        patch.object(linear_pulse, "_save_state", fake_save),
        patch.object(linear_pulse, "_pulse_issue_id", return_value="pulse-issue-1"),
        patch.object(linear_pulse, "_prune_stale_pulse_state", lambda *a, **k: None),
        # render_digest_text is imported function-locally inside run_pulse, so patch the
        # attribute the import resolves rather than sys.modules (see commit c8ff7336).
        patch("app.server.digest.render_digest_text", return_value="body"),
    ):
        return linear_pulse.run_pulse(), saved


def test_refused_pulse_comment_is_not_reported_as_posted(caplog) -> None:
    with caplog.at_level(logging.INFO, logger="pi-ceo.linear_pulse"):
        summary, _ = _run(post_result=False)

    assert summary["pulse_posted"] is False, (
        "pulse_posted must reflect whether the comment actually posted, not whether a "
        f"pulse issue id existed; got {summary!r}"
    )
    assert any(
        "portfolio-pulse comment FAILED to post" in r.getMessage()
        for r in caplog.records
    ), f"a refused pulse post must be logged as an error; got {[r.getMessage() for r in caplog.records]}"


def test_successful_pulse_comment_is_reported_as_posted() -> None:
    """Positive control — the working path must still report True."""
    summary, _ = _run(post_result=True)
    assert summary["pulse_posted"] is True


def test_refused_stuck_alert_is_not_marked_delivered(caplog) -> None:
    """A 🚨 alert Linear refused must stay un-alerted so the next tick retries."""
    sess = _session()
    key = f"stuck:{sess['id']}:{sess['phase']}"
    # Seen long enough ago to be well past the 30-min stuck threshold. Must be TRUTHY:
    # run_pulse treats a falsy last_seen as "first sighting" and resets it instead of
    # evaluating the stuck branch, so 0 would silently skip the code under test.
    stale_ts = 1  # 1970-01-01T00:00:01Z
    with caplog.at_level(logging.INFO, logger="pi-ceo.linear_pulse"):
        summary, saved = _run(
            post_result=False, state={key: stale_ts}, sessions=[sess]
        )

    assert not saved.get(f"{key}:alerted"), (
        "a stuck-phase alert that failed to post was marked delivered, which suppresses "
        "it permanently — no later tick will retry"
    )
    assert summary["stuck_alerts"] == 0, (
        f"stuck_alerts counted an alert that never reached Linear: {summary!r}"
    )
    assert any(
        "stuck-phase alert FAILED to post" in r.getMessage() for r in caplog.records
    )


def test_successful_stuck_alert_is_marked_delivered() -> None:
    """Positive control — a delivered alert must be recorded and counted once."""
    sess = _session()
    key = f"stuck:{sess['id']}:{sess['phase']}"
    summary, saved = _run(post_result=True, state={key: 1}, sessions=[sess])

    assert saved.get(f"{key}:alerted") is True
    assert summary["stuck_alerts"] == 1
