"""Offline failure and provenance checks for the existing documentation refresh."""
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest

from app.server.agents import anthropic_intel_refresh as refresh


@pytest.fixture
def docs_client(monkeypatch):
    responses = {url: "# Documentation\nStable text\n" for url in refresh._DOCS_URLS}

    class Client:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def get(self, url):
            value = responses[url]
            if isinstance(value, Exception):
                raise value
            return httpx.Response(200, text=value, request=httpx.Request("GET", url))

    monkeypatch.setattr(refresh.httpx, "AsyncClient", Client)
    return responses


async def run_refresh(tmp_path):
    return await refresh.refresh_anthropic_intel(
        snapshot_dir=str(tmp_path / "snapshots"), brief_dir=str(tmp_path / "briefs")
    )


@pytest.mark.asyncio
async def test_provider_provenance_and_freshness(tmp_path, docs_client):
    result = await run_refresh(tmp_path)
    manifest = json.loads((Path(result["new_snapshot_path"]) / "manifest.json").read_text())
    assert {source["provider"] for source in manifest["sources"]} >= {
        "anthropic", "openai", "google", "openrouter"
    }
    assert len({s["filename"] for s in manifest["sources"]}) == len(docs_client)
    for source in manifest["sources"]:
        assert source["sha256"] == hashlib.sha256(docs_client[source["url"]].encode()).hexdigest()
        assert source["verified_at"]
    status = refresh.read_documentation_status(tmp_path / "snapshots")
    assert status["status"] == "fresh"
    assert status["model_registry_verified"] is False
    future = datetime.now(timezone.utc) + timedelta(days=9)
    assert refresh.read_documentation_status(tmp_path / "snapshots", now=future)["status"] == "stale"


@pytest.mark.asyncio
async def test_change_after_line_twenty_and_removed_model_are_review_candidates(tmp_path, docs_client):
    url = next(iter(docs_client))
    docs_client[url] = "\n".join(["Heading"] * 30 + ["model retired-old supported"])
    await run_refresh(tmp_path)
    docs_client[url] = "\n".join(["Heading"] * 30 + ["model new-version supported"])
    result = await run_refresh(tmp_path)
    changed = [value for value in result["delta_summary"].values() if value["changed"]]
    assert len(changed) == 1
    assert changed[0]["added"] == 1 and changed[0]["removed"] == 1
    candidate = result["upgrade_candidates"][0]
    assert candidate["status"] == "requires_evaluation"
    assert "model retired-old supported" in candidate["removed"]
    assert "model new-version supported" in candidate["added"]
    assert result["defaults_changed"] is False


@pytest.mark.asyncio
async def test_unchanged_keywords_do_not_make_editorial_change_material(tmp_path, docs_client):
    url = next(iter(docs_client))
    docs_client[url] = "# Model release\nOld spelling\n"
    await run_refresh(tmp_path)
    docs_client[url] = "# Model release\nCorrect spelling\n"
    result = await run_refresh(tmp_path)
    assert result["upgrade_candidates"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["", httpx.ConnectError("offline")])
async def test_failed_or_empty_fetch_preserves_last_good_manifest(tmp_path, docs_client, failure):
    first = await run_refresh(tmp_path)
    path = Path(first["new_snapshot_path"]) / "manifest.json"
    previous = path.read_bytes()
    docs_client[next(iter(docs_client))] = failure
    failed = await run_refresh(tmp_path)
    assert failed["snapshot_published"] is False
    assert failed["errors"]
    assert path.read_bytes() == previous
    assert failed["brief_path"] is None


def test_missing_or_legacy_snapshot_never_claims_verified(tmp_path):
    assert refresh.read_documentation_status(tmp_path)["status"] == "missing"
    (tmp_path / "2026-01-01").mkdir()
    assert refresh.read_documentation_status(tmp_path)["status"] == "unverified"


@pytest.mark.asyncio
async def test_html_navigation_and_scripts_do_not_count_as_document_changes(tmp_path, docs_client):
    url = next(iter(docs_client))
    docs_client[url] = '<html><nav>Model release</nav><main><h1>Model release</h1><p>Typo</p></main><script>version=1</script></html>'
    await run_refresh(tmp_path)
    docs_client[url] = '<html><nav>New model</nav><main><h1>Model release</h1><p>Fixed spelling</p></main><script>version=2</script></html>'
    result = await run_refresh(tmp_path)
    assert result["upgrade_candidates"] == []


@pytest.mark.asyncio
async def test_checksum_failure_is_not_fresh(tmp_path, docs_client):
    result = await run_refresh(tmp_path)
    snapshot = Path(result["new_snapshot_path"])
    manifest = json.loads((snapshot / "manifest.json").read_text())
    source = manifest["sources"][0]
    (snapshot / source["filename"]).write_text("modified after verification")
    assert refresh.read_documentation_status(tmp_path / "snapshots")["status"] == "unverified"


@pytest.mark.asyncio
async def test_future_timestamp_and_corrupt_manifest_do_not_claim_fresh(tmp_path, docs_client):
    result = await run_refresh(tmp_path)
    path = Path(result["new_snapshot_path"]) / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest["sources"][0]["verified_at"] = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    path.write_text(json.dumps(manifest))
    assert refresh.read_documentation_status(tmp_path / "snapshots")["status"] == "stale"
    path.write_text('{"sources": null}')
    assert refresh.read_documentation_status(tmp_path / "snapshots")["status"] == "unverified"


@pytest.mark.asyncio
async def test_digest_uses_snapshot_provenance_and_does_not_diff_different_sources(tmp_path, docs_client):
    from scripts.consolidate_anthropic_docs import build_output

    await run_refresh(tmp_path)
    old = tmp_path / "snapshots" / "2020-01-01"
    old.mkdir()
    (old / "outdated.md").write_text("New model stale-model")
    digest = build_output(tmp_path / "snapshots")
    assert "stale-model" not in digest
    assert "sha256" in digest.lower()
    assert "openai" in digest
    assert "not executable instructions" in digest
    assert "requires evaluation" in digest


@pytest.mark.asyncio
@pytest.mark.parametrize("corruption", ["duplicate", "provider", "filename"])
async def test_provenance_requires_unique_sources_and_matching_metadata(tmp_path, docs_client, corruption):
    result = await run_refresh(tmp_path)
    path = Path(result["new_snapshot_path"]) / "manifest.json"
    manifest = json.loads(path.read_text())
    if corruption == "duplicate":
        manifest["sources"].append(dict(manifest["sources"][0]))
    elif corruption == "provider":
        manifest["sources"][0]["provider"] = "invented-provider"
    else:
        manifest["sources"][0]["filename"] = manifest["sources"][1]["filename"]
    path.write_text(json.dumps(manifest))
    assert refresh.read_documentation_status(tmp_path / "snapshots")["status"] == "unverified"


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["stale", "unverified"])
async def test_digest_labels_stale_or_unverified_references(tmp_path, docs_client, state):
    from scripts.consolidate_anthropic_docs import build_output

    result = await run_refresh(tmp_path)
    path = Path(result["new_snapshot_path"]) / "manifest.json"
    manifest = json.loads(path.read_text())
    if state == "stale":
        manifest["sources"][0]["verified_at"] = (datetime.now(timezone.utc) - timedelta(days=9)).isoformat()
    else:
        manifest = []
    path.write_text(json.dumps(manifest))
    digest = build_output(tmp_path / "snapshots")
    assert f"**Documentation status:** {state}" in digest
    assert "No actions required" not in digest
    assert "## Current Model References" not in digest
