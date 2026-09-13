"""UNI-2633 — Board exam and one-screen packet (SPM / Judge / Storm shape)."""

from __future__ import annotations

from pathlib import Path

from app.server.idea_pipeline import append_and_examine, daily_snapshot, examine_intake
from app.server.idea_pipeline.constants import NORTH_STAR, VERDICTS
from app.server.idea_pipeline.examine import recommend_verdict
from app.server.idea_pipeline.intake import RawIdea
from app.server.idea_pipeline.packet import build_packet


def _idea(text: str, source: str = "phill") -> RawIdea:
    return RawIdea(idea_id="idea-test", text=text, source=source, intake_path="IDEAS.md")


def test_strong_north_star_idea_promotes() -> None:
    text = (
        "Teach shop owners to film their own product videos in short "
        "self-paced lessons that also work as audio."
    )
    packet = build_packet(_idea(text))
    assert packet["recommended_verdict"] in VERDICTS
    assert packet["recommended_verdict"] == "PROMOTE"
    assert packet["north_star_fit"]["north_star"] == NORTH_STAR
    assert packet["north_star_fit"]["score"] >= 0.45
    assert packet["directive"]["id"] != "unmapped"
    assert packet["judge"]["score"] >= 1
    assert packet["spm"]["out_of_scope"]
    assert packet["storm"]["rows"]
    assert packet["executed"] is False
    assert packet["go_at"] is None


def test_unrelated_idea_is_killed() -> None:
    packet = build_packet(_idea("Repaint the office bikeshed a darker blue."))
    assert packet["recommended_verdict"] == "KILL"


def test_vague_idea_is_parked() -> None:
    packet = build_packet(_idea("Maybe videos later."))
    assert packet["recommended_verdict"] == "PARK"


def test_medium_fit_goes_to_backlog() -> None:
    text = "Add a reminder note about growth for owners next quarter."
    exam = {
        "north_star_fit": {"score": 0.25},
        "effort_vs_impact": {"effort": "low", "impact": "low"},
        "directive": {"id": "small-business-growth"},
    }
    assert recommend_verdict(exam["north_star_fit"], exam["effort_vs_impact"], exam["directive"], text) == "BACKLOG"


def test_examine_intake_writes_packets(tmp_path: Path) -> None:
    (tmp_path / "IDEAS.md").write_text(
        "Teach shop owners a short self-paced sales lesson on video.\n",
        encoding="utf-8",
    )
    packets = examine_intake(tmp_path)
    assert len(packets) == 1
    assert packets[0]["status"] == "awaiting_dispose"
    stored = tmp_path / ".harness" / "idea-pipeline" / f"{packets[0]['idea_id']}.json"
    assert stored.is_file()


def test_tracked_ideas_file_is_readable() -> None:
    from pathlib import Path

    from app.server.idea_pipeline.intake import read_ideas

    ideas = read_ideas(Path(__file__).resolve().parents[1] / "IDEAS.md")
    assert ideas, "IDEAS.md must carry at least one droppable test idea"
    assert ideas[0].source in {"phill", "margot"}
    assert len(ideas[0].text.split()) >= 8


def test_daily_snapshot_is_one_screen(tmp_path: Path) -> None:
    append_and_examine(
        tmp_path,
        "Teach cafe owners to grow with self-paced video lessons.",
        source="margot",
    )
    snap = daily_snapshot(tmp_path)
    assert snap["intake"] == "IDEAS.md"
    assert snap["awaiting"] == 1
    assert snap["go_required"] is True
    assert snap["executed"] is False
    assert snap["packet"]["source"] == "margot"
    assert set(snap["verdicts"]) == VERDICTS
