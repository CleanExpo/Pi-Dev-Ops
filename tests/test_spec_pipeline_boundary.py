"""Boundary gate tests."""
from __future__ import annotations

from app.server.spec_pipeline.ship_gate import scan_proposal_boundary


def test_forbidden_path_blocks():
    result = scan_proposal_boundary("Update dashboard/middleware.ts auth redirect")
    assert result.tier == "blocked"
    assert any("middleware" in p for p in result.blocked_paths)


def test_auth_proxy_blocks():
    # middleware.ts was migrated to proxy.ts (b77c406d); the live auth file must stay forbidden.
    result = scan_proposal_boundary("Update dashboard/proxy.ts auth redirect")
    assert result.tier == "blocked"
    assert "dashboard/proxy.ts" in result.blocked_paths


def test_safe_proposal_ok():
    result = scan_proposal_boundary("Add spec pipeline panel to control page")
    assert result.tier == "ok"
