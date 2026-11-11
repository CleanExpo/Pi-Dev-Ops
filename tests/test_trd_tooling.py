"""TRD gate tooling (.trd/tooling/trd): fail-closed behaviour on malformed input (PR #1015 review)."""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOLING = ROOT / ".trd" / "tooling"
sys.path.insert(0, str(TOOLING))

from trd import base, checks, cli, legacy  # noqa: E402


def _run_cli(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    env = {"PYTHONPATH": str(TOOLING), "PATH": "/usr/bin:/bin"}
    return subprocess.run([sys.executable, "-m", "trd", *args], cwd=cwd, env=env,
                          capture_output=True, text=True, check=False)


def test_days_since_rejects_non_string_with_type_error() -> None:
    with pytest.raises(TypeError):
        base.days_since(20261111)


def test_numeric_timestamp_is_an_issue_not_a_crash(tmp_path: Path) -> None:
    (tmp_path / "s.txt").write_text("evidence text here\n")
    digest = hashlib.sha256((tmp_path / "s.txt").read_bytes()).hexdigest()
    source = {"id": "S1", "path": "s.txt", "sha256": digest, "publisher": "p", "title": "t",
              "independence_group": "g", "source_type": "primary", "retrieved_at": 12345,
              "origin": {"status": "attested", "method": "m", "checked_by": "x", "checked_at": 12345}}
    case = {"case_id": "C", "jurisdiction": "AU", "sources": [source],
            "claims": [{"id": "K1", "risk": "routine", "type": "summary", "text": "t", "context": "c"}]}
    report = checks.check_case(case, tmp_path)
    codes = {i["code"] for c in report["claims"] for i in c["issues"]}
    assert report["status"] in ("HOLD", "BLOCK")
    assert "SOURCE_RETRIEVAL_TIME" in codes or report["status"] == "BLOCK"


def test_gate_cli_fails_closed_with_exit_3_on_non_object_case(tmp_path: Path) -> None:
    (tmp_path / "case.json").write_text(json.dumps(["not", "an", "object"]))
    (tmp_path / "rv").mkdir()
    result = _run_cli("packets", "case.json", "--root", ".", "--out", "out", cwd=tmp_path)
    assert result.returncode == 3, result.stderr
    assert "fail closed" in result.stderr


def test_review_template_does_not_pre_attest_independence(tmp_path: Path) -> None:
    case = {"case_id": "C", "claims": [{"id": "K1"}]}
    packet = cli._packet("Claude", case, "h" * 64, str(tmp_path))
    assert packet["review_template"]["independent_context"] is False


def test_backfill_survives_a_file_that_vanishes_after_inventory(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "keep.md").write_text("A paragraph that is clearly long enough to be a candidate.\n")
    (tmp_path / "gone.md").write_text("Another paragraph long enough to be counted as a candidate.\n")
    real_inventory = legacy.inventory

    def inventory_then_delete(root):
        records = real_inventory(root)
        (tmp_path / "gone.md").unlink()
        return records

    monkeypatch.setattr(legacy, "inventory", inventory_then_delete)
    result = legacy.backfill(tmp_path)
    by_path = {f["path"]: f for f in result["files"]}
    assert by_path["keep.md"]["candidates"]
    assert by_path["gone.md"]["candidates"] == []


def test_backfill_skips_text_whose_hash_changed_after_inventory(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "doc.md"
    target.write_text("Original paragraph long enough to be counted as a candidate.\n")
    real_inventory = legacy.inventory

    def inventory_then_edit(root):
        records = real_inventory(root)
        target.write_text("Edited paragraph that was never fingerprinted by inventory.\n")
        return records

    monkeypatch.setattr(legacy, "inventory", inventory_then_edit)
    item = legacy.backfill(tmp_path)["files"][0]
    assert item["candidates"] == []
    assert "changed" in item["next_step"]


INIT_FOLDERS = ["cases", "evidence", "reviews", "results", "legacy"]


def _is_git_ignored(repo: Path, rel: str) -> bool:
    result = subprocess.run(["git", "check-ignore", "-q", rel], cwd=repo, check=False)
    return result.returncode == 0


def test_init_gitignores_every_folder_it_creates(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    assert _run_cli("init", str(tmp_path), cwd=tmp_path).returncode == 0
    for folder in INIT_FOLDERS:
        assert (tmp_path / ".trd" / folder).is_dir()
        assert _is_git_ignored(tmp_path, f".trd/{folder}/record.json"), folder


def test_committed_trd_gitignore_covers_case_records() -> None:
    for folder in INIT_FOLDERS:
        assert _is_git_ignored(ROOT, f".trd/{folder}/record.json"), folder
