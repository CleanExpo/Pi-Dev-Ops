"""Negative controls for the Pi-CEO proxy fallback gate.

A gate that has never been watched failing scores zero, however green it is.
These tests plant the defect the gate exists to catch and assert it FIRES, then
assert it stays quiet on honest code — so a gate that always passes and a gate
that always fails both break the suite.

The gate under test: .github/scripts/proxy_fallback_lint.py
"""
from __future__ import annotations

import importlib.util
import pathlib
import sys

import pytest

from tests.proxy_lint_sources import (
    BLIND_SOURCE,
    COMMENT_ONLY_SOURCE,
    CONST_URL_SOURCE,
    HONEST_SOURCE,
    NON_CONSUMER_SOURCE,
    POST_ONLY_SOURCE,
    SSE_SOURCE,
    WRAPPER_HELPER_SOURCE,
)

REPO = pathlib.Path(__file__).resolve().parents[1]
GATE = REPO / ".github" / "scripts" / "proxy_fallback_lint.py"


def _load_gate():
    spec = importlib.util.spec_from_file_location("proxy_fallback_lint", GATE)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["proxy_fallback_lint"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def gate(tmp_path, monkeypatch):
    """The gate pointed at a synthetic repo, so no real file is created or deleted."""
    mod = _load_gate()
    monkeypatch.setattr(mod, "REPO", tmp_path)
    monkeypatch.setattr(mod, "BASELINE", tmp_path / ".github" / "proxy-fallback.baseline.txt")
    (tmp_path / ".github").mkdir(parents=True, exist_ok=True)
    return mod


def _plant(tmp_path, rel: str, source: str) -> None:
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(source, encoding="utf-8")


def test_fires_on_a_new_blind_consumer(gate, tmp_path, monkeypatch, capsys):
    """THE control: plant the defect, the gate must exit 1 and name the file."""
    rel = "dashboard/components/control/NewPanel.tsx"
    _plant(tmp_path, rel, BLIND_SOURCE)
    monkeypatch.setattr(gate, "tracked_files", lambda: [rel])
    gate.write_baseline([])  # nothing grandfathered

    monkeypatch.setattr(sys, "argv", ["proxy_fallback_lint.py"])
    assert gate.main() == 1
    assert rel in capsys.readouterr().out


def test_passes_when_the_client_uses_the_honest_reader(gate, tmp_path, monkeypatch):
    """The gate must not fire on correct code, or its red means nothing."""
    rel = "dashboard/components/control/NewPanel.tsx"
    _plant(tmp_path, rel, HONEST_SOURCE)
    monkeypatch.setattr(gate, "tracked_files", lambda: [rel])
    gate.write_baseline([])

    monkeypatch.setattr(sys, "argv", ["proxy_fallback_lint.py"])
    assert gate.main() == 0


def test_grandfathers_a_baselined_file(gate, tmp_path, monkeypatch):
    """Existing blind files must not break the build — the gate is a ratchet."""
    rel = "dashboard/components/control/OldPanel.tsx"
    _plant(tmp_path, rel, BLIND_SOURCE)
    monkeypatch.setattr(gate, "tracked_files", lambda: [rel])
    gate.write_baseline([rel])

    monkeypatch.setattr(sys, "argv", ["proxy_fallback_lint.py"])
    assert gate.main() == 0


def test_fires_when_a_fixed_file_stays_in_the_baseline(gate, tmp_path, monkeypatch, capsys):
    """Shrink-only: a file that is no longer blind cannot keep its exemption.

    Without this the baseline becomes a permanent permission slip and the count
    stops meaning anything.
    """
    rel = "dashboard/components/control/OldPanel.tsx"
    _plant(tmp_path, rel, HONEST_SOURCE)  # fixed
    monkeypatch.setattr(gate, "tracked_files", lambda: [rel])
    gate.write_baseline([rel])  # but still listed

    monkeypatch.setattr(sys, "argv", ["proxy_fallback_lint.py"])
    assert gate.main() == 1
    assert rel in capsys.readouterr().out


def test_ignores_files_that_never_touch_the_proxy(gate, tmp_path, monkeypatch):
    """Scope: the gate must not gate the whole dashboard."""
    rel = "dashboard/lib/constants.ts"
    _plant(tmp_path, rel, NON_CONSUMER_SOURCE)
    monkeypatch.setattr(gate, "tracked_files", lambda: [rel])
    gate.write_baseline([])

    monkeypatch.setattr(sys, "argv", ["proxy_fallback_lint.py"])
    assert gate.main() == 0


def test_exempts_the_proxy_route_itself(gate, tmp_path, monkeypatch):
    """The route that SETS the header is not a consumer of it."""
    rel = "dashboard/app/api/pi-ceo/[...path]/route.ts"
    _plant(tmp_path, rel, BLIND_SOURCE)
    monkeypatch.setattr(gate, "tracked_files", lambda: [rel])
    gate.write_baseline([])

    monkeypatch.setattr(sys, "argv", ["proxy_fallback_lint.py"])
    assert gate.main() == 0


@pytest.mark.parametrize(
    "name,source",
    [
        ("url-held-in-a-const", CONST_URL_SOURCE),
        ("called-via-a-wrapper-helper", WRAPPER_HELPER_SOURCE),
    ],
)
def test_sees_call_sites_that_do_not_sit_next_to_a_literal_fetch(
    gate, tmp_path, monkeypatch, name, source
):
    """Regression controls for the 18 -> 14 false narrowing.

    Both of these are GET paths the proxy fallback CAN reach. Neither has
    `fetch(` beside the URL. A gate that misses them reports a smaller,
    cleaner, wrong number.
    """
    rel = f"dashboard/components/control/{name}.tsx"
    _plant(tmp_path, rel, source)
    monkeypatch.setattr(gate, "tracked_files", lambda: [rel])
    gate.write_baseline([])

    monkeypatch.setattr(sys, "argv", ["proxy_fallback_lint.py"])
    assert gate.main() == 1, f"{name}: gate went blind on a reachable GET path"


@pytest.mark.parametrize(
    "name,source",
    [
        ("comment-prose-only", COMMENT_ONLY_SOURCE),
        ("post-mutation-only", POST_ONLY_SOURCE),
        ("sse-event-source", SSE_SOURCE),
    ],
)
def test_exempts_shapes_the_fallback_cannot_reach(gate, tmp_path, monkeypatch, name, source):
    """The other direction: quietFallback fires only for GET, and never for SSE.

    Without these, the gate flags everything and its red stops meaning anything.
    """
    rel = f"dashboard/components/control/{name}.tsx"
    _plant(tmp_path, rel, source)
    monkeypatch.setattr(gate, "tracked_files", lambda: [rel])
    gate.write_baseline([])

    monkeypatch.setattr(sys, "argv", ["proxy_fallback_lint.py"])
    assert gate.main() == 0, f"{name}: gate fired on a path the fallback cannot reach"


def test_the_real_repo_baseline_is_current(capsys):
    """Runs the gate against the ACTUAL repo — catches a baseline left stale.

    This is the only test here that touches real files, and it is read-only.
    """
    mod = _load_gate()
    sys.argv = ["proxy_fallback_lint.py"]
    assert mod.main() == 0, capsys.readouterr().out
