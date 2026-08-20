from __future__ import annotations

import json
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CHECKER = REPO_ROOT / "scripts" / "unlazy-gate-check.mjs"


def repo_fixture(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(
        [
            "git", "-c", "user.name=Unlazy Test", "-c", "user.email=unlazy@example.invalid",
            "commit", "--allow-empty", "-q", "-m", "fixture",
        ],
        cwd=tmp_path,
        check=True,
    )
    return tmp_path


def run_checker(root: Path, gate: Path, *args: str):
    return subprocess.run(
        ["node", str(CHECKER), "--json", *args, gate.name],
        cwd=root,
        text=True,
        capture_output=True,
    )


def write_gate(root: Path, body: str) -> Path:
    path = root / "GATES.md"
    path.write_text(body)
    return path


def test_expected_text_cannot_override_nonzero_exit(tmp_path):
    root = repo_fixture(tmp_path)
    gate = write_gate(
        root,
        """- [ ] G1: command really succeeds
  CHECK: node -e \"console.log('EXPECTED'); process.exit(7)\"
  EXIT: 0
  EXPECT: EXPECTED
  TIMEOUT: 10
  EVIDENCE: pending
""",
    )
    result = run_checker(root, gate)
    assert result.returncode == 1
    receipt = json.loads(result.stdout)
    assert receipt["verified"] is True
    assert len(receipt["candidate_sha"]) == 40
    assert receipt["summary"]["failed"] == 1
    assert receipt["gates"][0]["exitCode"] == 7
    assert receipt["gates"][0]["expectMatched"] is True


def test_exit_and_expectation_both_pass(tmp_path):
    root = repo_fixture(tmp_path)
    gate = write_gate(
        root,
        """- [ ] G1: exact marker appears
  CHECK: node -e \"console.log('READY')\"
  EXIT: 0
  EXPECT: /REA(DY)/
  EVIDENCE: pending
""",
    )
    result = run_checker(root, gate)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["summary"]["passed"] == 1


def test_status_is_read_only_and_never_reverifies(tmp_path):
    root = repo_fixture(tmp_path)
    marker = root / "should-not-exist"
    gate = write_gate(
        root,
        f"""- [ ] G1: status only
  CHECK: touch {marker.name}
  EXIT: 0
  EVIDENCE: pending
""",
    )
    result = run_checker(root, gate, "--status")
    assert result.returncode == 1
    assert not marker.exists()
    assert json.loads(result.stdout)["summary"]["pending"] == 1


def test_abandoned_gate_blocks_strict_completion(tmp_path):
    root = repo_fixture(tmp_path)
    gate = write_gate(
        root,
        """- [ ] G1: required result
  CHECK: node -e \"process.exit(0)\"
  EXIT: 0
  EVIDENCE: pending
ABANDON: G1 upstream decision missing
""",
    )
    result = run_checker(root, gate)
    assert result.returncode == 1
    assert json.loads(result.stdout)["summary"]["abandoned"] == 1


def test_duplicate_shared_check_executes_once(tmp_path):
    root = repo_fixture(tmp_path)
    command = "node -e \"const fs=require('fs');let n=fs.existsSync('count')?+fs.readFileSync('count','utf8'):0;fs.writeFileSync('count',String(n+1));console.log('OK')\""
    gate = write_gate(
        root,
        f"""- [ ] G1: first consumer
  CHECK: {command}
  EXIT: 0
  EXPECT: OK
  EVIDENCE: pending
- [ ] G2: second consumer
  CHECK: {command}
  EXIT: 0
  EXPECT: OK
  EVIDENCE: pending
""",
    )
    result = run_checker(root, gate, "--jobs", "2")
    assert result.returncode == 0, result.stderr
    assert (root / "count").read_text() == "1"
    assert json.loads(result.stdout)["summary"]["passed"] == 2


def test_invalid_regex_is_runner_error(tmp_path):
    root = repo_fixture(tmp_path)
    gate = write_gate(
        root,
        """- [ ] G1: regex must compile
  CHECK: node -e \"console.log('OK')\"
  EXIT: 0
  EXPECT: /[/
  EVIDENCE: pending
""",
    )
    result = run_checker(root, gate)
    assert result.returncode == 2
    assert json.loads(result.stdout)["summary"]["runner_errors"] == 1
