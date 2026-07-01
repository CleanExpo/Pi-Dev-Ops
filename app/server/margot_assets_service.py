"""Margot asset preview service — wraps scripts/margot_generate for dashboard use."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts import margot_generate as MG

_PACKET_NAME_RE = re.compile(r"^margot-build-packet-\d{8}T\d{6}Z\.json$")
_GENERATED_NAME_RE = re.compile(r"^margot-[a-z0-9-]+\.png$")


class MargotAssetsError(ValueError):
    """User-facing asset preview error."""


def get_options() -> dict[str, Any]:
    manifest = MG.load_manifest()
    opts = MG.list_options(manifest)
    return {
        "schema_version": manifest["schema_version"],
        "canonical_name": manifest["canonical_name"],
        "model": manifest["openai"]["model"],
        "canonical_asset_path": manifest["canonical_asset_path"],
        "canonical_asset_exists": Path(manifest["canonical_asset_path"]).exists(),
        "projects": opts["projects"],
        "variants": opts["variants"],
        "matrix_item_count": len(opts["projects"]) * len(opts["variants"]),
    }


def preview_asset(*, project: str, variant: str, notes: str = "") -> dict[str, Any]:
    manifest = MG.load_manifest()
    payload = MG.build_image_payload(
        manifest, project=project, variant=variant, notes=notes,
    )
    image_path, provenance_path = MG.output_paths(
        manifest, project=project, variant=variant, prompt=payload["prompt"],
    )
    provenance = MG.build_provenance(
        manifest,
        project=project,
        variant=variant,
        payload=payload,
        output_path=image_path,
    )
    return {
        "project": project,
        "variant": variant,
        "payload": payload,
        "provenance": provenance,
        "planned_image_path": str(image_path),
        "planned_provenance_path": str(provenance_path),
    }


def list_build_packets(*, limit: int = 10) -> list[dict[str, Any]]:
    root = MG.REPO_ROOT / ".harness/margot/build-packets"
    if not root.is_dir():
        return []
    rows: list[dict[str, Any]] = []
    for path in sorted(root.glob("margot-build-packet-*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        if not _PACKET_NAME_RE.match(path.name):
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        rows.append({
            "filename": path.name,
            "path": str(path),
            "modified_at": datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat(),
            "item_count": int(data.get("item_count", 0)),
            "mode": data.get("mode", ""),
        })
        if len(rows) >= limit:
            break
    return rows


def read_build_packet(filename: str) -> dict[str, Any]:
    if not _PACKET_NAME_RE.match(filename):
        raise MargotAssetsError(f"Invalid build packet name: {filename}")
    path = MG.REPO_ROOT / ".harness/margot/build-packets" / filename
    if not path.is_file():
        raise MargotAssetsError(f"Build packet not found: {filename}")
    return json.loads(path.read_text(encoding="utf-8"))


def create_build_packet(
    *,
    projects: list[str] | None = None,
    variants: list[str] | None = None,
    notes: str = "",
) -> dict[str, Any]:
    manifest = MG.load_manifest()
    packet = MG.build_matrix_packet(
        manifest, projects=projects, variants=variants, notes=notes,
    )
    path = MG.write_build_packet(packet)
    return {
        "build_packet": str(path),
        "filename": path.name,
        "item_count": packet["item_count"],
        "mode": packet["mode"],
    }


def list_generated_assets(*, limit: int = 20) -> list[dict[str, Any]]:
    root = MG.REPO_ROOT / ".harness/margot/generated-assets"
    if not root.is_dir():
        return []
    rows: list[dict[str, Any]] = []
    for path in sorted(root.glob("margot-*.png"), key=lambda p: p.stat().st_mtime, reverse=True):
        if not _GENERATED_NAME_RE.match(path.name):
            continue
        prov = path.with_suffix(".json")
        rows.append({
            "filename": path.name,
            "path": str(path),
            "modified_at": datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat(),
            "size_bytes": path.stat().st_size,
            "has_provenance": prov.is_file(),
            "provenance_path": str(prov) if prov.is_file() else "",
        })
        if len(rows) >= limit:
            break
    return rows
