"""tests/test_mesh_env_file.py — which PI_CEO_API_KEY a fleet node sends (RA-7905).

On Phill_Desktop a stale User-level PI_CEO_API_KEY overrode the provisioned key in
~/.hermes/.env, and the backend refused every heartbeat with a 401. The provisioned
file now wins; a differing environment value is reported by name, never by value.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

MESH = Path(__file__).resolve().parents[1] / "mesh"
sys.path.insert(0, str(MESH))


@pytest.fixture
def env_file(monkeypatch, tmp_path):
    home = tmp_path / "home"
    (home / ".hermes").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.delenv("PI_CEO_API_KEY", raising=False)
    mod = importlib.reload(importlib.import_module("env_file"))
    return mod, home / ".hermes" / ".env"


def test_the_provisioned_file_wins_over_a_stale_environment_value(env_file, monkeypatch, capsys):
    mod, f = env_file
    f.write_text("PI_CEO_API_KEY='provisioned-key-41-chars'\n", encoding="utf-8")
    monkeypatch.setenv("PI_CEO_API_KEY", "stale-21-char-key")
    assert mod.resolve_key("PI_CEO_API_KEY") == "provisioned-key-41-chars"
    err = capsys.readouterr().err
    assert "PI_CEO_API_KEY" in err and "differs" in err
    # Names only: neither value may reach the log.
    assert "stale-21-char-key" not in err and "provisioned-key-41-chars" not in err


def test_the_environment_is_used_when_no_file_holds_the_key(env_file, monkeypatch, capsys):
    mod, _ = env_file
    monkeypatch.setenv("PI_CEO_API_KEY", "ci-only-key")
    assert mod.resolve_key("PI_CEO_API_KEY") == "ci-only-key"
    assert capsys.readouterr().err == ""


def test_matching_values_are_silent(env_file, monkeypatch, capsys):
    mod, f = env_file
    f.write_text("PI_CEO_API_KEY=same\n", encoding="utf-8")
    monkeypatch.setenv("PI_CEO_API_KEY", "same")
    assert mod.resolve_key("PI_CEO_API_KEY") == "same"
    assert capsys.readouterr().err == ""


def test_neither_set_is_empty_not_an_error(env_file):
    mod, _ = env_file
    assert mod.resolve_key("PI_CEO_API_KEY") == ""


@pytest.mark.parametrize("path", ["heartbeat.py", "runner.py", "report_ship.py"])
def test_every_fleet_sender_resolves_the_key_through_resolve_key(path):
    """A node with one sender env-first and the others file-first would send two keys."""
    src = (MESH / path).read_text(encoding="utf-8")
    assert 'resolve_key("PI_CEO_API_KEY")' in src
    assert 'os.environ.get("PI_CEO_API_KEY") or' not in src
