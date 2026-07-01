from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts import margot_generate as MG  # noqa: E402


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
        "base_prompt": "Create Margot as a realistic professional Unite-Group assistant. No deliberate sexualisation.",
        "projects": {
            "unite-group": {"display_name": "Unite-Group", "overlay": "Nexus operator."},
            "synthex": {"display_name": "Synthex", "overlay": "Marketing automation."},
        },
        "variants": {
            "avatar": {"slug": "avatar", "direction": "Portrait avatar."},
            "dashboard": {"slug": "dashboard", "direction": "Dashboard companion."},
        },
        "safety_rules": [
            "Keep Margot realistic, original, adult, and professional.",
            "Do not add deliberate sexual emphasis or body-emphasis details.",
        ],
    }


def test_validate_manifest_requires_gpt_image_2(tmp_path: Path):
    manifest = _manifest(tmp_path)
    manifest["openai"]["model"] = "gpt-image-1"
    with pytest.raises(MG.MargotGenerationError, match="gpt-image-2"):
        MG.validate_manifest(manifest)


def test_validate_manifest_can_require_canonical_asset(tmp_path: Path):
    manifest = _manifest(tmp_path)
    MG.validate_manifest(manifest, require_asset=True)
    manifest["canonical_asset_path"] = str(tmp_path / "missing.png")
    with pytest.raises(MG.MargotGenerationError, match="Canonical Margot asset missing"):
        MG.validate_manifest(manifest, require_asset=True)


def test_build_prompt_includes_project_variant_and_safety(tmp_path: Path):
    manifest = _manifest(tmp_path)
    prompt = MG.build_prompt(
        manifest,
        project="synthex",
        variant="dashboard",
        notes="Use navy accents.",
    )
    assert "Create Margot" in prompt
    assert "Project surface: Synthex" in prompt
    assert "Marketing automation." in prompt
    assert "Dashboard companion." in prompt
    assert "Use navy accents." in prompt
    assert "Do not add deliberate sexual emphasis" in prompt


def test_unknown_project_fails_closed(tmp_path: Path):
    with pytest.raises(MG.MargotGenerationError, match="Unknown project"):
        MG.build_prompt(_manifest(tmp_path), project="unknown", variant="avatar")


def test_build_image_payload_shape(tmp_path: Path):
    payload = MG.build_image_payload(
        _manifest(tmp_path),
        project="unite-group",
        variant="avatar",
    )
    assert payload["model"] == "gpt-image-2"
    assert payload["size"] == "1024x1536"
    assert payload["quality"] == "high"
    assert payload["n"] == 1
    assert "Unite-Group" in payload["prompt"]


def test_provenance_has_prompt_hash_and_no_secret(tmp_path: Path):
    manifest = _manifest(tmp_path)
    payload = MG.build_image_payload(manifest, project="unite-group", variant="avatar")
    provenance = MG.build_provenance(
        manifest,
        project="unite-group",
        variant="avatar",
        payload=payload,
    )
    assert provenance["model"] == "gpt-image-2"
    assert len(provenance["prompt_sha256"]) == 64
    assert "OPENAI_API_KEY" not in json.dumps(provenance)


def test_cli_dry_run_outputs_payload(tmp_path: Path, capsys):
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(_manifest(tmp_path)), encoding="utf-8")
    code = MG.main([
        "--manifest",
        str(manifest_path),
        "--project",
        "unite-group",
        "--variant",
        "avatar",
        "--dry-run",
    ])
    assert code == 0
    out = json.loads(capsys.readouterr().out)
    assert out["payload"]["model"] == "gpt-image-2"
    assert out["provenance"]["canonical_name"] == "Margot"
