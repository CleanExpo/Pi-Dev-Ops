"""tests/test_conversation_collector.py — Milestone 3 client half.

Covers the two properties that make this collector safe to run on three
machines: nothing unredacted leaves the box, and a second run over an
unchanged lake ships nothing. Both are positive-controlled — the two
`*_positive_control_note` tests record the sabotage each was seen to fail
under. No test touches the network: every run injects a fake poster.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import conversation_collector as cc  # noqa: E402

# Must match sync_claude_sessions._SECRET_PATTERNS ANTHROPIC_API (sk-ant-api +
# 20 chars). A short "sk-ant-api03-FAKEKEY" would pass for the wrong reason.
FAKE_SECRET = "sk-ant-api03-" + "FAKEKEY" * 4


class FakePoster:
    """Records batches instead of POSTing them."""

    def __init__(self, status: int = 200) -> None:
        self.status = status
        self.calls: list[tuple[str, dict, dict]] = []

    def __call__(self, url: str, headers: dict, payload: dict) -> tuple[int, str]:
        self.calls.append((url, headers, payload))
        return self.status, "{}"

    @property
    def rows(self) -> list[dict]:
        """Every digest sent, in the server's ingest shape."""
        return [d for _, _, body in self.calls for d in body["digests"]]


def _session_lines(secret: str) -> list[dict]:
    """Two turns in the real lake shape, both carrying the fake key."""
    return [
        {"type": "user", "timestamp": "2026-08-30T10:00:00Z",
         "cwd": "/Users/someone/Pi-Dev-Ops", "gitBranch": "feature/RA-9999-thing",
         "message": {"content": f"Deploy with key {secret} please"}},
        {"type": "assistant", "timestamp": "2026-08-30T10:00:05Z",
         "message": {"content": [
             {"type": "text", "text": f"Using {secret} now — done."},
             {"type": "tool_use", "name": "Bash"}]}},
    ]


@pytest.fixture(autouse=True)
def _credential(monkeypatch) -> None:
    """Every run has a shared secret unless a test removes it deliberately."""
    monkeypatch.setenv("PI_CEO_API_KEY", "test-secret")


@pytest.fixture()
def lake(tmp_path: Path) -> Path:
    """A one-session lake whose transcript contains a fake Anthropic key."""
    project = tmp_path / "lake" / "-Users-someone-Pi-Dev-Ops"
    project.mkdir(parents=True)
    body = "\n".join(json.dumps(rec) for rec in _session_lines(FAKE_SECRET))
    (project / "abc12345-dead-beef-0000-000000000001.jsonl").write_text(body + "\n")
    return tmp_path / "lake"


@pytest.fixture()
def marker(tmp_path: Path) -> Path:
    return tmp_path / "markers" / ".conversation-sync-markers.json"


def _run(lake: Path, marker: Path, poster: FakePoster, **kw) -> dict:
    return cc.run(
        root=lake, marker_path=marker, poster=poster, machine="testbox",
        enabled=True, **kw,
    )


# ── (a) redaction ────────────────────────────────────────────────────────────
def test_shipped_row_never_contains_the_raw_secret(lake: Path, marker: Path) -> None:
    poster = FakePoster()
    summary = _run(lake, marker, poster)
    assert summary["status"] == "ok"
    assert summary["sent"] == 1
    row = poster.rows[0]
    blob = json.dumps(row)
    assert FAKE_SECRET not in blob
    assert "FAKEKEY" not in blob
    assert "[REDACTED:ANTHROPIC_API]" in row["digest_md"]


def test_no_raw_transcript_field_is_shipped(lake: Path, marker: Path) -> None:
    """Only the digest travels — no raw messages/content/transcript key."""
    poster = FakePoster()
    _run(lake, marker, poster)
    digest = poster.rows[0]
    assert set(digest) == {
        "session_id", "project_dir", "title", "digest_md",
        "turn_count", "started_at", "last_activity_at",
    }
    assert digest["session_id"] == "abc12345-dead-beef-0000-000000000001"
    assert digest["turn_count"] == 2
    assert digest["started_at"] == "2026-08-30T10:00:00Z"
    assert digest["last_activity_at"].startswith("20")


def test_wire_envelope_matches_the_ingest_contract(lake: Path, marker: Path) -> None:
    """POST body is {machine, digests[]} — app/server/routes/conversations.py
    IngestRequest — while build_row keeps the machine-scoped id internally."""
    poster = FakePoster()
    _run(lake, marker, poster)
    _, _, body = poster.calls[0]
    assert set(body) == {"machine", "digests"}
    assert body["machine"] == "testbox"
    row = cc.build_row(next(lake.rglob("*.jsonl")), "testbox")
    assert row["id"] == f"testbox:{body['digests'][0]['session_id']}"


def test_build_row_redacts_title_and_project(tmp_path: Path) -> None:
    """title and project_dir are redacted by build_row alone.

    render_digest redacts the digest body itself, so these two fields are the
    ones where this module is the only barrier — hence a cwd shaped like a
    Google key, which nothing upstream of build_row would scrub.
    """
    project = tmp_path / "-Users-someone-proj"
    project.mkdir()
    path = project / "s1.jsonl"
    path.write_text(json.dumps({
        "type": "user",
        "timestamp": "2026-08-30T10:00:00Z",
        "cwd": f"/Users/someone/AIza{'FAKE' * 6}",
        "message": {"content": f"token {FAKE_SECRET}"},
    }) + "\n")
    row = cc.build_row(path, "testbox")
    assert row is not None
    assert FAKE_SECRET not in row["title"]
    assert "AIza" not in row["project_dir"]
    assert row["project_dir"] == "[REDACTED:GOOGLE_API]"


def test_redaction_positive_control_note() -> None:
    """Control, run twice, each substitution asserted to change the file:
    (1) `redact()` in sync_claude_sessions.py stubbed to `return text`, and
    (2) build_row's own redact() calls removed. Both times the two tests above
    FAILED on `FAKE_SECRET not in blob`; reverted, green again.
    """
    assert "redact(render_digest" in Path(cc.__file__).read_text()


# ── (b) incremental marker ───────────────────────────────────────────────────
def test_second_run_over_unchanged_lake_ships_nothing(lake: Path, marker: Path) -> None:
    first = FakePoster()
    assert _run(lake, marker, first)["sent"] == 1
    second = FakePoster()
    summary = _run(lake, marker, second)
    assert summary["candidates"] == 0
    assert summary["sent"] == 0
    assert second.calls == []


def test_appended_session_is_shipped_again(lake: Path, marker: Path) -> None:
    """The MacBook rejoin case: a session that grew is picked up next run."""
    assert _run(lake, marker, FakePoster())["sent"] == 1
    path = next(lake.rglob("*.jsonl"))
    with path.open("a") as handle:
        handle.write(json.dumps({
            "type": "user", "timestamp": "2026-08-30T11:00:00Z",
            "message": {"content": "one more turn"},
        }) + "\n")
    again = FakePoster()
    assert _run(lake, marker, again)["sent"] == 1


def test_marker_positive_control_note() -> None:
    """Control: dropping the marker write makes the idempotence test FAIL.

    Verified by editing scripts/conversation_collector.py to replace
    `save_markers(markers, marker_path)` in run() with `pass`  (substitution
    asserted to change the file), then re-running this module: 1 failed on
    `assert summary["candidates"] == 0` (got 1 — the same session re-shipped).
    Reverted; green again.
    """
    assert "save_markers(markers, marker_path)" in Path(cc.__file__).read_text()


def test_torn_marker_costs_one_entry_not_the_history(tmp_path: Path) -> None:
    path = tmp_path / "m.json"
    path.write_text(
        json.dumps({"path": "/a.jsonl", "mtime": 1.0, "size": 10}) + "\n"
        + '{"path": "/b.jsonl", "mtime": 2.0, "siz\n'          # torn line
        + json.dumps({"path": "/c.jsonl", "mtime": 3.0, "size": 30}) + "\n"
    )
    markers = cc.load_markers(path)
    assert set(markers) == {"/a.jsonl", "/c.jsonl"}


def test_marker_roundtrip_and_legacy_json_object(tmp_path: Path) -> None:
    path = tmp_path / "m.json"
    cc.save_markers({"/a.jsonl": {"mtime": 1.5, "size": 7}}, path)
    assert cc.load_markers(path) == {"/a.jsonl": {"mtime": 1.5, "size": 7}}
    assert not path.with_suffix(path.suffix + ".tmp").exists()
    legacy = tmp_path / "legacy.json"
    legacy.write_text(json.dumps({"/x.jsonl": {"mtime": 9.0, "size": 3}}))
    assert cc.load_markers(legacy)["/x.jsonl"]["size"] == 3
    assert cc.load_markers(tmp_path / "missing.json") == {}


# ── gating, limits, failure handling ─────────────────────────────────────────
def test_dry_run_neither_posts_nor_writes_marker(lake: Path, marker: Path) -> None:
    poster = FakePoster()
    summary = _run(lake, marker, poster, dry_run=True)
    assert summary == {"status": "dry-run", "candidates": 1, "sent": 0, "errors": []}
    assert poster.calls == []
    assert not marker.exists()


def test_disabled_by_default_gate(lake: Path, marker: Path, monkeypatch) -> None:
    monkeypatch.delenv("CONVERSATION_SYNC_ENABLED", raising=False)
    poster = FakePoster()
    summary = cc.run(root=lake, marker_path=marker, poster=poster, machine="testbox")
    assert summary["status"] == "disabled"
    assert poster.calls == []
    assert not marker.exists()


def test_missing_credential_refuses_to_post(lake: Path, marker: Path, monkeypatch) -> None:
    monkeypatch.setattr(cc, "api_secret", lambda: "")
    poster = FakePoster()
    assert _run(lake, marker, poster)["status"] == "no-credential"
    assert poster.calls == []


def test_failed_batch_leaves_marker_unwritten_for_retry(
    lake: Path, marker: Path, monkeypatch
) -> None:
    monkeypatch.setattr(cc, "api_secret", lambda: "s3cr3t")
    summary = _run(lake, marker, FakePoster(status=500))
    assert summary["status"] == "partial"
    assert summary["errors"] and "HTTP 500" in summary["errors"][0]
    assert not marker.exists()
    ok = FakePoster()
    assert _run(lake, marker, ok)["sent"] == 1
    # launchd sees only the exit code, and this run committed no marker at all.
    monkeypatch.setattr(sys, "argv", ["conversation_collector.py"])
    monkeypatch.setattr(cc, "run", lambda **kw: summary)
    assert cc.main() == 4
    monkeypatch.setattr(cc, "run", lambda **kw: {"status": "a-future-status"})
    assert cc.main() == 1, "an unmapped status must never report success"


def test_secret_header_and_endpoint(lake: Path, marker: Path, monkeypatch) -> None:
    monkeypatch.setattr(cc, "api_secret", lambda: "s3cr3t")
    monkeypatch.setattr(cc, "api_url", lambda: "https://example.test/")
    poster = FakePoster()
    _run(lake, marker, poster)
    url, headers, _ = poster.calls[0]
    assert url == "https://example.test/api/conversations/ingest"
    assert headers["X-Pi-CEO-Secret"] == "s3cr3t"


def test_limit_caps_rows(tmp_path: Path, marker: Path) -> None:
    root = tmp_path / "lake"
    root.mkdir()
    for index in range(3):
        (root / f"s{index}.jsonl").write_text(json.dumps({
            "type": "user", "timestamp": "2026-08-30T10:00:00Z",
            "message": {"content": f"hello {index}"},
        }) + "\n")
    poster = FakePoster()
    assert _run(root, marker, poster, limit=2)["sent"] == 2


def test_missing_lake_is_reported_not_raised(tmp_path: Path, marker: Path) -> None:
    summary = _run(tmp_path / "nope", marker, FakePoster())
    assert summary["status"] == "no-lake"


def test_empty_session_file_yields_no_row(tmp_path: Path) -> None:
    path = tmp_path / "empty.jsonl"
    path.write_text("")
    assert cc.build_row(path, "testbox") is None


def test_env_file_credential_reader(tmp_path: Path, monkeypatch) -> None:
    """Same ~/.hermes/.env read path as mesh/runner.py — never executes the file."""
    home = tmp_path / "home"
    (home / ".hermes").mkdir(parents=True)
    (home / ".hermes" / ".env").write_text(
        "# comment\nPI_CEO_API_KEY='from-file'\nOTHER=1\n"
    )
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.delenv("PI_CEO_API_KEY", raising=False)
    assert cc.api_secret() == "from-file"
