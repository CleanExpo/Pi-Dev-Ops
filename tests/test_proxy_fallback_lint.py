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

REPO = pathlib.Path(__file__).resolve().parents[1]
GATE = REPO / ".github" / "scripts" / "proxy_fallback_lint.py"


def _load_gate():
    spec = importlib.util.spec_from_file_location("proxy_fallback_lint", GATE)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["proxy_fallback_lint"] = mod
    spec.loader.exec_module(mod)
    return mod


# A client that renders whatever the proxy hands it. The defect.
BLIND_SOURCE = """
async function load() {
  const res = await fetch(`/api/pi-ceo/api/autonomy/status`);
  if (!res.ok) return null;
  return await res.json();
}
"""

# The same client, routed through the honest reader.
HONEST_SOURCE = """
import { fetchProxyJSON } from "@/lib/pi-ceo-fetch";
async function load() {
  return await fetchProxyJSON("/api/autonomy/status");
}
"""

# Touches the proxy path only in a comment; still a consumer by the textual
# rule, and deliberately so — the gate says it is textual rather than pretending
# to understand the code.
NON_CONSUMER_SOURCE = """
export const POLL_MS = 20_000;
"""


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


def test_the_real_repo_baseline_is_current(capsys):
    """Runs the gate against the ACTUAL repo — catches a baseline left stale.

    This is the only test here that touches real files, and it is read-only.
    """
    mod = _load_gate()
    sys.argv = ["proxy_fallback_lint.py"]
    assert mod.main() == 0, capsys.readouterr().out
