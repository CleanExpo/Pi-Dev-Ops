import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_secrets_check_detects_jwt_and_redacts_output(tmp_path):
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True, text=True)
    leaked = "eyJ" + "A" * 40 + "." + "B" * 40 + "." + "C" * 40
    (tmp_path / "leaky.py").write_text(f'SERVICE_KEY = "{leaked}"\n', encoding="utf-8")

    result = subprocess.run(
        ["python", str(REPO_ROOT / "scripts" / "secrets_check.py"), "--repo-root", str(tmp_path), "--dry-run"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )

    combined = result.stdout + result.stderr
    assert result.returncode == 1
    assert "JWT-like service token" in combined
    assert "<REDACTED_SECRET>" in combined
    assert leaked not in combined


def test_railway_check_failure_branch_uses_masking_guard():
    script = (REPO_ROOT / "scripts" / "railway_check.sh").read_text(encoding="utf-8")

    assert "mask_kv_stream()" in script
    assert 'printf \'%s\\n\' "$RAW" | mask_kv_stream' in script
    assert 'echo "$RAW"' not in script
