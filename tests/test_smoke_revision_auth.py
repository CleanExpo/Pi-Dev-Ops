"""Revision admission must use authenticated health without leaking credentials."""
import io
import json
from pathlib import Path
import runpy
import urllib.request

import pytest

from scripts import deployment_revision


SHA = "a" * 40
PASSWORD = "synthetic-smoke-password"


class SmokeBoundaryReached(Exception):
    """Stop before the script performs any smoke actions."""


def run_preflight(monkeypatch, *, password=PASSWORD, revision=SHA):
    requests = []
    admitted = False

    class Opener:
        def open(self, request, **_kwargs):
            requests.append(request)
            if admitted:
                raise SmokeBoundaryReached
            payload = {"status": "ok"}
            if request.get_header("Authorization") == f"Bearer {PASSWORD}":
                payload["revision"] = revision
            response = io.BytesIO(json.dumps(payload).encode())
            response.status = 200
            return response

    original_wait = deployment_revision.wait_for_revision

    def verify(fetch, expected, **_kwargs):
        nonlocal admitted
        ticks = iter(range(10))
        result = original_wait(fetch, expected, timeout=1, interval=1,
                               monotonic=lambda: next(ticks), sleep=lambda _: None)
        admitted = True
        return result

    monkeypatch.setattr(urllib.request, "build_opener", lambda *_args: Opener())
    monkeypatch.setattr(deployment_revision, "wait_for_revision", verify)
    monkeypatch.setattr("sys.argv", ["smoke", "--url", "https://smoke.invalid",
                                    "--password", password, "--expected-sha", SHA])
    return requests


def test_revision_admission_authenticates_only_its_health_request(monkeypatch, capsys):
    requests = run_preflight(monkeypatch)
    with pytest.raises(SmokeBoundaryReached):
        runpy.run_path(str(Path(__file__).parents[1] / "scripts/smoke_test.py"),
                         run_name="scripts.__main__")
    assert len(requests) == 2
    assert requests[0].full_url == "https://smoke.invalid/health"
    assert requests[0].get_header("Authorization") == f"Bearer {PASSWORD}"
    assert requests[0].get_header("Cache-control") == "no-cache"
    assert requests[1].get_header("Authorization") is None
    output = capsys.readouterr()
    assert PASSWORD not in output.out + output.err


@pytest.mark.parametrize("password,revision", [
    ("", SHA), ("incorrect-password", SHA), (PASSWORD, None), (PASSWORD, "b" * 40),
])
def test_unverified_revision_stops_before_smoke_actions(monkeypatch, capsys, password, revision):
    requests = run_preflight(monkeypatch, password=password, revision=revision)
    with pytest.raises(SystemExit) as error:
        runpy.run_path(str(Path(__file__).parents[1] / "scripts/smoke_test.py"),
                         run_name="scripts.__main__")
    assert error.value.code == 1
    assert requests and all(request.full_url.endswith("/health") for request in requests)
    output = capsys.readouterr()
    assert "expected revision" in output.err
    assert PASSWORD not in output.out + output.err
    assert "incorrect-password" not in output.out + output.err


def test_revision_credential_is_not_forwarded_on_redirect(monkeypatch):
    requests = run_preflight(monkeypatch)
    with pytest.raises((SmokeBoundaryReached, SystemExit)):
        runpy.run_path(str(Path(__file__).parents[1] / "scripts/smoke_test.py"),
                         run_name="scripts.__main__")
    original = requests[0]
    assert original.get_header("Authorization") == f"Bearer {PASSWORD}"
    redirected = urllib.request.HTTPRedirectHandler().redirect_request(
        original, None, 302, "Found", {}, "https://other.invalid/health",
    )
    assert redirected.get_header("Authorization") is None
