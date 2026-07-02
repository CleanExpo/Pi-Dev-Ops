"""tests/test_marketing_skill_bridge.py — UNI-2236 marketing bridge tests."""
from __future__ import annotations

from unittest.mock import patch

from swarm.marketing_content_generator import generate_social_post, score_eeat, score_geo
from swarm.marketing_skill_bridge import ingest_markdown_file, run_scheduled_bridge


def test_score_eeat_passes_substantive_copy():
    body = (
        "According to IICRC S500, we measured 38% faster dry times on a certified "
        "restoration job. Source: https://example.com/case-study Contact us."
    )
    result = score_eeat(body, ymyl=False)
    assert "scores" in result
    assert result["verdict"] in {"pass", "needs-work", "fail"}
    assert result["scores"]["trust"] >= 25


def test_score_geo_rewards_front_loaded_answer():
    body = (
        "Pi CEO automates marketing publishing with scored social posts that land in "
        "the publisher queue without manual seeding each week across the portfolio. "
        "The bridge applies E-E-A-T and GEO checks before scheduling. "
        "## FAQ\n\n### How does scheduling work?\n\nRows land in social_posts.\n"
    )
    result = score_geo(body)
    assert result["score"] >= 35


def test_generate_social_post_includes_scores():
    post = generate_social_post(
        business_key="synthex",
        topic="Authority post",
        body="We tested autonomous publishing across 3 brands with measurable lift.",
        channel="linkedin",
    )
    assert post.platforms == ["linkedin"]
    assert post.scores.composite > 0


def test_ingest_markdown_file_writes_row(tmp_path, monkeypatch):
    monkeypatch.setenv("TAO_FOUNDER_USER_ID", "00000000-0000-4000-8000-000000000001")
    md = tmp_path / "synthex-linkedin-1.md"
    md.write_text(
        "---\nbrand: synthex\nchannel: linkedin\ntopic: Bridge test\n---\n\n"
        "Autonomous marketing bridge seeds publisher queues.\n",
        encoding="utf-8",
    )
    with patch("app.server.supabase_log._insert", return_value=True) as ins:
        row_id = ingest_markdown_file(md, business_key="synthex", channel="linkedin")
    assert row_id
    ins.assert_called_once()
    row = ins.call_args[0][1]
    assert row["business_key"] == "synthex"
    assert row["founder_id"] == "00000000-0000-4000-8000-000000000001"
    assert row["eeat_score"]
    assert row["geo_score"]


def test_run_scheduled_bridge_generates_when_no_files(monkeypatch):
    monkeypatch.setenv("TAO_FOUNDER_USER_ID", "00000000-0000-4000-8000-000000000001")
    monkeypatch.setattr(
        "swarm.marketing_skill_bridge._discover_skill_outputs",
        lambda: [],
    )
    with patch("app.server.supabase_log._insert", return_value=True):
        result = run_scheduled_bridge(max_rows=1)
    assert result.rows_written == 1
    assert not result.errors
