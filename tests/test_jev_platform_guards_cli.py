"""Guard sweep 29/09: CLI refusals and exit codes (`__main__`, `cli_scale`) that no test could fail without.

Each test below fails with its named guard removed (tests/mutation/jev_platform_mutants.py).
The product call behind each command is replaced by a recorder, so "nothing sent" is observed, not assumed.
"""
from __future__ import annotations

import pytest
from jev_scale_support import Recorder, make_repo

from jev_platform import __main__ as cli
from jev_platform import ask, cli_scale, engine, scout
from jev_platform import manifest as mf

KEY = "TYPESAFE_API_KEY"


class Seen(list):
    """The names of product calls made, plus `.reply` (canned returns) and `.post` (the transport recorder)."""


@pytest.fixture
def calls(monkeypatch):
    """Record every product call the CLI makes; each returns what `calls.reply[name]` holds (default {})."""
    seen, reply = Seen(), {}

    def spy(name):
        return lambda *a, **k: seen.append(name) or reply.get(name, {})
    for mod, name in ((engine, "calibrate"), (ask, "ask_files"), (ask, "approve_entry"),
                      (mf, "approve_glob"), (mf, "approve_prompt"), (scout, "scout_files")):
        monkeypatch.setattr(mod, name, spy(name))
    monkeypatch.setattr(engine, "artifact_rating", lambda rid: seen.append("rating") or reply["rating"])
    post = Recorder()
    monkeypatch.setattr(cli, "http_post", post)
    seen.reply, seen.post = reply, post
    return seen


# ---- __main__.py

def test_calibrate_and_ask_without_key_are_blocked_and_send_nothing(calls, monkeypatch, capsys):
    """guard sweep 29/09: no key -> rc 2 before any call reaches the transport."""
    monkeypatch.delenv(KEY, raising=False)
    assert cli.main(["calibrate", "--rule", "core-01"]) == 2
    assert cli.main(["ask", "--file", "a.ts", "--q", "known-issue"]) == 2
    assert calls == [] and calls.post.calls == [] and capsys.readouterr().err.count("BLOCKED") == 2


@pytest.mark.parametrize("state,rc", [("incomplete", 1), (None, 1), ("provisional", 0)])
def test_calibrate_exit_code_follows_the_record_state(calls, monkeypatch, state, rc):
    """guard sweep 29/09: an incomplete (or stateless) calibration exits 1."""
    monkeypatch.setenv(KEY, "ts-test-value-0000")
    calls.reply["calibrate"] = {"rule": "core-01", "state": state}
    assert cli.main(["calibrate", "--rule", "core-01"]) == rc and calls == ["calibrate"]


@pytest.mark.parametrize("rating,rc", [(("FAIL", ["absent"]), 1), (("AA", []), 0), (("AAA", []), 0)])
def test_verify_calibration_exit_code_follows_the_rating(calls, rating, rc):
    """guard sweep 29/09: a FAIL rating exits 1."""
    calls.reply["rating"] = rating
    assert cli.main(["verify-calibration", "--rule", "core-01"]) == rc


def test_ask_blocked_exits_2(calls, monkeypatch):
    """guard sweep 29/09: a blocked ask is not a success."""
    monkeypatch.setenv(KEY, "ts-test-value-0000")
    calls.reply["ask_files"] = {"blocked": "manifest missing", "results": []}
    assert cli.main(["ask", "--file", "a.ts", "--q", "known-issue"]) == 2 and calls == ["ask_files"]
    calls.reply["ask_files"] = {"results": []}
    assert cli.main(["ask", "--file", "a.ts", "--q", "known-issue"]) == 0


def test_ask_refuses_more_than_50_files_before_asking(calls, monkeypatch, capsys):
    """guard sweep 29/09: 51 --file is refused with rc 2 and nothing is asked."""
    monkeypatch.setenv(KEY, "ts-test-value-0000")
    argv = ["ask", "--q", "known-issue"] + [x for i in range(51) for x in ("--file", f"f{i}.ts")]
    assert cli.main(argv) == 2 and calls == [] and "at most 50 files" in capsys.readouterr().err


@pytest.mark.parametrize("argv", [
    ["approve", "x.ts", "--glob", "src/**"],
    ["approve", "--glob", "src/**", "--prompt-file", "p.txt", "--id", "p"],
    ["approve", "--prompt-file", "p.txt"],
    ["approve", "x.ts", "--id", "p"],
])
def test_approve_refuses_anything_but_exactly_one_source(calls, argv, capsys):
    """guard sweep 29/09: two sources, or --prompt-file and --id not given together, is rc 2 with no call."""
    calls.reply.update(approve_glob={"files": {}}, approve_prompt={"prompts": {}}, approve_entry={"files": {}})
    assert cli.main(argv) == 2 and calls == [] and "REFUSED" in capsys.readouterr().err


def test_approve_empty_prompt_file_exits_2(monkeypatch, tmp_path):
    """guard sweep 29/09: an empty prompt file yields no `prompts` entry, so the command is not a success."""
    (tmp_path / "empty.txt").write_text("")
    assert cli.main(["approve", "--prompt-file", str(tmp_path / "empty.txt"), "--id", "p"]) == 2


# ---- cli_scale.py

def test_scout_without_key_is_blocked_and_sends_nothing(calls, monkeypatch, tmp_path, capsys):
    """guard sweep 29/09: no key -> rc 2 before the repository is even resolved."""
    monkeypatch.delenv(KEY, raising=False)
    repo = make_repo(tmp_path, {"a.ts": "x\n"})
    assert cli.main(["scout", "--glob", "*.ts", "--q", "known-issue", "--repo", repo]) == 2
    assert calls == [] and calls.post.calls == [] and "BLOCKED" in capsys.readouterr().err
    assert cli_scale._jev_ready() is False


def test_scout_refuses_a_relative_repo_even_when_it_is_a_repository(calls, monkeypatch, tmp_path, capsys):
    """guard sweep 29/09: --repo must be absolute; a relative path that resolves is still refused."""
    monkeypatch.setenv(KEY, "ts-test-value-0000")
    make_repo(tmp_path / "r", {"a.ts": "x\n"})
    monkeypatch.chdir(tmp_path)
    assert cli.main(["scout", "--glob", "*.ts", "--q", "known-issue", "--repo", "r"]) == 2
    assert calls == [] and "must be an absolute path" in capsys.readouterr().err


def test_scout_refuses_a_directory_outside_any_repository(calls, monkeypatch, tmp_path, capsys):
    """guard sweep 29/09: a non-git directory is refused with rc 2; nothing runs against it."""
    monkeypatch.setenv(KEY, "ts-test-value-0000")
    (tmp_path / "plain").mkdir()
    assert cli_scale.repo_root(str(tmp_path / "plain")) is None
    assert cli.main(["scout", "--glob", "*.ts", "--q", "known-issue", "--repo", str(tmp_path / "plain")]) == 2
    assert calls == [] and "not inside a git repository" in capsys.readouterr().err


@pytest.mark.parametrize("out,rc", [({"blocked": "no manifest"}, 2), ({"outcome": "refused"}, 2),
                                    ({"outcome": "none", "results": []}, 0)])
def test_scout_exit_code_is_2_for_blocked_and_for_refused(calls, monkeypatch, tmp_path, out, rc):
    """guard sweep 29/09: both a blocked run and a refused outcome exit 2; anything else exits 0."""
    monkeypatch.setenv(KEY, "ts-test-value-0000")
    repo = make_repo(tmp_path, {"a.ts": "x\n"})
    calls.reply["scout_files"] = out
    assert cli.main(["scout", "--glob", "*.ts", "--q", "known-issue", "--repo", repo]) == rc
    assert calls == ["scout_files"]
