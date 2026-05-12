"""tests/test_sprinkle_triage.py — RA-3017 sprinkle coverage.

Covers `app.server.triage._claude_triage`:
  * Routes through provider_router with role `sprinkle.triage`
  * Parses valid JSON response into the expected verdict dict
  * Returns None on rc != 0 (LLM call failed)
  * Returns None on router-unavailable exception
  * Logs a structured sprinkle event to .harness/autonomy.jsonl on each outcome
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from app.server.scanner import Finding  # noqa: E402
from tests._sprinkle_helpers import FakeProviderRouter, install_fake_router  # noqa: E402


def _make_finding() -> Finding:
    return Finding(
        scan_type="security",
        severity="high",
        title="Possible SSRF",
        description="axios call with user-controlled URL",
        file_path="apps/web/lib/fetch.ts",
        line_number=42,
    )


def _read_autonomy_log_tail(tmp_log: Path) -> list[dict]:
    if not tmp_log.exists():
        return []
    return [json.loads(ln) for ln in tmp_log.read_text().splitlines() if ln.strip()]


@pytest.fixture
def autonomy_log(monkeypatch, tmp_path: Path):
    """Redirect `triage._AUTONOMY_LOG` to a tmp file so per-test logs don't bleed."""
    from app.server import triage as t
    log = tmp_path / "autonomy.jsonl"
    monkeypatch.setattr(t, "_AUTONOMY_LOG", log)
    return log


def test_triage_routes_through_provider_router(monkeypatch, autonomy_log):
    fake = FakeProviderRouter(
        response='{"title": "SSRF risk in fetch.ts", "verdict": "real", "confidence": 0.82}',
    )
    install_fake_router(monkeypatch, fake)

    from app.server import triage as t
    out = t._claude_triage("dr-nrpg", _make_finding())

    assert out is not None
    assert out["verdict"] == "real"
    assert out["title"] == "SSRF risk in fetch.ts"
    assert pytest.approx(0.82, rel=1e-3) == out["confidence"]
    assert len(fake.calls) == 1
    assert fake.calls[0]["role"] == t._TRIAGE_ROLE == "sprinkle.triage"


def test_triage_returns_none_on_llm_failure(monkeypatch, autonomy_log):
    fake = FakeProviderRouter(rc=1, response="", error="upstream_500")
    install_fake_router(monkeypatch, fake)

    from app.server import triage as t
    out = t._claude_triage("dr-nrpg", _make_finding())

    assert out is None
    events = _read_autonomy_log_tail(autonomy_log)
    assert any(e.get("sprinkle") == "triage" and e.get("outcome") == "call_failed" for e in events)


def test_triage_returns_none_on_router_exception(monkeypatch, autonomy_log):
    fake = FakeProviderRouter(raise_exc=RuntimeError("router gone"))
    install_fake_router(monkeypatch, fake)

    from app.server import triage as t
    out = t._claude_triage("dr-nrpg", _make_finding())

    assert out is None
    events = _read_autonomy_log_tail(autonomy_log)
    assert any(e.get("sprinkle") == "triage" and e.get("outcome") == "router_unavailable" for e in events)


def test_triage_returns_none_on_unparseable_json(monkeypatch, autonomy_log):
    fake = FakeProviderRouter(response="not json at all, ho hum")
    install_fake_router(monkeypatch, fake)

    from app.server import triage as t
    out = t._claude_triage("dr-nrpg", _make_finding())

    assert out is None
    events = _read_autonomy_log_tail(autonomy_log)
    # The JSON-parse failure either logs `json_parse_failed` or `bad_shape`;
    # we just assert it didn't silently succeed.
    assert any(e.get("sprinkle") == "triage" for e in events)
