"""RA-8133: git children get an allowlisted env, never a copy of the parent's.

`git_auth_env` and `git_safety.prepare_git` used to start from the whole
inherited environment, so every service secret the server held reached git
and, through whole-dict assertions, the pytest log. These tests plant
obviously fake values and assert by name and by value, never by printing a
whole environment.
"""
from __future__ import annotations

import pytest

from app.server import autopr, git_safety
from app.server.git_auth import git_auth_env

PLANTED = "planted-not-a-secret"
PLANTED_NAMES = ("MC_LANE_SECRET", "SOME_API_TOKEN")
_GITHUB = "https://github.com/CleanExpo/Pi-Dev-Ops"
_GITLAB = "https://gitlab.com/some/repo"


def _plant(monkeypatch):
    for name in PLANTED_NAMES:
        monkeypatch.setenv(name, PLANTED)
    monkeypatch.setenv("GITHUB_TOKEN", "fake-token-for-tests")


def _leaked(env: dict[str, str]) -> list[str]:
    """Names (never values) that carry a planted name or the planted value."""
    return sorted(k for k, v in env.items() if k in PLANTED_NAMES or v == PLANTED)


@pytest.mark.parametrize("url", [_GITHUB, _GITLAB, ""])
def test_planted_secrets_never_reach_git_auth_env(monkeypatch, url):
    _plant(monkeypatch)
    assert _leaked(git_auth_env(url)) == []


def test_github_token_itself_is_not_passed_as_a_variable(monkeypatch):
    _plant(monkeypatch)
    assert "GITHUB_TOKEN" not in set(git_auth_env(_GITHUB))


def test_needed_names_survive_with_their_values(monkeypatch):
    _plant(monkeypatch)
    wanted = {
        "PATH": "/planted/bin", "HOME": "/planted/home", "LANG": "en_AU.UTF-8",
        "HTTPS_PROXY": "http://proxy.invalid:3128", "SSL_CERT_FILE": "/planted/ca.pem",
    }
    for name, value in wanted.items():
        monkeypatch.setenv(name, value)
    env = git_auth_env(_GITHUB)
    for name, value in wanted.items():
        assert env.get(name) == value, name
    assert env["GIT_TERMINAL_PROMPT"] == "0"
    assert env["GIT_CONFIG_KEY_0"] == "http.https://github.com/.extraheader"


def test_windows_home_fallback_names_survive():
    """Git on Windows finds HOME via HOMEDRIVE+HOMEPATH, then USERPROFILE."""
    parent = {"HOMEDRIVE": "C:", "HOMEPATH": "\\Users\\planted", "USERPROFILE": "C:\\Users\\planted"}
    env = git_auth_env(_GITLAB, environ=parent)
    for name, value in parent.items():
        assert env.get(name) == value, name


def test_inherited_git_config_pairs_are_dropped_for_other_remotes(monkeypatch):
    """A parent's own extraheader must not ride along to a non-github host."""
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "http.extraheader")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", PLANTED)
    env = git_auth_env(_GITLAB)
    assert {"GIT_CONFIG_COUNT", "GIT_CONFIG_KEY_0", "GIT_CONFIG_VALUE_0"}.isdisjoint(set(env))


def test_original_failing_shape_cannot_print_the_planted_value():
    """The RA-8133 log leak: a whole-env membership assert failing in pytest."""
    parent = {"PATH": "/usr/bin", "MC_LANE_SECRET": PLANTED, "SOME_API_TOKEN": PLANTED}
    env = git_auth_env(_GITLAB, environ=parent)
    with pytest.raises(AssertionError) as caught:
        assert "GIT_CONFIG_VALUE_0" in env  # deliberately false, as in the incident
    rendered = str(caught.value) + str(caught.getrepr())
    assert "PATH" in rendered, "positive control: the assertion did render the env"
    assert PLANTED not in rendered


def test_prepare_git_drops_planted_secrets_without_an_env(monkeypatch, tmp_path):
    _plant(monkeypatch)
    _, child = git_safety.prepare_git(str(tmp_path), ["status"], None)
    assert _leaked(child) == []
    assert "GITHUB_TOKEN" not in set(child)


def test_prepare_git_drops_planted_secrets_from_a_caller_env(monkeypatch, tmp_path):
    _plant(monkeypatch)
    caller = {**git_auth_env(_GITHUB), "MC_LANE_SECRET": PLANTED}
    _, child = git_safety.prepare_git(str(tmp_path), ["push"], caller)
    assert _leaked(child) == []
    assert child["GIT_CONFIG_KEY_0"] == "http.https://github.com/.extraheader"


@pytest.mark.asyncio
async def test_autopr_git_child_process_gets_no_planted_secret(monkeypatch, tmp_path):
    _plant(monkeypatch)
    seen: dict[str, dict[str, str]] = {}

    class _Proc:
        returncode = 0

        async def communicate(self):
            return b"", b""

    async def fake_exec(*_args, **kwargs):
        seen["env"] = kwargs["env"]
        return _Proc()

    monkeypatch.setattr(autopr.asyncio, "create_subprocess_exec", fake_exec)
    await autopr._git(["status"], tmp_path)
    assert _leaked(seen["env"]) == []
    assert seen["env"]["GIT_AUTHOR_NAME"] == "Pi-SEO"
