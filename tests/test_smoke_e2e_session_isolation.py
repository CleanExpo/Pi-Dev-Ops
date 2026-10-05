"""tests/test_smoke_e2e_session_isolation.py — unauth probes must run signed out.

Since 27c6f915 the backend revision check logs in before the horizontal run. It
shared the probe session, so every `auth: false` surface went out carrying the
login cookie and production smoke failed 48 checks per run from 19/09 while the
live site correctly refused them (401 / 307 when probed signed out).
"""
from __future__ import annotations

import sys
from http.cookiejar import Cookie
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import smoke_test_e2e as e2e  # noqa: E402


def _signed_in(session) -> bool:
    session.jar.set_cookie(Cookie(
        0, "pi_session", "x", None, False, "example.test", True, False, "/", True,
        True, None, False, None, None, {}))
    return True


def test_the_horizontal_run_starts_signed_out(monkeypatch):
    seen: list = []
    monkeypatch.setattr(e2e, "parse_e2e_args", lambda: type("A", (), {
        "password": "pw", "url": "https://example.test", "mode": "horizontal",
        "expected_sha": "abc", "deployment_timeout": 1})())
    monkeypatch.setattr(e2e, "_load_surface_map", lambda: {"horizontal": [{"path": "/x"}]})
    monkeypatch.setattr(e2e, "verify_e2e_revisions", lambda session, *_: _signed_in(session))
    monkeypatch.setattr(e2e, "run_horizontal", lambda session, *_: seen.append(len(session.jar)) or e2e.TestRun())
    monkeypatch.setattr(e2e, "report_totals", lambda runs: 0)
    assert e2e.main() == 0
    assert seen == [0], "the revision check's login leaked into the unauth probes"
