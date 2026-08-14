"""/health must report GITHUB_TOKEN presence (RA-7220).

Every build starts with `git clone`, so without this token EVERY session dies in
the clone phase about 7 seconds in. 51 sessions failed that way over 7 days while
`/health` kept returning 200 — because the one credential gating all work was the
one credential `/health` did not report.

That is the failure CLAUDE.md already hardwired for `linear_api_key` ("autonomy.py
silently skips every poll when the key is missing while /health still returns
200"), reappearing on a different key. These tests stop it reappearing again.

The second half pins something subtler: `/health` and the clone path must apply
the SAME truthiness rule to the same variable. If they diverge, `/health` becomes
a confident second opinion that contradicts what the build actually does — worse
than not reporting it at all.
"""
from __future__ import annotations

import asyncio
import json

import pytest

from app.server import session_phases
from app.server.routes import health as health_route


class _StubRequest:
    """Minimal Request stand-in — /health only reads headers and cookies."""

    def __init__(self, headers: dict | None = None, cookies: dict | None = None):
        self.headers = headers or {}
        self.cookies = cookies or {}


def _health_payload(monkeypatch) -> dict:
    """Call /health and return the decoded body.

    TAO_PASSWORD is cleared so the handler serves the full payload: the auth gate
    is `if tao_password and not authed`, so an unset password falls through.
    """
    monkeypatch.delenv("TAO_PASSWORD", raising=False)
    response = asyncio.run(health_route.health(_StubRequest()))
    return json.loads(response.body)


# ── the field exists and tracks the variable ─────────────────────────────────

def test_health_reports_github_token_present(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_realtokenvalue")
    payload = _health_payload(monkeypatch)
    assert payload["github_token"] is True


def test_health_reports_github_token_missing(monkeypatch):
    """MUTATION CONTROL: drop the `github_token` key from the payload and this
    fails with KeyError — which is the whole point, since a week-long outage was
    invisible precisely because the key was absent."""
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    payload = _health_payload(monkeypatch)
    assert payload["github_token"] is False


def test_health_never_leaks_the_token_value(monkeypatch):
    """Presence is a bool. The value must not appear anywhere in the response."""
    secret = "ghp_thismustnotbeserialised"
    monkeypatch.setenv("GITHUB_TOKEN", secret)
    response = asyncio.run(health_route.health(_StubRequest()))
    assert secret not in response.body.decode()


def test_health_is_read_at_request_time(monkeypatch):
    """Railway env changes take effect on restart without a code deploy, so the
    value must not be captured at module import."""
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    assert _health_payload(monkeypatch)["github_token"] is False
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_setafterimport")
    assert _health_payload(monkeypatch)["github_token"] is True


# ── /health must agree with what the clone actually does ─────────────────────

@pytest.mark.parametrize(
    "value,expected",
    [
        ("ghp_real", True),
        ("", False),
        ("   ", False),       # whitespace-only
        ("\n", False),        # the trailing-newline hazard CLAUDE.md records
        ("ghp_real\n", True),  # real token with the newline Railway/Vercel append
    ],
)
def test_health_and_clone_path_agree(monkeypatch, value, expected):
    """The reported flag and `_git_clone_env`'s decision must never disagree.

    `_git_clone_env` returns None when it has no usable token — that is the
    branch that produces the unauthenticated clone. If /health said True while
    the clone path took that branch, /health would be actively misleading during
    exactly the outage it exists to surface.
    """
    monkeypatch.setenv("GITHUB_TOKEN", value)

    reported = _health_payload(monkeypatch)["github_token"]
    clone_env = session_phases._git_clone_env("https://github.com/CleanExpo/Pi-Dev-Ops")
    clone_will_authenticate = clone_env is not None

    assert reported is expected
    assert reported == clone_will_authenticate, (
        f"/health says github_token={reported} but the clone path "
        f"{'would' if clone_will_authenticate else 'would NOT'} authenticate"
    )


def test_non_github_remote_does_not_make_health_lie(monkeypatch):
    """Negative control: `_git_clone_env` also returns None for a non-github
    remote, but that is a URL fact, not a credential fact. /health reports on the
    VARIABLE, so it stays True — the agreement test above is scoped to github
    URLs on purpose.
    """
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_real")
    assert _health_payload(monkeypatch)["github_token"] is True
    assert session_phases._git_clone_env("https://gitlab.com/some/repo") is None
