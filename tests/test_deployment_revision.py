"""A healthy old deployment must never verify a new release."""
import pytest

from scripts.deployment_revision import wait_for_revision


SHA = "a" * 40


class Clock:
    now = 0.0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def wait(fetch, expected=SHA, timeout=3):
    clock = Clock()
    return wait_for_revision(
        fetch, expected, timeout=timeout, interval=1,
        monotonic=clock.monotonic, sleep=clock.sleep,
    )


def test_matching_healthy_revision_succeeds():
    assert wait(lambda: (200, {"revision": SHA})) == SHA


@pytest.mark.parametrize("payload", [{}, {"revision": "a" * 7}, {"revision": "b" * 40}, []])
def test_missing_or_stale_revision_cannot_pass(payload):
    with pytest.raises(TimeoutError, match="expected revision"):
        wait(lambda: (200, payload))


@pytest.mark.parametrize("status", [0, 301, 401, 500, 503])
def test_unhealthy_response_cannot_pass_even_with_matching_revision(status):
    with pytest.raises(TimeoutError):
        wait(lambda: (status, {"revision": SHA}))


def test_polls_until_the_expected_deployment_is_ready():
    responses = iter([(200, {"revision": "b" * 40}), (503, {}), (200, {"revision": SHA})])
    assert wait(lambda: next(responses)) == SHA


def test_transient_network_error_can_recover():
    calls = 0

    def fetch():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("connection refused")
        return 200, {"revision": SHA}

    assert wait(fetch) == SHA


@pytest.mark.parametrize("expected", ["", "main", "a" * 7, "g" * 40])
def test_invalid_expected_revision_fails_before_any_network_call(expected):
    def fetch():
        pytest.fail("invalid revision must not make a request")

    with pytest.raises(ValueError):
        wait(fetch, expected)


def test_json_response_and_case_are_normalized():
    assert wait(lambda: (200, '{"revision": "' + SHA.upper() + '"}')) == SHA


def test_non_json_error_payload_times_out_without_echoing_its_body():
    with pytest.raises(TimeoutError) as error:
        wait(lambda: (200, "private response detail"))
    assert "private response detail" not in str(error.value)


@pytest.mark.parametrize("stale_component", ["frontend", "backend"])
def test_e2e_never_runs_smoke_surfaces_on_a_stale_deployment(monkeypatch, stale_component):
    from scripts import smoke_test_e2e as smoke

    class Session:
        def __init__(self, _url):
            pass

        def request(self, _method, path, **_kwargs):
            component = "frontend" if path == "/api/revision" else "backend"
            return 200, {"revision": "b" * 40 if component == stale_component else SHA}

        def login(self, _password):
            return True

    monkeypatch.setattr(smoke, "Session", Session)
    monkeypatch.setattr(smoke, "wait_for_revision", lambda fetch, expected, **kw: wait(fetch, expected))
    monkeypatch.setattr(smoke, "_load_surface_map", lambda: {"horizontal": [{}]})
    monkeypatch.setattr(smoke, "run_horizontal", lambda *args: pytest.fail("stale deployment reached smoke actions"))
    monkeypatch.setattr("sys.argv", ["smoke", "--mode", "horizontal", "--password", "test", "--expected-sha", SHA])
    assert smoke.main() == 1


def test_e2e_runs_surfaces_only_after_both_revisions_match(monkeypatch):
    from scripts import smoke_test_e2e as smoke

    observed = []

    class Session:
        def __init__(self, _url):
            pass

        def request(self, _method, path, **_kwargs):
            observed.append(path)
            return 200, {"revision": SHA}

        def login(self, _password):
            return True

    def run_surfaces(*args):
        assert observed == ["/api/revision", "/api/pi-ceo/health"]
        return smoke.TestRun([smoke.TestResult("surface", True)])

    monkeypatch.setattr(smoke, "Session", Session)
    monkeypatch.setattr(smoke, "_load_surface_map", lambda: {"horizontal": [{}]})
    monkeypatch.setattr(smoke, "run_horizontal", run_surfaces)
    monkeypatch.setattr("sys.argv", ["smoke", "--mode", "horizontal", "--password", "test", "--expected-sha", SHA])
    assert smoke.main() == 0



def test_backend_production_args_require_revision_before_requests(monkeypatch):
    from scripts.smoke_revision import parse_backend_args

    monkeypatch.delenv("EXPECTED_SHA", raising=False)
    monkeypatch.setattr("sys.argv", ["smoke", "--target", "prod"])
    with pytest.raises(SystemExit) as error:
        parse_backend_args()
    assert error.value.code == 2


def test_backend_production_args_preserve_flags_and_target(monkeypatch):
    from scripts.smoke_revision import parse_backend_args

    monkeypatch.setattr("sys.argv", ["smoke", "--target", "prod", "--expected-sha", SHA,
                                    "--emit-metrics", "--agent-sdk"])
    args = parse_backend_args()
    assert args.url == "https://pi-dev-ops-production.up.railway.app"
    assert args.expected_sha == SHA
    assert args.emit_metrics and args.agent_sdk


def test_backend_production_args_preserve_explicit_url(monkeypatch):
    from scripts.smoke_revision import parse_backend_args

    monkeypatch.setattr("sys.argv", ["smoke", "--target", "prod", "--expected-sha", SHA,
                                    "--url", "https://example.invalid"])
    assert parse_backend_args().url == "https://example.invalid"
