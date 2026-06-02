from __future__ import annotations

import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from tao.repo_intake import (  # noqa: E402
    apply_repo_scan,
    build_repo_intake_audit,
    clone_repo_to_sandbox,
    extract_source_url,
    scan_local_repo,
    slug_for_source,
    write_repo_intake_audit,
    write_repo_intake_clone_scan,
    write_repo_intake_scan,
)


def test_extract_source_url_trims_sentence_punctuation():
    assert extract_source_url("scan https://github.com/example/tool.git, then advise") == "https://github.com/example/tool.git"


def test_repo_intake_audit_is_local_no_build_receipt():
    audit = build_repo_intake_audit(
        "implement https://github.com/can1357/oh-my-pi.git with 40+ providers and Rust core",
        now=dt.datetime(2026, 6, 2, 6, 45, tzinfo=dt.timezone.utc),
    )
    assert audit["route"] == "repo-intake"
    assert audit["status"] == "intake-required"
    assert audit["no_build_started"] is True
    assert audit["verification"]["network_calls"] == 0
    assert audit["verification"]["repository_mutations"] == 0
    assert audit["fit_classification"] == "pending-read-only-scan"
    assert "40+ providers" in audit["capability_claims"]


def test_slug_for_source_is_stable_and_safe():
    slug = slug_for_source("https://github.com/Example/Tool.git", "ignored")
    assert slug.startswith("github-com-example-tool-")
    assert slug == slug_for_source("https://github.com/Example/Tool.git", "ignored")


def test_write_repo_intake_audit_creates_json_and_markdown(tmp_path: Path):
    result = write_repo_intake_audit(
        "look at https://github.com/example/tool.git for LSP DAP ops",
        tmp_path,
        now=dt.datetime(2026, 6, 2, 6, 45, tzinfo=dt.timezone.utc),
    )
    json_path = Path(result["json_path"])
    md_path = Path(result["markdown_path"])
    assert json_path.exists()
    assert md_path.exists()
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["source_url"] == "https://github.com/example/tool.git"
    assert payload["recommended_next_lane"] == "repo-intake-read-only-scan"
    assert "No build started: True" in md_path.read_text(encoding="utf-8")


def test_route_cli_write_audit_outputs_paths(tmp_path: Path):
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/route_build_method.py",
            "--json",
            "--write-audit",
            "--audits-dir",
            str(tmp_path),
            "build https://github.com/example/tool.git now",
        ],
        cwd=REPO_ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    payload = json.loads(completed.stdout)
    assert payload["route"] == "repo-intake"
    assert Path(payload["audit_json_path"]).exists()
    assert Path(payload["audit_markdown_path"]).exists()
    assert completed.stderr == ""


def test_route_cli_refuses_audit_for_non_repo_intake(tmp_path: Path):
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/route_build_method.py",
            "--write-audit",
            "--audits-dir",
            str(tmp_path),
            "build a local feature",
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
    )
    assert completed.returncode == 2
    assert "only valid for repo-intake" in completed.stderr
    assert not list(tmp_path.iterdir())


def _write_fixture_repo(root: Path) -> None:
    (root / ".github" / "workflows").mkdir(parents=True)
    (root / "README.md").write_text("# Example Tool\n\nA typed provider registry with CLI helpers.", encoding="utf-8")
    (root / "LICENSE").write_text("MIT License\n\nPermission is hereby granted, free of charge...", encoding="utf-8")
    (root / "package.json").write_text(
        json.dumps({"scripts": {"test": "vitest", "lint": "pnpm lint", "type-check": "pnpm type-check"}}),
        encoding="utf-8",
    )
    (root / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
    (root / ".github" / "workflows" / "ci.yml").write_text(
        "name: ci\nsteps:\n  - run: pnpm test\n  - run: pnpm lint\n",
        encoding="utf-8",
    )


def test_scan_local_repo_detects_stack_license_manifests_and_ci(tmp_path: Path):
    _write_fixture_repo(tmp_path)
    scan = scan_local_repo(tmp_path)
    assert scan["scan_mode"] == "read-only-local-path"
    assert scan["network_calls"] == 0
    assert scan["repository_mutations"] == 0
    assert scan["license"] == "MIT"
    assert "typescript/javascript" in scan["detected_stack"]
    assert "github-actions" in scan["detected_stack"]
    assert "package.json" in scan["manifests"]
    assert ".github/workflows/ci.yml" in scan["manifests"]
    assert "pnpm test" in scan["ci_commands"]
    assert scan["fit_classification"] == "tool-adoption"


def test_apply_repo_scan_updates_audit_next_lane(tmp_path: Path):
    _write_fixture_repo(tmp_path)
    audit = build_repo_intake_audit("scan https://github.com/example/tool.git")
    updated = apply_repo_scan(audit, scan_local_repo(tmp_path))
    assert updated["fit_classification"] == "tool-adoption"
    assert updated["recommended_next_lane"] == "spike-or-feature-with-tests"
    assert updated["verification"]["read_only_scan"] is True
    assert updated["verification"]["repository_mutations"] == 0


def test_write_repo_intake_scan_creates_enriched_markdown(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_fixture_repo(repo)
    out = tmp_path / "audits"
    result = write_repo_intake_scan("scan https://github.com/example/tool.git", out, repo)
    payload = json.loads(Path(result["json_path"]).read_text(encoding="utf-8"))
    markdown = Path(result["markdown_path"]).read_text(encoding="utf-8")
    assert payload["fit_classification"] == "tool-adoption"
    assert payload["license"] == "MIT"
    assert "Read-only scan evidence" in markdown
    assert "pnpm test" in markdown


def test_route_cli_scan_path_writes_enriched_audit(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_fixture_repo(repo)
    audits = tmp_path / "audits"
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/route_build_method.py",
            "--json",
            "--scan-path",
            str(repo),
            "--audits-dir",
            str(audits),
            "scan https://github.com/example/tool.git",
        ],
        cwd=REPO_ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    route = json.loads(completed.stdout)
    payload = json.loads(Path(route["audit_json_path"]).read_text(encoding="utf-8"))
    assert route["fit_classification"] == "tool-adoption"
    assert payload["verification"]["read_only_scan"] is True
    assert payload["verification"]["network_calls"] == 0
    assert payload["verification"]["repository_mutations"] == 0


def test_clone_repo_to_sandbox_uses_shallow_filtered_clone(monkeypatch, tmp_path: Path):
    def fake_run(cmd, text, capture_output, check):
        target = Path(cmd[-1])
        target.mkdir(parents=True)
        _write_fixture_repo(target)
        class Result:
            returncode = 0
            stdout = ""
            stderr = "cloned"
        return Result()

    monkeypatch.setattr("tao.repo_intake.subprocess.run", fake_run)
    clone = clone_repo_to_sandbox("https://github.com/example/tool.git", tmp_path)
    assert Path(clone["sandbox_path"]).exists()
    assert clone["clone_command"] == "git clone --depth 1 --filter=blob:none <source_url> <sandbox_path>"
    assert clone["network_calls"] == 1
    assert clone["repository_mutations"] == 0
    assert clone["build_started"] is False


def test_write_repo_intake_clone_scan_combines_clone_and_scan(monkeypatch, tmp_path: Path):
    def fake_run(cmd, text, capture_output, check):
        target = Path(cmd[-1])
        target.mkdir(parents=True)
        _write_fixture_repo(target)
        class Result:
            returncode = 0
            stdout = ""
            stderr = "cloned"
        return Result()

    monkeypatch.setattr("tao.repo_intake.subprocess.run", fake_run)
    result = write_repo_intake_clone_scan(
        "scan https://github.com/example/tool.git",
        tmp_path / "audits",
        tmp_path / "sandbox",
    )
    payload = json.loads(Path(result["json_path"]).read_text(encoding="utf-8"))
    markdown = Path(result["markdown_path"]).read_text(encoding="utf-8")
    assert payload["fit_classification"] == "tool-adoption"
    assert payload["verification"]["network_calls"] == 1
    assert payload["verification"]["repository_mutations"] == 0
    assert payload["verification"]["build_started"] is False
    assert "Sandbox path:" in markdown


def test_route_cli_rejects_scan_path_with_sandbox_clone(tmp_path: Path):
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/route_build_method.py",
            "--sandbox-clone",
            "--scan-path",
            str(tmp_path),
            "scan https://github.com/example/tool.git",
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
    )
    assert completed.returncode == 2
    assert "either --sandbox-clone or --scan-path" in completed.stderr
