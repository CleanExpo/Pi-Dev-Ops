from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
COVERAGE_CHECK_SCRIPT = Path(
    os.environ.get("COVERAGE_CHECK_SCRIPT", ROOT / "scripts" / "coverage_check.py")
)
SPEC = importlib.util.spec_from_file_location(
    "coverage_check_under_test", COVERAGE_CHECK_SCRIPT
)
assert SPEC and SPEC.loader
coverage_check = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(coverage_check)


def test_command_probe_rejects_legacy_cmd_without_execution(monkeypatch, tmp_path):
    def unexpected_run(*_args, **_kwargs):
        pytest.fail("legacy command reached subprocess.run")

    monkeypatch.setattr(coverage_check.subprocess, "run", unexpected_run)

    status, evidence = coverage_check.probe_command(
        tmp_path,
        {"cmd": "printf unsafe", "expect_exit": 0},
    )

    assert status == coverage_check.FAIL
    assert evidence == "legacy cmd strings are not supported; use argv or steps"


@pytest.mark.parametrize(
    "requirement",
    [
        {},
        {"argv": ["true"], "steps": [["true"]]},
        {"argv": "true"},
        {"argv": []},
        {"argv": [""]},
        {"argv": ["true", 1]},
        {"steps": []},
        {"steps": [[]]},
        {"steps": [["true"], "false"]},
    ],
)
def test_command_probe_rejects_malformed_vectors_without_execution(
    monkeypatch, tmp_path, requirement
):
    def unexpected_run(*_args, **_kwargs):
        pytest.fail("malformed command reached subprocess.run")

    monkeypatch.setattr(coverage_check.subprocess, "run", unexpected_run)

    status, _ = coverage_check.probe_command(tmp_path, requirement)

    assert status == coverage_check.FAIL


def test_command_probe_treats_shell_metacharacters_as_literal_arguments(tmp_path):
    marker = tmp_path / "shell-substitution-ran"
    token = "$(touch shell-substitution-ran); echo chained"

    status, evidence = coverage_check.probe_command(
        tmp_path,
        {"argv": [sys.executable, "-c", "import sys; print(sys.argv[1])", token]},
    )

    assert status == coverage_check.PASS
    assert "shell-substitution-ran" in evidence
    assert not marker.exists()


def test_command_probe_preserves_expected_exit_and_disables_shell(monkeypatch, tmp_path):
    captured = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        captured.update(kwargs)
        return subprocess.CompletedProcess(argv, 7, "", "expected failure")

    monkeypatch.setattr(coverage_check.subprocess, "run", fake_run)

    status, evidence = coverage_check.probe_command(
        tmp_path,
        {"argv": ["checker", "--strict"], "expect_exit": 7},
    )

    assert status == coverage_check.PASS
    assert "exit 7 (expected 7)" in evidence
    assert captured["argv"] == ["checker", "--strict"]
    assert captured["shell"] is False


def test_command_probe_reports_timeout_as_failure(monkeypatch, tmp_path):
    def fake_run(argv, **_kwargs):
        raise subprocess.TimeoutExpired(argv, 3)

    monkeypatch.setattr(coverage_check.subprocess, "run", fake_run)

    status, evidence = coverage_check.probe_command(
        tmp_path,
        {"argv": ["slow-check"], "timeout": 3},
    )

    assert status == coverage_check.FAIL
    assert evidence == "timed out after 3s running: ['slow-check']"


def test_command_probe_runs_steps_in_order_and_short_circuits(monkeypatch, tmp_path):
    calls = []

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs["shell"]))
        returncode = 9 if argv[0] == "reject" else 0
        output = "FIRST_EVIDENCE" if argv[0] == "prepare" else ""
        return subprocess.CompletedProcess(argv, returncode, output, "")

    monkeypatch.setattr(coverage_check.subprocess, "run", fake_run)

    status, evidence = coverage_check.probe_command(
        tmp_path,
        {
            "steps": [["prepare"], ["reject"], ["must-not-run"]],
            "expect_exit": 9,
        },
    )

    assert status == coverage_check.PASS
    assert "exit 9 (expected 9)" in evidence
    assert "FIRST_EVIDENCE" in evidence
    assert calls == [(["prepare"], False), (["reject"], False)]


def test_command_probe_applies_timeout_to_the_whole_step_sequence(tmp_path):
    started = time.monotonic()
    status, evidence = coverage_check.probe_command(
        tmp_path,
        {
            "steps": [
                [sys.executable, "-c", "import time; time.sleep(0.6)"],
                [sys.executable, "-c", "import time; time.sleep(0.6)"],
            ],
            "timeout": 1,
        },
    )
    elapsed = time.monotonic() - started

    assert status == coverage_check.FAIL
    assert evidence.startswith("timed out after 1s")
    assert elapsed < 1.4


def test_default_repo_supports_legacy_harness_dod_location(tmp_path):
    repo = tmp_path / "repo"
    dod_dir = repo / ".harness" / "dod"
    dod_dir.mkdir(parents=True)
    (repo / "marker.txt").write_text("present", encoding="utf-8")
    dod = dod_dir / "compat.dod.yaml"
    dod.write_text(
        "project_id: compat\n"
        "requirements:\n"
        "  - id: marker\n"
        "    check: path_exists\n"
        "    path: marker.txt\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "coverage_check.py"), str(dod), "--json"],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )

    report = coverage_check.json.loads(result.stdout)
    assert report["passed"] == 1


def test_tracked_dod_migrates_all_five_command_probes():
    dod = coverage_check._load_yaml(
        ROOT / "config" / "harness" / "dod" / "pi-dev-ops-verification.dod.yaml"
    )
    probes = [req for req in dod["requirements"] if req.get("check") == "command"]

    assert len(probes) == 5
    assert all("cmd" not in probe for probe in probes)
    assert sum("argv" in probe for probe in probes) == 4
    assert sum("steps" in probe for probe in probes) == 1
    assert all(
        "&&" not in arg
        for probe in probes
        for step in ([probe["argv"]] if "argv" in probe else probe["steps"])
        for arg in step
    )


def test_tracked_dod_runs_end_to_end_without_legacy_command_strings(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "coverage_check.py"),
            str(ROOT / "config" / "harness" / "dod" / "pi-dev-ops-verification.dod.yaml"),
            "--json",
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )

    report = coverage_check.json.loads(result.stdout)
    assert report["project_id"] == "pi-dev-ops"
    assert all(
        "legacy cmd strings" not in item["evidence"] for item in report["results"]
    )
