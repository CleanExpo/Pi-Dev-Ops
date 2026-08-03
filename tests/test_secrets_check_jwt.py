"""Regression coverage for public Supabase anon JWT classification."""
from __future__ import annotations

import base64
import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "secrets_check.py"


def _jwt(role: str) -> str:
    def encoded(value: dict[str, str]) -> str:
        raw = json.dumps(value, separators=(",", ":")).encode()
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    return f"{encoded({'alg': 'HS256', 'typ': 'JWT'})}.{encoded({'iss': 'supabase', 'role': role})}.{'x' * 32}"


def _scan(tmp_path: Path, token: str) -> subprocess.CompletedProcess[str]:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "client.js").write_text(f'const KEY = "{token}";\n', encoding="utf-8")
    subprocess.run(["git", "add", "client.js"], cwd=tmp_path, check=True)
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--repo-root", str(tmp_path), "--dry-run"],
        text=True,
        capture_output=True,
        check=False,
    )


def test_public_supabase_anon_jwt_is_not_reported(tmp_path: Path) -> None:
    result = _scan(tmp_path, _jwt("anon"))
    assert result.returncode == 0, result.stdout + result.stderr


def test_supabase_service_role_jwt_still_fails_closed(tmp_path: Path) -> None:
    result = _scan(tmp_path, _jwt("service_role"))
    assert result.returncode == 1, result.stdout + result.stderr
    assert "JWT (Supabase service-role/anon key or similar)" in result.stdout
