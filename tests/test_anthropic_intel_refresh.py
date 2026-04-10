"""
test_anthropic_intel_refresh.py — Unit tests for Anthropic Intelligence Refresh.

Covers:
  - Baseline creation (no prior snapshot)
  - Delta detection and brief generation
  - No-delta scenarios
  - Dry-run mode
  - Network error handling
  - Complete fetch failure
"""
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_urls():
    """Mock URL content."""
    return {
        "https://docs.claude.com/en/release-notes/overview": "Release notes content\nNew model: Claude 4.0\nBreaking changes in SDK",
        "https://docs.claude.com/en/api/overview": "API documentation\nUpdated endpoints\nNew authentication method",
        "https://docs.claude.com/en/docs/claude-code/overview": "Claude Code overview\nAgent SDK improvements\nNew hooks",
    }


def test_refresh_baseline(tmp_path, mock_urls):
    """No prior snapshot — creates baseline, returns brief_path=None."""
    from app.server.agents.anthropic_intel_refresh import refresh_anthropic_intel

    snapshot_dir = tmp_path / "snapshots"
    brief_dir = tmp_path / "briefs"

    with patch("app.server.agents.anthropic_intel_refresh.httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        # Mock responses
        async def mock_get(url):
            response = AsyncMock()
            response.text = mock_urls[url]
            response.raise_for_status = lambda: None
            return response

        mock_client.get = mock_get

        result = asyncio.run(
            refresh_anthropic_intel(
                snapshot_dir=str(snapshot_dir),
                brief_dir=str(brief_dir),
            )
        )

    assert result["brief_path"] is None
    assert len(result["fetched_urls"]) == 3
    assert len(result["errors"]) == 0
    assert snapshot_dir.exists()


def test_refresh_with_delta(tmp_path, mock_urls):
    """Prior snapshot exists, content differs — writes brief."""
    from app.server.agents.anthropic_intel_refresh import refresh_anthropic_intel

    snapshot_dir = tmp_path / "snapshots"
    brief_dir = tmp_path / "briefs"
    snapshot_dir.mkdir(parents=True)

    # Create prior snapshot with different content
    # Note: filenames are {second-to-last}-{last}.md from URL path
    prior_date = "2026-04-10"
    prior_snapshot = snapshot_dir / prior_date
    prior_snapshot.mkdir()
    (prior_snapshot / "release-notes-overview.md").write_text("Old release notes content")
    (prior_snapshot / "api-overview.md").write_text("Old API docs content")
    (prior_snapshot / "claude-code-overview.md").write_text("Old Claude Code content")

    with patch("app.server.agents.anthropic_intel_refresh.httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        async def mock_get(url):
            response = AsyncMock()
            response.text = mock_urls[url]
            response.raise_for_status = lambda: None
            return response

        mock_client.get = mock_get

        result = asyncio.run(
            refresh_anthropic_intel(
                snapshot_dir=str(snapshot_dir),
                brief_dir=str(brief_dir),
            )
        )

    # Should generate a brief because content differs
    assert result["brief_path"] is not None
    assert brief_dir.exists()
    brief_file = Path(result["brief_path"])
    assert brief_file.exists()
    brief_content = brief_file.read_text()
    assert "Delta detected" in brief_content or "Refresh" in brief_content


def test_refresh_no_delta(tmp_path, mock_urls):
    """Prior snapshot exists, content matches — returns brief_path=None."""
    from app.server.agents.anthropic_intel_refresh import refresh_anthropic_intel

    snapshot_dir = tmp_path / "snapshots"
    brief_dir = tmp_path / "briefs"
    snapshot_dir.mkdir(parents=True)

    # Create prior snapshot with identical content
    prior_date = "2026-04-10"
    prior_snapshot = snapshot_dir / prior_date
    prior_snapshot.mkdir()
    (prior_snapshot / "release-notes-overview.md").write_text(mock_urls["https://docs.claude.com/en/release-notes/overview"])
    (prior_snapshot / "api-overview.md").write_text(mock_urls["https://docs.claude.com/en/api/overview"])
    (prior_snapshot / "claude-code-overview.md").write_text(mock_urls["https://docs.claude.com/en/docs/claude-code/overview"])

    with patch("app.server.agents.anthropic_intel_refresh.httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        async def mock_get(url):
            response = AsyncMock()
            response.text = mock_urls[url]
            response.raise_for_status = lambda: None
            return response

        mock_client.get = mock_get

        result = asyncio.run(
            refresh_anthropic_intel(
                snapshot_dir=str(snapshot_dir),
                brief_dir=str(brief_dir),
            )
        )

    # No delta, no brief
    assert result["brief_path"] is None
    assert len(result["fetched_urls"]) == 3


def test_refresh_dry_run(tmp_path, mock_urls):
    """Dry-run=True — no files written, result dict populated."""
    from app.server.agents.anthropic_intel_refresh import refresh_anthropic_intel

    snapshot_dir = tmp_path / "snapshots"
    brief_dir = tmp_path / "briefs"

    with patch("app.server.agents.anthropic_intel_refresh.httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        async def mock_get(url):
            response = AsyncMock()
            response.text = mock_urls[url]
            response.raise_for_status = lambda: None
            return response

        mock_client.get = mock_get

        result = asyncio.run(
            refresh_anthropic_intel(
                snapshot_dir=str(snapshot_dir),
                brief_dir=str(brief_dir),
                dry_run=True,
            )
        )

    # Result computed but no files written
    assert result["fetched_urls"]
    assert not snapshot_dir.exists() or not list(snapshot_dir.glob("*"))


def test_refresh_network_error(tmp_path, mock_urls):
    """One URL fails, other two succeed — failed URL in errors list."""
    from app.server.agents.anthropic_intel_refresh import refresh_anthropic_intel

    snapshot_dir = tmp_path / "snapshots"
    brief_dir = tmp_path / "briefs"

    with patch("app.server.agents.anthropic_intel_refresh.httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        async def mock_get(url):
            if "release-notes" in url:
                # Simulate network error
                raise Exception("Connection timeout")
            response = MagicMock()
            response.text = mock_urls[url]
            response.raise_for_status = MagicMock()
            return response

        mock_client.get = mock_get

        result = asyncio.run(
            refresh_anthropic_intel(
                snapshot_dir=str(snapshot_dir),
                brief_dir=str(brief_dir),
            )
        )

    assert len(result["errors"]) == 1
    assert "release-notes" in result["errors"][0][0]
    assert len(result["fetched_urls"]) == 2


def test_refresh_all_fail(tmp_path):
    """All three URLs fail — errors list has 3 entries, no snapshot."""
    from app.server.agents.anthropic_intel_refresh import refresh_anthropic_intel

    snapshot_dir = tmp_path / "snapshots"
    brief_dir = tmp_path / "briefs"

    with patch("app.server.agents.anthropic_intel_refresh.httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        async def mock_get(url):
            raise Exception("Network error")

        mock_client.get = mock_get

        result = asyncio.run(
            refresh_anthropic_intel(
                snapshot_dir=str(snapshot_dir),
                brief_dir=str(brief_dir),
            )
        )

    assert len(result["errors"]) == 3
    assert len(result["fetched_urls"]) == 0
    # No snapshot written (no successful fetches)
    assert not snapshot_dir.exists() or len(list(snapshot_dir.glob("*/*"))) == 0
