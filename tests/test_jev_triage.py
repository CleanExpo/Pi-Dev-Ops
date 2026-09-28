"""Tests for scripts/jev_triage.py — offline only; the transport is always a fake."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "jev_triage", Path(__file__).resolve().parent.parent / "scripts" / "jev_triage.py")
jt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(jt)

SECRET = "sk-ant-api03-" + "A" * 40


def _snap(**kw) -> dict:
    base = {"run_id": "r1", "sha": "abc", "surface": "MC-10", "contract": "J1",
            "page_text": f"Margot assets 3 packets {SECRET} contact phill@example.com",
            "network": [{"method": "GET", "path": "/api/pi-ceo/api/margot/assets/options",
                         "status": 200}]}
    base.update(kw)
    return base


def _fake(answer: dict, tokens: int = 1000):
    calls: list[dict] = []

    def transport(body: dict, key: str) -> dict:
        calls.append(body)
        return {"model": "jev-1.13.0", "answers": {"j1": answer},
                "usage": {"input_tokens": tokens, "output_tokens": 5}}
    return transport, calls


def test_body_uses_documented_shape_and_redacts_before_egress():
    body = jt.build_body(_snap())
    assert set(body) == {"state", "model", "questions"}
    assert body["questions"]["j1"]["type"] == "choice"
    assert SECRET not in body["state"] and "phill@example.com" not in body["state"]
    assert "margot/assets/options -> 200" in body["state"]


def test_state_is_truncated_under_the_state_budget():
    state = jt.build_state(_snap(page_text="x" * (jt.MAX_STATE_TOKENS * 4 + 500)))
    assert state.endswith("[TRUNCATED]")
    assert len(state) <= jt.MAX_STATE_TOKENS * 4 + len("\n[TRUNCATED]")


def test_live_label_is_advisory_and_spend_is_recorded(tmp_path):
    ledger = jt.Ledger(tmp_path / "spend.json", "2026-09-28")
    transport, calls = _fake({"type": "choice", "choice": "REAL_DATA", "confidence": 0.9})
    row = jt.evaluate(_snap(), ledger, transport, "k")
    assert row["mode"] == "ADVISORY" and row["status"] == "OK"
    assert row["answer"]["choice"] == "REAL_DATA" and row["model"] == "jev-1.13.0"
    assert len(calls) == 1
    saved = json.loads((tmp_path / "spend.json").read_text())
    assert saved["2026-09-28"] == round(1000 * jt.PRICE_PER_MTOK_INPUT / 1e6, 6)


def test_uncapped_by_default_still_records_spend(tmp_path):
    (tmp_path / "spend.json").write_text(json.dumps({"2026-09-28": 1000.0}))
    ledger = jt.Ledger(tmp_path / "spend.json", "2026-09-28")
    assert jt.DAILY_CAP_USD is None and ledger.allows(10_000_000)


def test_an_explicit_cap_stops_the_call(tmp_path):
    (tmp_path / "spend.json").write_text(json.dumps({"2026-09-28": 4.0}))
    ledger = jt.Ledger(tmp_path / "spend.json", "2026-09-28", cap=4.0)
    transport, calls = _fake({"choice": "REAL_DATA"})
    assert jt.evaluate(_snap(), ledger, transport, "k")["status"] == "BUDGET_STOP"
    assert calls == []


def test_vendor_failure_is_not_evaluated_not_a_crash(tmp_path):
    ledger = jt.Ledger(tmp_path / "spend.json", "2026-09-28")

    def boom(body, key):
        raise TimeoutError("jev timeout")
    assert jt.evaluate(_snap(), ledger, boom, "k")["status"] == "NOT_EVALUATED"


def test_dry_run_sends_nothing(tmp_path, capsys):
    ledger = jt.Ledger(tmp_path / "spend.json", "2026-09-28")
    assert jt.run([_snap()], tmp_path / "out.jsonl", ledger, None, "") == 0
    assert not (tmp_path / "out.jsonl").exists()
    assert json.loads(capsys.readouterr().out)["model"] == "jev-latest"


def test_live_run_without_key_refuses(tmp_path, monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    snaps = tmp_path / "s.jsonl"
    snaps.write_text(json.dumps(_snap()) + "\n")
    assert jt.main(["--snapshots", str(snaps), "--live",
                    "--ledger", str(tmp_path / "l.json")]) == 2


def test_every_contract_has_a_question():
    for c in ("J1", "J2", "J3", "J4"):
        assert jt.build_body(_snap(contract=c))["questions"][c.lower()]["type"] in {
            "choice", "noul", "score"}
