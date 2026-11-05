"""RA-8187 AR-01 account map validator: CLI behaviour and the committed map.

Rule-by-rule coverage lives in test_check_account_map.py. Test docstrings cite the
why (W1-W5) recorded in the PR body's "Five whys".
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

import check_account_map as cam  # noqa: E402
from test_check_account_map import FIXTURES, _map  # noqa: E402



def test_cli_exit_codes_and_rule_names(tmp_path, capsys):
    """W1.4/W3.3: the CLI fails the build (exit 1) and names the rule, so CI can act on it."""
    good = tmp_path / "good.yaml"
    good.write_text(yaml.safe_dump(_map()))
    assert cam.main(["--path", str(good)]) == 0

    assert cam.main(["--path", str(FIXTURES / "planted_secret.yaml")]) == 1
    assert "SECRET_FIELD" in capsys.readouterr().out

    assert cam.main(["--path", str(FIXTURES / "shared_claude_email.yaml")]) == 1
    assert "SHARED_CLAUDE_EMAIL" in capsys.readouterr().out


def test_cli_missing_file_fails_not_empty(tmp_path, capsys):
    """W5.5: a failed read must never look like an empty successful read."""
    assert cam.main(["--path", str(tmp_path / "absent.yaml")]) == 1
    assert "FILE" in capsys.readouterr().out


def test_cli_invalid_yaml_fails(tmp_path, capsys):
    """W5.5: unparseable YAML is a failure with a rule name, not a traceback or a pass."""
    bad = tmp_path / "bad.yaml"
    bad.write_text("accounts: [unclosed\n")
    assert cam.main(["--path", str(bad)]) == 1
    assert "FILE" in capsys.readouterr().out


def test_committed_map_passes_and_reports_pending(capsys):
    """W5.3: the shipped file passes its own validator and says its emails await Phill."""
    assert cam.main([]) == 0
    out = capsys.readouterr().out
    assert "PENDING" in out


def test_committed_map_holds_no_real_addresses():
    """W5.2: agents never write real emails; every committed email is a .invalid placeholder."""
    data = yaml.safe_load(cam.DEFAULT_PATH.read_text())
    emails = [a["email"] for a in data["accounts"]]
    assert emails and all(e.endswith(".invalid") for e in emails)


@pytest.mark.parametrize(
    "path, value",
    [
        (("accounts", 0, "label"), ["a"]),
        (("accounts", 0, "label"), ""),
        (("accounts", 0, "machines"), [["mini"]]),
        (("accounts", 0, "machines"), [{"id": "mini"}]),
        (("accounts", 0, "provider"), ["claude"]),
        (("accounts", 0, "email"), ["a@example.com"]),
    ],
)
def test_wrong_types_fail_with_a_rule_not_a_traceback(path, value):
    """W5.5: a wrong type is a named failure, never a crash and never a pass."""
    data = _map()
    node = data
    for step in path[:-1]:
        node = node[step]
    node[path[-1]] = value
    report = cam.validate(data)
    assert report.errors, "a wrong type must not pass"


@pytest.mark.parametrize(
    "where, field",
    [("accounts", "plan"), ("accounts", "notes"), ("machines", "host"), ("machines", "notes")],
)
def test_credential_key_nested_inside_an_allowed_field_is_rejected(where, field):
    """W1.4: a credential-named key hidden one level down (notes: {token: ...}) still fails."""
    data = _map()
    data[where][0][field] = {"api_key": "not-a-real-value"}
    rules = {f.rule for f in cam.validate(data).errors}
    assert "SECRET_FIELD" in rules


@pytest.mark.parametrize(
    "where, field, value",
    [
        ("machines", "host", ["bad"]),
        ("machines", "notes", {"a": "b"}),
        ("accounts", "plan", ["max"]),
        ("accounts", "notes", 5),
    ],
)
def test_text_fields_must_be_text_or_null(where, field, value):
    """W4.1: host, plan and notes are plain text (or null); other shapes are SCHEMA errors."""
    data = _map()
    data[where][0][field] = value
    assert "SCHEMA" in {f.rule for f in cam.validate(data).errors}


def test_cli_nested_secret_fails(tmp_path, capsys):
    """W1.4: the CLI path (what CI runs) fails on the nested plant too."""
    data = _map()
    data["accounts"][0]["notes"] = {"token": "not-a-real-value"}
    path = tmp_path / "nested.yaml"
    path.write_text(yaml.safe_dump(data))
    assert cam.main(["--path", str(path)]) == 1
    assert "SECRET_FIELD" in capsys.readouterr().out
