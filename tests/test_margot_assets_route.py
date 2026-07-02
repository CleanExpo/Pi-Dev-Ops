"""tests/test_margot_assets_route.py — Margot asset preview API."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.server.routes import margot_assets
from app.server.auth import require_auth
from scripts import margot_generate as MG


def _manifest(tmp_path: Path) -> dict:
    asset = tmp_path / "margot.png"
    asset.write_bytes(b"png")
    return {
        "schema_version": 1,
        "canonical_name": "Margot",
        "canonical_asset_path": str(asset),
        "canonical_wiki_page": "Wiki/margot-visual-identity.md",
        "default_output_dir": ".harness/margot/generated-assets",
        "openai": {
            "api": "image",
            "endpoint": "https://api.openai.com/v1/images/generations",
            "model": "gpt-image-2",
            "size": "1024x1536",
            "quality": "high",
            "n": 1,
        },
        "identity": {"brand_boundary": "brand-safe"},
        "base_prompt": "Create Margot as a realistic professional assistant.",
        "projects": {
            "unite-group": {"display_name": "Unite-Group", "overlay": "Nexus."},
            "synthex": {"display_name": "Synthex", "overlay": "Marketing."},
        },
        "variants": {
            "avatar": {"slug": "avatar", "direction": "Portrait."},
            "dashboard": {"slug": "dashboard", "direction": "Dashboard."},
        },
        "safety_rules": ["Keep Margot professional."],
    }


@pytest.fixture
def client(monkeypatch, tmp_path: Path):
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(_manifest(tmp_path)), encoding="utf-8")
    monkeypatch.setattr(MG, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(MG, "DEFAULT_MANIFEST", manifest_path)
    (tmp_path / ".harness/margot/build-packets").mkdir(parents=True)
    (tmp_path / ".harness/margot/generated-assets").mkdir(parents=True)

    app = FastAPI()
    app.include_router(margot_assets.router)
    app.dependency_overrides[require_auth] = lambda: None
    return TestClient(app)


def test_options_lists_projects_and_variants(client: TestClient):
    r = client.get("/api/margot/assets/options")
    assert r.status_code == 200
    body = r.json()
    assert body["model"] == "gpt-image-2"
    assert body["matrix_item_count"] == 4
    assert "unite-group" in body["projects"]


def test_preview_returns_payload(client: TestClient):
    r = client.get("/api/margot/assets/preview", params={"project": "synthex", "variant": "avatar"})
    assert r.status_code == 200
    body = r.json()
    assert body["payload"]["model"] == "gpt-image-2"
    assert "Synthex" in body["payload"]["prompt"]
    assert len(body["provenance"]["prompt_sha256"]) == 64


def test_create_build_packet_writes_file(client: TestClient, tmp_path: Path):
    r = client.post("/api/margot/assets/packets", json={"projects": ["unite-group"], "variants": ["avatar"]})
    assert r.status_code == 200
    body = r.json()
    assert body["item_count"] == 1
    packet_path = Path(body["build_packet"])
    assert packet_path.is_file()
    assert packet_path.name.startswith("margot-build-packet-")


def test_list_and_read_packets(client: TestClient):
    client.post("/api/margot/assets/packets", json={})
    listed = client.get("/api/margot/assets/packets")
    assert listed.status_code == 200
    packets = listed.json()["packets"]
    assert len(packets) >= 1
    detail = client.get(f"/api/margot/assets/packets/{packets[0]['filename']}")
    assert detail.status_code == 200
    assert detail.json()["item_count"] == 4


def test_invalid_packet_name_rejected(client: TestClient):
    r = client.get("/api/margot/assets/packets/../secrets.json")
    assert r.status_code in (400, 404)
