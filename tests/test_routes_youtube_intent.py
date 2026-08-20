from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.server.routes import youtube_intent as youtube_intent_route
from app.server import youtube_intent as intent_module
from app.server import youtube_connector as connector_module


def _client(tmp_path: Path) -> TestClient:
    intent_module.STATE_PATH = tmp_path / "state.json"
    intent_module.POLICY_PATH = tmp_path / "policy.json"
    intent_module.WIKI_DIR = tmp_path / "wiki"
    connector_module.OAUTH_STATE_PATH = tmp_path / "oauth.json"
    app = FastAPI()
    app.include_router(youtube_intent_route.router)
    app.dependency_overrides[youtube_intent_route.require_auth] = lambda: {"sub": "test"}
    return TestClient(app)


def test_policy_endpoint_bootstraps_file(tmp_path: Path):
    client = _client(tmp_path)
    res = client.get("/api/nexus/youtube-intent/policy")
    assert res.status_code == 200
    body = res.json()
    assert body["policy"]["name"] == "intent_only_strategic_policy"
    assert (tmp_path / "policy.json").exists()


def test_catalog_filters_entertainment(tmp_path: Path):
    client = _client(tmp_path)
    res = client.post(
        "/api/nexus/youtube-intent/catalog",
        json={
            "items": [
                {
                    "video_id": "v1",
                    "title": "AI workflow for revenue growth",
                    "channel": "UGN Ops",
                    "watch_count_window": 6,
                    "selected_by_user": True,
                    "tags": ["automation", "strategy"],
                },
                {
                    "video_id": "v2",
                    "title": "Comedy highlights of the week",
                    "channel": "Fun Times",
                    "watch_count_window": 3,
                    "tags": ["comedy", "highlights"],
                },
            ]
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["accepted"] == 1
    assert body["excluded"] == 1

    catalog = client.get("/api/nexus/youtube-intent/catalog").json()
    assert catalog["accepted_count"] == 1
    assert catalog["excluded_count"] == 1
    assert catalog["accepted_items"][0]["reason"] in {"strategic_match", "selected_user_seed"}
    assert catalog["excluded_items"][0]["reason"] == "entertainment_signal"


def test_synthesize_writes_wiki_pages(tmp_path: Path):
    client = _client(tmp_path)
    client.post(
        "/api/nexus/youtube-intent/catalog",
        json={
            "items": [
                {
                    "video_id": "v3",
                    "title": "Agentic automation system for operations",
                    "channel": "UGN Systems",
                    "watch_count_window": 8,
                    "selected_by_user": True,
                    "tags": ["agent", "operations", "automation"],
                }
            ]
        },
    )
    res = client.post("/api/nexus/youtube-intent/synthesize")
    assert res.status_code == 200
    payload = res.json()
    assert payload["topics"]
    assert payload["persona_traits"]
    assert len(payload["wiki_pages"]) == 4
    for page in payload["wiki_pages"]:
        assert Path(page).exists()


def test_oauth_start_reports_missing_config(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("YOUTUBE_OAUTH_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_ID", raising=False)
    monkeypatch.delenv("YOUTUBE_OAUTH_REDIRECT_URI", raising=False)
    monkeypatch.delenv("GOOGLE_OAUTH_REDIRECT_URI", raising=False)
    client = _client(tmp_path)
    res = client.get("/api/nexus/youtube-intent/oauth/start")
    assert res.status_code == 200
    body = res.json()
    assert body["configured"] is False
    assert body["auth_url"] is None


def test_takeout_import_aggregates_watch_counts(tmp_path: Path):
    client = _client(tmp_path)
    res = client.post(
        "/api/nexus/youtube-intent/import-takeout",
        json={
            "entries": [
                {
                    "title": "Watched AI automation strategy deep dive",
                    "titleUrl": "https://youtube.com/watch?v=alpha",
                    "subtitles": [{"name": "UGN Channel"}],
                },
                {
                    "title": "Watched AI automation strategy deep dive",
                    "titleUrl": "https://youtube.com/watch?v=alpha",
                    "subtitles": [{"name": "UGN Channel"}],
                },
                {
                    "title": "Watched Comedy highlights",
                    "titleUrl": "https://youtube.com/watch?v=beta",
                    "subtitles": [{"name": "Fun Channel"}],
                },
            ]
        },
    )
    assert res.status_code == 200
    payload = res.json()
    assert payload["unique_items"] == 2
    catalog = client.get("/api/nexus/youtube-intent/catalog").json()
    accepted = {row["video_key"]: row for row in catalog["accepted_items"]}
    excluded = {row["video_key"]: row for row in catalog["excluded_items"]}
    assert accepted["https://youtube.com/watch?v=alpha"]["watch_count_window"] == 2
    assert excluded["https://youtube.com/watch?v=beta"]["reason"] == "entertainment_signal"
