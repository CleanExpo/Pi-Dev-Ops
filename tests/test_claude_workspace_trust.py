"""Ephemeral Pi-CEO workspaces must be marked trusted in ~/.claude.json.

Official Claude Code docs: SDK / `claude -p` never show the trust dialog, and
project `.claude/settings.json` `permissions.allow` is ignored until
`projects["<repo-root>"].hasTrustDialogAccepted` is true. Production Pipeline
Smoke clones into `/tmp/pi-ceo-workspaces/{sid}` — a new path every run —
then the planner returns rc=1 (`_block_plan_phase`).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.server import claude_workspace_trust as trust


ROOT = "/tmp/pi-ceo-workspaces"
SESSION = "/tmp/pi-ceo-workspaces/4264c07a4fea"


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_ephemeral_child_is_in_scope() -> None:
    assert trust.is_ephemeral_workspace(SESSION, ROOT) is True


def test_workspace_root_itself_is_in_scope() -> None:
    assert trust.is_ephemeral_workspace(ROOT, ROOT) is True


def test_escape_via_dotdot_is_out_of_scope() -> None:
    assert trust.is_ephemeral_workspace("/tmp/pi-ceo-workspaces/../evil", ROOT) is False


def test_unrelated_tmp_path_is_out_of_scope() -> None:
    assert trust.is_ephemeral_workspace("/tmp/other/ws", ROOT) is False


def test_slash_workspace_root_never_matches() -> None:
    assert trust.is_ephemeral_workspace("/etc/passwd", "/") is False


def test_home_slash_refuses_claude_json_path() -> None:
    assert trust.claude_json_path("/") is None


def test_missing_home_refuses_claude_json_path() -> None:
    assert trust.claude_json_path("") is None


def test_real_home_points_at_dot_claude_json() -> None:
    assert trust.claude_json_path("/home/railway") == Path("/home/railway/.claude.json")


def test_trust_write_sets_flag_and_preserves_oauth(tmp_path: Path) -> None:
    config = tmp_path / ".claude.json"
    config.write_text(
        json.dumps({"oauthAccount": {"accountUuid": "keep-me"}, "projects": {}}),
        encoding="utf-8",
    )

    assert trust.ensure_workspace_trusted(
        SESSION, workspace_root=ROOT, config_path=config,
    ) is True

    data = _read(config)
    assert data["oauthAccount"]["accountUuid"] == "keep-me"
    assert data["projects"][SESSION]["hasTrustDialogAccepted"] is True


def test_trust_write_merges_existing_project_entry(tmp_path: Path) -> None:
    config = tmp_path / ".claude.json"
    config.write_text(
        json.dumps({"projects": {SESSION: {"allowedTools": ["Read"]}}}),
        encoding="utf-8",
    )

    assert trust.ensure_workspace_trusted(
        SESSION, workspace_root=ROOT, config_path=config,
    ) is True

    entry = _read(config)["projects"][SESSION]
    assert entry["allowedTools"] == ["Read"]
    assert entry["hasTrustDialogAccepted"] is True


def test_trust_write_is_idempotent(tmp_path: Path) -> None:
    config = tmp_path / ".claude.json"
    assert trust.ensure_workspace_trusted(
        SESSION, workspace_root=ROOT, config_path=config,
    ) is True
    first = config.read_text(encoding="utf-8")
    assert trust.ensure_workspace_trusted(
        SESSION, workspace_root=ROOT, config_path=config,
    ) is True
    assert config.read_text(encoding="utf-8") == first


def test_outside_root_does_not_touch_claude_json(tmp_path: Path) -> None:
    config = tmp_path / ".claude.json"
    config.write_text("{}", encoding="utf-8")

    assert trust.ensure_workspace_trusted(
        "/etc/ssh", workspace_root=ROOT, config_path=config,
    ) is False
    assert config.read_text(encoding="utf-8") == "{}"


def test_corrupt_claude_json_is_left_alone(tmp_path: Path) -> None:
    config = tmp_path / ".claude.json"
    config.write_text("{not-json", encoding="utf-8")

    assert trust.ensure_workspace_trusted(
        SESSION, workspace_root=ROOT, config_path=config,
    ) is False
    assert config.read_text(encoding="utf-8") == "{not-json"


def test_kill_switch_disables_writes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAO_TRUST_EPHEMERAL_WORKSPACES", "0")
    config = tmp_path / ".claude.json"

    assert trust.ensure_workspace_trusted(
        SESSION, workspace_root=ROOT, config_path=config,
    ) is False
    assert not config.exists()


def test_home_slash_skips_write_even_for_ephemeral_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME", "/")
    # No config_path override: the HOME=/ guard must fire first.
    assert trust.ensure_workspace_trusted(SESSION, workspace_root=ROOT) is False
    assert not Path("/.claude.json").exists()
    assert not (tmp_path / ".claude.json").exists()


def test_prepare_sdk_environment_pops_empty_api_key_and_trusts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import os

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    called: list[str] = []
    monkeypatch.setattr(
        trust, "ensure_workspace_trusted", lambda ws: called.append(ws) or True,
    )

    trust.prepare_sdk_environment(SESSION)

    assert "ANTHROPIC_API_KEY" not in os.environ
    assert called == [SESSION]


def test_session_sdk_calls_prepare_before_query() -> None:
    """Positive control: `_attempt` must invoke prepare on the workspace cwd."""
    source = Path(__file__).resolve().parents[1] / "app" / "server" / "session_sdk.py"
    text = source.read_text(encoding="utf-8")
    assert "from . import claude_workspace_trust" in text
    assert "claude_workspace_trust.prepare_sdk_environment(workspace)" in text
