"""Tests for scripts/probe_dr_nrpg_stripe_keys.py"""
from __future__ import annotations

import json
from unittest.mock import patch

import scripts.probe_dr_nrpg_stripe_keys as probe_mod


def _health_payload(*, stripe_status: str, reason: str | None = None, key_mode: str | None = None):
    stripe: dict = {"status": stripe_status}
    if reason:
        stripe["reason"] = reason
    if key_mode:
        stripe["keyMode"] = key_mode
    return {
        "status": "healthy" if stripe_status == "healthy" else "unhealthy",
        "checks": {
            "database": {"status": "healthy"},
            "stripe": stripe,
            "storage": {"status": "healthy"},
        },
    }


def test_probe_egress_blocked_returns_exit_1():
    with patch.object(probe_mod, "_fetch_health", side_effect=OSError("tunnel failed")):
        result = probe_mod.probe("https://dr-nrpg-platform.vercel.app")
    assert result.exit_code == 1
    assert result.egress_reachable is False


def test_probe_stripe_not_configured_returns_exit_2():
    with (
        patch.object(
            probe_mod,
            "_fetch_health",
            return_value=(503, _health_payload(stripe_status="unhealthy", reason="not_configured")),
        ),
        patch.object(probe_mod, "_probe_checkout", return_value=(503, False)),
        patch.object(probe_mod, "_probe_webhook", return_value=(400, True)),
    ):
        result = probe_mod.probe("https://dr-nrpg-platform.vercel.app")
    assert result.exit_code == 2
    assert result.egress_reachable is True
    assert result.stripe_secret_configured is False
    assert result.webhook_secret_configured is True


def test_probe_stripe_healthy_without_webhook_returns_exit_3():
    with (
        patch.object(
            probe_mod,
            "_fetch_health",
            return_value=(200, _health_payload(stripe_status="healthy", key_mode="live")),
        ),
        patch.object(probe_mod, "_probe_checkout", return_value=(400, True)),
        patch.object(probe_mod, "_probe_webhook", return_value=(500, False)),
    ):
        result = probe_mod.probe("https://dr-nrpg-platform.vercel.app")
    assert result.exit_code == 3
    assert result.stripe_healthy is True
    assert result.webhook_secret_configured is False


def test_probe_all_green_returns_exit_0():
    with (
        patch.object(
            probe_mod,
            "_fetch_health",
            return_value=(200, _health_payload(stripe_status="healthy", key_mode="live")),
        ),
        patch.object(probe_mod, "_probe_checkout", return_value=(400, True)),
        patch.object(probe_mod, "_probe_webhook", return_value=(400, True)),
    ):
        result = probe_mod.probe("https://dr-nrpg-platform.vercel.app")
    assert result.exit_code == 0
    assert result.ok is True


def test_main_json_output(capsys):
    with patch.object(
        probe_mod,
        "probe",
        return_value=probe_mod.ProbeResult(
            ok=False,
            exit_code=2,
            egress_reachable=True,
            stripe_secret_configured=False,
            stripe_healthy=False,
            stripe_reason="not_configured",
            stripe_key_mode=None,
            webhook_secret_configured=True,
            checkout_http_status=503,
            webhook_http_status=400,
            http_status=503,
            url="https://dr-nrpg-platform.vercel.app/api/health",
            detail="STRIPE_SECRET_KEY not configured (checkout=503, health=not_configured)",
        ),
    ):
        code = probe_mod.main(["--json"])
    out = json.loads(capsys.readouterr().out)
    assert code == 2
    assert out["checkout_http_status"] == 503
    assert out["webhook_http_status"] == 400
