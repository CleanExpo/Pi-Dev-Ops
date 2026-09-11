"""Fail-open controls for the Pi-CEO proxy fallback gate.

Split out of `test_proxy_fallback_lint.py`, which reached the 300-line
convention. Same discipline as that module: every control here plants the
defect and is watched FAILING against the unfixed gate before the fix lands.

Both defects were found by independent review of 84b6d9d5:

  P0  an unreadable file was skipped, so "I could not look" was indistinguishable
      from "there is nothing there"
  P1  a `method:` or `EventSource(` belonging to a NEIGHBOURING call, merely
      inside the character window, excused a genuinely blind GET
"""
from __future__ import annotations

import importlib.util
import pathlib
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
GATE = REPO / ".github" / "scripts" / "proxy_fallback_lint.py"

# Duplicated from test_proxy_fallback_lint.py rather than shared: a pytest
# fixture has to live in the module that uses it or in conftest, and putting
# gate-specific scaffolding in the repo-wide conftest would reach every suite.
SSE_SOURCE = """
function openStream(sid: string) {
  const es = new EventSource(`/api/pi-ceo/api/sessions/${sid}/logs`);
  return es;
}
"""


def _load_gate():
    spec = importlib.util.spec_from_file_location("proxy_fallback_lint", GATE)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["proxy_fallback_lint"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def gate(tmp_path, monkeypatch):
    """The gate pointed at a synthetic repo, so no real file is touched."""
    mod = _load_gate()
    monkeypatch.setattr(mod, "REPO", tmp_path)
    monkeypatch.setattr(mod, "BASELINE", tmp_path / ".github" / "proxy-fallback.baseline.txt")
    (tmp_path / ".github").mkdir(parents=True, exist_ok=True)
    return mod


def _plant(tmp_path, rel: str, source: str) -> None:
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(source, encoding="utf-8")


# A URL held in a const sits outside any call, so there is no call to read a
# method off. Proximity was standing in for evidence, and it failed open both
# ways: found by probing _enclosing_call after the first round of fixes.
CONST_AFTER_EVENTSOURCE_SOURCE = """
function stream(sid) {
  const es = new EventSource(`/api/pi-ceo/api/sessions/${sid}/logs`);
}
const API = "/api/pi-ceo/api/margot/assets";
"""

CONST_BEFORE_POST_SOURCE = """
const API = "/api/pi-ceo/api/margot/assets";
async function save() {
  await fetch(`/api/pi-ceo/api/sessions`, { method: "POST" });
}
"""


@pytest.mark.parametrize(
    "name,source",
    [
        ("const-url-after-an-eventsource", CONST_AFTER_EVENTSOURCE_SOURCE),
        ("const-url-before-a-post", CONST_BEFORE_POST_SOURCE),
    ],
)
def test_a_const_url_is_not_excused_by_a_neighbour(
    gate, tmp_path, monkeypatch, name, source
):
    """A URL outside any call is BLIND, with no appeal to what sits near it.

    The reviewer named the wrong mechanism here — `_enclosing_call` returns
    empty for a const URL rather than grabbing a preceding call — but the
    conclusion held: the character-window fallback excused both of these.
    Probed before fixing, so the red was observed and not assumed.
    """
    rel = f"dashboard/components/control/{name}.tsx"
    _plant(tmp_path, rel, source)
    monkeypatch.setattr(gate, "tracked_files", lambda: [rel])
    gate.write_baseline([])

    monkeypatch.setattr(sys, "argv", ["proxy_fallback_lint.py"])
    assert gate.main() == 1, f"{name}: a neighbouring call excused a const URL"


# A blind GET whose NEIGHBOUR carries the POST. The GET itself has no options
# object at all, so it is a real violation; the old lookahead window simply saw
# a `method:` belonging to a different call and excused it.
POST_NEIGHBOUR_SOURCE = """
async function load() {
  const res = await fetch(`/api/pi-ceo/api/autonomy/status`);
  await fetch(`/api/pi-ceo/api/sessions`, { method: "POST" });
  return await res.json();
}
"""

# The same trick with the lookback: a genuine EventSource stream, and a blind
# GET close enough behind it to be mistaken for part of it.
EVENTSOURCE_NEIGHBOUR_SOURCE = """
function stream(sid) {
  const es = new EventSource(`/api/pi-ceo/api/sessions/${sid}/logs`);
  const res = fetch(`/api/pi-ceo/api/autonomy/status`);
  return [es, res];
}
"""


@pytest.mark.parametrize(
    "name,source",
    [
        ("post-on-a-sibling-call", POST_NEIGHBOUR_SOURCE),
        ("eventsource-on-a-sibling-call", EVENTSOURCE_NEIGHBOUR_SOURCE),
    ],
)
def test_a_neighbouring_call_cannot_vouch_for_a_blind_get(
    gate, tmp_path, monkeypatch, capsys, name, source
):
    """A blind GET must not be excused by a `method:` or `EventSource(` that
    belongs to a DIFFERENT call merely sitting within the character window."""
    rel = "dashboard/components/control/NewPanel.tsx"
    _plant(tmp_path, rel, source)
    monkeypatch.setattr(gate, "tracked_files", lambda: [rel])
    gate.write_baseline([])

    monkeypatch.setattr(sys, "argv", ["proxy_fallback_lint.py"])
    assert gate.main() == 1, f"{name}: a sibling call hid a blind GET"
    assert rel in capsys.readouterr().out


def test_a_real_eventsource_is_still_exempt(gate, tmp_path, monkeypatch):
    """The negative half: tightening the window must not start firing on
    streams, or the test above passes for the wrong reason."""
    rel = "dashboard/components/control/Stream.tsx"
    _plant(tmp_path, rel, SSE_SOURCE)
    monkeypatch.setattr(gate, "tracked_files", lambda: [rel])
    gate.write_baseline([])

    monkeypatch.setattr(sys, "argv", ["proxy_fallback_lint.py"])
    assert gate.main() == 0


@pytest.mark.parametrize("argv", [["proxy_fallback_lint.py"],
                                  ["proxy_fallback_lint.py", "--update"]])
def test_refuses_when_a_tracked_file_cannot_be_read(
    gate, tmp_path, monkeypatch, capsys, argv
):
    """An unreadable file must FAIL the gate, not be skipped.

    Skipping made "I could not look" indistinguishable from "there is nothing
    there". `--update` is covered too: a baseline rewritten from a partial read
    would record files nobody managed to open as clean.
    """
    rel = "dashboard/components/control/Unreadable.tsx"
    (tmp_path / rel).mkdir(parents=True)  # a directory where a file is expected
    monkeypatch.setattr(gate, "tracked_files", lambda: [rel])
    gate.write_baseline([])

    monkeypatch.setattr(sys, "argv", argv)
    assert gate.main() == 1
    out = capsys.readouterr().out
    assert "could not read" in out and rel in out
