"""The portfolio needs a repository identifier in each saved pipeline summary."""

from app.server import pipeline


def test_saved_pipeline_summary_exposes_repo_for_project_matching(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "_PIPELINE_ROOT", tmp_path / "pipeline")
    state = pipeline.PipelineState(
        pipeline_id="portfolio-01",
        idea="Track a project through release",
        repo_url="https://github.com/example/inventory-api",
        current_phase="spec",
        phases_completed=[],
        spec="## Spec",
        plan=None,
        session_id=None,
        test_results=None,
        review_score=None,
        ship_log=None,
    )
    pipeline.save_pipeline_state(state)
    assert pipeline.list_pipelines()[0]["repo_url"] == state.repo_url
