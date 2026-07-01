#!/usr/bin/env python3
"""Generate deterministic Margot image prompts and optional OpenAI image assets."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import sys
import textwrap
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = REPO_ROOT / ".harness/margot/assets/margot_identity.json"


class MargotGenerationError(RuntimeError):
    """Raised for user-facing generator errors."""


def load_manifest(path: Path = DEFAULT_MANIFEST) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise MargotGenerationError(f"Manifest not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise MargotGenerationError(f"Manifest is not valid JSON: {path}: {exc}") from exc
    validate_manifest(data)
    return data


def validate_manifest(manifest: dict[str, Any], *, require_asset: bool = False) -> None:
    required = [
        "schema_version",
        "canonical_name",
        "canonical_asset_path",
        "openai",
        "identity",
        "base_prompt",
        "projects",
        "variants",
        "safety_rules",
    ]
    missing = [key for key in required if key not in manifest]
    if missing:
        raise MargotGenerationError(f"Manifest missing required keys: {', '.join(missing)}")
    if manifest["openai"].get("model") != "gpt-image-2":
        raise MargotGenerationError("Margot generation must use gpt-image-2")
    if require_asset and not Path(manifest["canonical_asset_path"]).exists():
        raise MargotGenerationError(
            f"Canonical Margot asset missing: {manifest['canonical_asset_path']}",
        )


def list_options(manifest: dict[str, Any]) -> dict[str, list[str]]:
    return {
        "projects": sorted(manifest["projects"].keys()),
        "variants": sorted(manifest["variants"].keys()),
    }


def _resolve_project(manifest: dict[str, Any], project: str) -> dict[str, str]:
    try:
        return manifest["projects"][project]
    except KeyError as exc:
        valid = ", ".join(sorted(manifest["projects"].keys()))
        raise MargotGenerationError(f"Unknown project '{project}'. Valid projects: {valid}") from exc


def _resolve_variant(manifest: dict[str, Any], variant: str) -> dict[str, str]:
    try:
        return manifest["variants"][variant]
    except KeyError as exc:
        valid = ", ".join(sorted(manifest["variants"].keys()))
        raise MargotGenerationError(f"Unknown variant '{variant}'. Valid variants: {valid}") from exc


def build_prompt(
    manifest: dict[str, Any],
    *,
    project: str,
    variant: str,
    notes: str = "",
) -> str:
    project_spec = _resolve_project(manifest, project)
    variant_spec = _resolve_variant(manifest, variant)
    safety = "\n".join(f"- {rule}" for rule in manifest["safety_rules"])
    optional_notes = notes.strip()
    sections = [
        manifest["base_prompt"].strip(),
        f"Project surface: {project_spec['display_name']}. {project_spec['overlay']}",
        f"Variant: {variant_spec['direction']}",
        "Composition requirements: photorealistic, premium commercial lighting, professional posture, "
        "natural skin texture, clean business software brand aesthetic, reusable across Unite-Group portfolio products.",
        f"Safety and brand rules:\n{safety}",
    ]
    if optional_notes:
        sections.append(f"Additional operator notes: {optional_notes}")
    return "\n\n".join(sections)


def build_image_payload(
    manifest: dict[str, Any],
    *,
    project: str,
    variant: str,
    notes: str = "",
) -> dict[str, Any]:
    openai_cfg = manifest["openai"]
    return {
        "model": openai_cfg["model"],
        "prompt": build_prompt(manifest, project=project, variant=variant, notes=notes),
        "size": openai_cfg.get("size", "1024x1536"),
        "quality": openai_cfg.get("quality", "high"),
        "n": int(openai_cfg.get("n", 1)),
    }


def asset_slug(*, project: str, variant: str, prompt: str) -> str:
    digest = hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:10]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"margot-{project}-{variant}-{stamp}-{digest}"


def build_provenance(
    manifest: dict[str, Any],
    *,
    project: str,
    variant: str,
    payload: dict[str, Any],
    output_path: Path | None = None,
) -> dict[str, Any]:
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "generator": "scripts/margot_generate.py",
        "schema_version": manifest["schema_version"],
        "canonical_name": manifest["canonical_name"],
        "canonical_asset_path": manifest["canonical_asset_path"],
        "canonical_wiki_page": manifest.get("canonical_wiki_page", ""),
        "project": project,
        "variant": variant,
        "model": payload["model"],
        "size": payload["size"],
        "quality": payload["quality"],
        "prompt_sha256": hashlib.sha256(payload["prompt"].encode("utf-8")).hexdigest(),
        "output_path": str(output_path) if output_path else "",
        "safety_rules": manifest["safety_rules"],
    }


def output_paths(manifest: dict[str, Any], *, project: str, variant: str, prompt: str) -> tuple[Path, Path]:
    output_dir = REPO_ROOT / manifest.get("default_output_dir", ".harness/margot/generated-assets")
    slug = asset_slug(project=project, variant=variant, prompt=prompt)
    return output_dir / f"{slug}.png", output_dir / f"{slug}.json"


def write_live_image(
    manifest: dict[str, Any],
    *,
    payload: dict[str, Any],
    image_path: Path,
    provenance_path: Path,
    provenance: dict[str, Any],
) -> None:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise MargotGenerationError("OPENAI_API_KEY is required for --live mode")
    endpoint = manifest["openai"]["endpoint"]
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": " ".join(("Bearer", api_key)),
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:  # noqa: S310 - fixed OpenAI endpoint
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise MargotGenerationError(f"OpenAI image generation failed HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise MargotGenerationError(f"OpenAI image generation failed: {exc.reason}") from exc
    image_data = ((body.get("data") or [{}])[0] or {}).get("b64_json")
    if not image_data:
        raise MargotGenerationError("OpenAI response did not include data[0].b64_json")
    image_path.parent.mkdir(parents=True, exist_ok=True)
    image_path.write_bytes(base64.b64decode(image_data))
    provenance["output_path"] = str(image_path)
    provenance["openai_response_id"] = body.get("id", "")
    provenance_path.write_text(json.dumps(provenance, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate Margot image prompts and optional OpenAI image assets.",
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--project", default="unite-group")
    parser.add_argument("--variant", default="avatar")
    parser.add_argument("--notes", default="")
    parser.add_argument("--dry-run", action="store_true", help="Print payload and provenance preview. Default mode.")
    parser.add_argument("--live", action="store_true", help="Call OpenAI Image API and write PNG/provenance files.")
    parser.add_argument("--require-asset", action="store_true", help="Require canonical avatar file to exist.")
    parser.add_argument("--list", action="store_true", help="List valid projects and variants.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        manifest = load_manifest(args.manifest)
        validate_manifest(manifest, require_asset=bool(args.live or args.require_asset))
        if args.list:
            print(json.dumps(list_options(manifest), indent=2, sort_keys=True))
            return 0
        payload = build_image_payload(
            manifest,
            project=args.project,
            variant=args.variant,
            notes=args.notes,
        )
        image_path, provenance_path = output_paths(
            manifest,
            project=args.project,
            variant=args.variant,
            prompt=payload["prompt"],
        )
        provenance = build_provenance(
            manifest,
            project=args.project,
            variant=args.variant,
            payload=payload,
            output_path=image_path,
        )
        if args.live:
            write_live_image(
                manifest,
                payload=payload,
                image_path=image_path,
                provenance_path=provenance_path,
                provenance=provenance,
            )
            print(json.dumps({"image": str(image_path), "provenance": str(provenance_path)}, indent=2))
            return 0
        print(json.dumps({"payload": payload, "provenance": provenance}, indent=2, sort_keys=True))
        return 0
    except MargotGenerationError as exc:
        print(textwrap.fill(str(exc), width=100), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
