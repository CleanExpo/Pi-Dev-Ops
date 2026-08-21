from __future__ import annotations

import json
import subprocess
import time
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
        [
            "node", str(CHECKER), "--json",
            "--plan-id", "plan-1",
            "--node-id", "1.1",
            "--worker-id", "worker-a",
            "--verifier-id", "verifier-1",
            "--relevant-input", gate.name,
            *args,
            gate.name,
        ],
        cwd=root,
        text=True,
        capture_output=True,
    )


def write_gate(root: Path, body: str) -> Path:
    path = root / "GATES.md"
    path.write_text(body)
    subprocess.run(["git", "add", "--all"], cwd=root, check=True)
    subprocess.run(
        [
            "git", "-c", "user.name=Unlazy Test", "-c", "user.email=unlazy@example.invalid",
            "commit", "-q", "-m", "gate fixture",
        ],
        cwd=root,
        check=True,
    )
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
    receipt = json.loads(result.stdout)
    assert receipt["summary"]["passed"] == 1
    assert receipt["worktree_clean_before_run"] is True
    assert receipt["plan_id"] == "plan-1"
    assert receipt["node_id"] == "1.1"
    assert receipt["worker_id"] == "worker-a"
    assert receipt["verifier_id"] == "verifier-1"
    assert receipt["relevant_input_digest"].startswith("sha256:")


def test_verified_run_requires_plan_node_and_verifier_ids(tmp_path):
    root = repo_fixture(tmp_path)
    gate = write_gate(
        root,
        """- [ ] G1: exact marker appears
  CHECK: node -e \"console.log('READY')\"
  EXIT: 0
  EXPECT: READY
  EVIDENCE: pending
""",
    )
    result = subprocess.run(
        ["node", str(CHECKER), "--json", gate.name],
        cwd=root,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 2
    assert "--plan-id, --node-id, --worker-id, and --verifier-id are required" in result.stderr


def test_relevant_input_content_is_bound_to_receipt_digest(tmp_path):
    root = repo_fixture(tmp_path)
    relevant = root / "contract.json"
    relevant.write_text('{"version":1}\n')
    gate = write_gate(
        root,
        """- [ ] G1: status-bound gate
  CHECK: node -e \"console.log('READY')\"
  EXIT: 0
  EXPECT: READY
  EVIDENCE: pending
""",
    )
    first = run_checker(root, gate, "--status", "--relevant-input", relevant.name)
    relevant.write_text('{"version":2}\n')
    second = run_checker(root, gate, "--status", "--relevant-input", relevant.name)
    assert first.returncode == 1
    assert second.returncode == 1
    first_receipt = json.loads(first.stdout)
    second_receipt = json.loads(second.stdout)
    assert any(item["path"] == "contract.json" for item in first_receipt["relevant_inputs"])
    assert first_receipt["relevant_input_digest"] != second_receipt["relevant_input_digest"]


def test_relevant_input_mutation_changes_command_cache_key_at_same_sha(tmp_path):
    root = repo_fixture(tmp_path)
    gate = write_gate(
        root,
        """- [ ] G1: relevant-input-bound gate
  CHECK: node -e \"console.log('READY')\"
  EXIT: 0
  EXPECT: READY
  EVIDENCE: pending
""",
    )
    (root / ".git" / "info" / "exclude").write_text("runtime-contract.json\n")
    relevant = root / "runtime-contract.json"
    relevant.write_text('{"version":1}\n')
    first = run_checker(root, gate, "--relevant-input", relevant.name)
    relevant.write_text('{"version":2}\n')
    second = run_checker(root, gate, "--relevant-input", relevant.name)
    assert first.returncode == 0
    assert second.returncode == 0
    first_receipt = json.loads(first.stdout)
    second_receipt = json.loads(second.stdout)
    assert first_receipt["candidate_sha"] == second_receipt["candidate_sha"]
    assert first_receipt["relevant_input_digest"] != second_receipt["relevant_input_digest"]
    assert first_receipt["gates"][0]["commandDigest"] != second_receipt["gates"][0]["commandDigest"]


def test_same_process_recomputes_relevant_input_before_cache_lookup(tmp_path):
    root = repo_fixture(tmp_path)
    (root / ".git" / "info" / "exclude").write_text("runtime-contract.txt\n")
    relevant = root / "runtime-contract.txt"
    relevant.write_text("v1\n")
    command = (
        "node -e \"const fs=require('fs');const p='runtime-contract.txt';"
        "const v=fs.readFileSync(p,'utf8').trim();console.log(v);"
        "if(v==='v1')fs.writeFileSync(p,'v2\\n')\""
    )
    gate = write_gate(
        root,
        f"""- [ ] G1: first input version
  CHECK: {command}
  EXIT: 0
  EXPECT: v1
  EVIDENCE: pending
- [ ] G2: changed input version
  CHECK: {command}
  EXIT: 0
  EXPECT: v2
  EVIDENCE: pending
""",
    )
    result = run_checker(root, gate, "--jobs", "1", "--relevant-input", relevant.name)
    assert result.returncode == 0, result.stdout + result.stderr
    receipt = json.loads(result.stdout)
    assert [item["state"] for item in receipt["gates"]] == ["passed", "passed"]
    assert receipt["gates"][0]["relevantInputDigest"] != receipt["gates"][1]["relevantInputDigest"]
    assert receipt["gates"][0]["commandDigest"] != receipt["gates"][1]["commandDigest"]


def test_untracked_worktree_refuses_before_gate_execution(tmp_path):
    root = repo_fixture(tmp_path)
    marker = root / "should-not-exist"
    gate = write_gate(
        root,
        f"""- [ ] G1: must not run dirty code
  CHECK: touch {marker.name}
  EXIT: 0
  EXPECT: impossible
  EVIDENCE: pending
""",
    )
    (root / "untracked.py").write_text("dirty\n")
    result = run_checker(root, gate)
    assert result.returncode == 2
    assert "worktree must be clean" in result.stderr
    assert result.stdout == ""
    assert not marker.exists()


def test_tracked_worktree_refuses_before_gate_execution(tmp_path):
    root = repo_fixture(tmp_path)
    tracked = root / "tracked.py"
    tracked.write_text("clean\n")
    marker = root / "should-not-exist"
    gate = write_gate(
        root,
        f"""- [ ] G1: must not run dirty code
  CHECK: touch {marker.name}
  EXIT: 0
  EXPECT: impossible
  EVIDENCE: pending
""",
    )
    tracked.write_text("dirty\n")
    result = run_checker(root, gate)
    assert result.returncode == 2
    assert "worktree must be clean" in result.stderr
    assert result.stdout == ""
    assert not marker.exists()


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


def test_timeout_terminates_descendant_process_group(tmp_path):
    root = repo_fixture(tmp_path)
    marker = root / "late-marker"
    (root / "spawn-descendant.js").write_text(
        """const { spawn } = require('node:child_process');
const childCode = `
  const fs = require('node:fs');
  process.on('SIGTERM', () => {});
  setTimeout(() => fs.writeFileSync('late-marker', 'survived'), 1500);
`;
spawn(process.execPath, ['-e', childCode], { stdio: 'inherit' });
setTimeout(() => {}, 3000);
"""
    )
    gate = write_gate(
        root,
        """- [ ] G1: descendants are terminated on timeout
  CHECK: node spawn-descendant.js
  EXIT: 0
  EXPECT: impossible
  TIMEOUT: 1
  EVIDENCE: pending
""",
    )
    started = time.monotonic()
    result = run_checker(root, gate)
    elapsed = time.monotonic() - started
    assert result.returncode == 2
    assert elapsed < 2.0
    time.sleep(0.8)
    assert not marker.exists()
